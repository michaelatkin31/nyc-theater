# NYC Indie Theater (moved)

The live site and maintained code now live in the [`films`](https://github.com/michaelatkin31/films/tree/main/theater) repository:

**[michaelatkin31.github.io/films/theater/](https://michaelatkin31.github.io/films/theater/)**

This repository remains as the original MVP history. Its GitHub Pages root redirects to the combined site.

## Original MVP

A phone-first, date-first guide to performances at ten independent and artist-led New York theater presenters.

The site includes every theater production found for its selected presenters. It has no ratings or quality scores. Listings come from [NYC Small Stages](https://bronder.nyc/) and link directly to each presenter's official details page.

## Presenters

- The Brick
- The Tank
- HERE Arts Center
- Performance Space New York
- The Public Theater (main-stage productions; Joe's Pub concerts are excluded)
- Under St. Marks
- New York Theatre Workshop
- The Flea Theater
- wild project
- The Clemente

## Run locally

```bash
uv sync
uv run python fetch.py
python -m http.server 8000 --directory docs
```

Then open <http://localhost:8000>.

The generated static site lives in `docs/` for GitHub Pages. GitHub Actions refreshes the next 60 days of listings every morning. If the upstream feed is briefly unavailable, the build retains each presenter's last successful cache.
