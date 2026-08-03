from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scraper.bronder import SOURCE_NAME, SOURCE_URL, VENUES, SourceError, fetch


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "source-cache"
DOCS_DIR = ROOT / "docs"
NY_TZ = ZoneInfo("America/New_York")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_cached_events(venue_key: str) -> list[dict[str, Any]]:
    path = CACHE_DIR / f"{venue_key}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        events = payload.get("events", [])
        return events if isinstance(events, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def load_events() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fetched_at = datetime.now(NY_TZ).isoformat(timespec="seconds")
    try:
        fresh_by_venue = fetch()
        fetch_error = ""
    except SourceError as exc:
        fresh_by_venue = None
        fetch_error = str(exc)

    events: list[dict[str, Any]] = []
    health: list[dict[str, Any]] = []
    for venue in VENUES:
        if fresh_by_venue is not None:
            venue_events = fresh_by_venue.get(venue.key, [])
            write_json(
                CACHE_DIR / f"{venue.key}.json",
                {
                    "venue": venue.name,
                    "fetched_at": fetched_at,
                    "events": venue_events,
                },
            )
            status = "fresh" if venue_events else "no upcoming shows"
            note = ""
        else:
            venue_events = read_cached_events(venue.key)
            status = "cached" if venue_events else "unavailable"
            note = fetch_error
        events.extend(venue_events)
        health.append(
            {
                "venue": venue.name,
                "status": status,
                "events": len(venue_events),
                "note": note,
            }
        )

    events.sort(
        key=lambda event: (event["performances"][0]["datetime"], event["title"].casefold())
    )
    return events, health


def render_site(payload: dict[str, Any]) -> None:
    environment = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("index.html")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "index.html").write_text(
        template.render(
            payload=payload,
            venues=[{"key": venue.key, "name": venue.name} for venue in VENUES],
        ),
        encoding="utf-8",
    )
    (DOCS_DIR / ".nojekyll").touch()


def write_health(health: list[dict[str, Any]], generated_at: str) -> None:
    rows = [
        "# Source health",
        "",
        f"Last generated: {generated_at}",
        "",
        "| Presenter | Status | Productions |",
        "| --- | --- | ---: |",
    ]
    rows.extend(
        f'| {item["venue"]} | {item["status"]} | {item["events"]} |'
        for item in health
    )
    rows.extend(
        [
            "",
            f"Technical feed: [{SOURCE_NAME}]({SOURCE_URL}). Every listing links to its presenter.",
            "",
        ]
    )
    (ROOT / "HEALTH.md").write_text("\n".join(rows), encoding="utf-8")


def main() -> None:
    events, health = load_events()
    generated_at = datetime.now(NY_TZ).isoformat(timespec="seconds")
    payload = {
        "generated_at": generated_at,
        "horizon_days": 60,
        "events": events,
        "health": health,
        "source": {"name": SOURCE_NAME, "url": SOURCE_URL},
    }
    write_json(DATA_DIR / "events.json", payload)
    write_health(health, generated_at)
    render_site(payload)
    performance_count = sum(len(event["performances"]) for event in events)
    print(
        f"Built docs/index.html with {len(events)} productions and "
        f"{performance_count} performances."
    )


if __name__ == "__main__":
    main()
