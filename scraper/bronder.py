from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Tag


SOURCE_NAME = "NYC Small Stages"
SOURCE_URL = "https://bronder.nyc/"
NY_TZ = ZoneInfo("America/New_York")
TIME_RE = re.compile(r"\bat\s+(\d{1,2}):(\d{2})\s*([AP]M)\b", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Venue:
    key: str
    name: str
    neighborhood: str


VENUES = (
    Venue("brick", "The Brick", "Williamsburg"),
    Venue("tank", "The Tank", "Midtown West"),
    Venue("here", "HERE Arts Center", "SoHo"),
    Venue("performance_space", "Performance Space New York", "East Village"),
    Venue("public_theater", "The Public Theater", "NoHo"),
    Venue("under_st_marks", "Under St. Marks", "East Village"),
    Venue("nytw", "New York Theatre Workshop", "East Village"),
    Venue("flea_theater", "The Flea Theater", "TriBeCa"),
    Venue("wild_project", "wild project", "East Village"),
    Venue("clemente_center", "The Clemente", "Lower East Side"),
)

VENUE_BY_KEY = {venue.key: venue for venue in VENUES}

# NYC Small Stages categorizes Joe's Pub performances as theater. The Public's
# production URLs are distinct, so this drops the concert feed without trying to
# judge the productions themselves.
PUBLIC_NON_THEATER_PATHS = ("/performances-jp/",)
NON_THEATER_TITLE_RE = re.compile(
    r"\b(brickflix|films?|movies?|screenings?|music videos?)\b", re.IGNORECASE
)


class SourceError(RuntimeError):
    pass


def clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", value).strip()


def _event_url(row: Tag) -> str | None:
    link = row.select_one('a[data-content-type="source_link"][href]')
    if not link:
        return None
    url = str(link.get("href", "")).strip()
    return url if url.startswith(("https://", "http://")) else None


def _time_from_label(label: str) -> tuple[str, int] | None:
    match = TIME_RE.search(label)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    meridiem = match.group(3).lower()
    hour_24 = hour % 12 + (12 if meridiem == "pm" else 0)
    display = f"{hour}:{minute:02d}{meridiem}"
    return display, hour_24 * 60 + minute


def _performances(row: Tag, start: date, end: date) -> list[dict[str, Any]]:
    raw_dates = str(row.get("data-dates", ""))
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in raw_dates.split(";"):
        if "|" not in item:
            continue
        raw_date, label = item.split("|", 1)
        try:
            performance_date = date.fromisoformat(raw_date.strip())
        except ValueError:
            continue
        parsed_time = _time_from_label(label)
        if not parsed_time or not start <= performance_date <= end:
            continue
        display_time, minutes = parsed_time
        key = (performance_date.isoformat(), minutes)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "date": performance_date.isoformat(),
                "time": display_time,
                "minutes": minutes,
                "datetime": datetime.combine(
                    performance_date,
                    datetime.min.time(),
                    tzinfo=NY_TZ,
                ).replace(hour=minutes // 60, minute=minutes % 60).isoformat(),
            }
        )
    return sorted(result, key=lambda performance: performance["datetime"])


def _is_theater_event(venue_key: str, title: str, url: str) -> bool:
    normalized_title = title.casefold()
    if NON_THEATER_TITLE_RE.search(normalized_title):
        return False
    if venue_key == "public_theater":
        path = urlparse(url).path.casefold()
        if any(blocked in path for blocked in PUBLIC_NON_THEATER_PATHS):
            return False
    return True


def fetch(*, horizon_days: int = 60, today: date | None = None) -> dict[str, list[dict[str, Any]]]:
    """Fetch selected theater-only venue listings grouped by venue key."""
    current_date = today or datetime.now(NY_TZ).date()
    end_date = current_date + timedelta(days=horizon_days)
    try:
        response = requests.get(
            SOURCE_URL,
            timeout=30,
            headers={
                "User-Agent": (
                    "NYC-Indie-Theater/0.1 "
                    "(+https://github.com/michaelatkin31/nyc-theater)"
                )
            },
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SourceError(f"Could not fetch {SOURCE_URL}: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    if not soup.select("article.venue-card"):
        raise SourceError("NYC Small Stages returned an unexpected page")

    grouped: dict[str, list[dict[str, Any]]] = {venue.key: [] for venue in VENUES}
    for venue in VENUES:
        card = soup.select_one(f'article.venue-card[data-venue="{venue.key}"]')
        if not card:
            continue
        for row in card.select('.show-preview-row[data-kind="theater"]'):
            title_element = row.select_one(".show-preview-title")
            url = _event_url(row)
            if not title_element or not url:
                continue
            title = clean_text(title_element.get_text(" ", strip=True))
            if not title or not _is_theater_event(venue.key, title, url):
                continue
            performances = _performances(row, current_date, end_date)
            if not performances:
                continue
            description_element = row.select_one(".show-preview-description")
            description = (
                clean_text(description_element.get_text(" ", strip=True))
                if description_element
                else ""
            )
            event_hash = hashlib.sha1(
                f"{venue.key}|{title.casefold()}|{url}".encode(), usedforsecurity=False
            ).hexdigest()[:12]
            grouped[venue.key].append(
                {
                    "id": f"{venue.key}-{event_hash}",
                    "title": title,
                    "venue": venue.name,
                    "venue_key": venue.key,
                    "neighborhood": venue.neighborhood,
                    "description": description,
                    "url": url,
                    "source": SOURCE_NAME,
                    "performances": performances,
                }
            )

        grouped[venue.key].sort(
            key=lambda event: (event["performances"][0]["datetime"], event["title"].casefold())
        )
    return grouped
