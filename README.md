# World Cup Tracker — USA × México

Static site tracking the US and Mexico through the 2026 World Cup.

## Run locally

`fetch()` requires a server (file:// won't work):

```
cd WorldCupTracker
python3 -m http.server 8000
```

Open http://localhost:8000

## Automatic updates

A GitHub Action (`.github/workflows/update.yml`) runs `scripts/update.py` every 3 hours and commits `data.json` only when something changed — so on non-game days there are no commits, and results land within ~3 hours of full time. It:

- pulls final scores from ESPN's public scoreboard API (no key) once a match is 2.5+ hours past kickoff
- attaches recap articles from Google News RSS, falling back to the ESPN match report
- discovers new fixtures (knockout rounds) automatically as they're scheduled, with stage, venue, and weather coordinates
- recomputes each team's W-D-L record

Run it on demand from the repo's Actions tab (workflow_dispatch), or locally with `python3 scripts/update.py`.

Not automated (still hand-edited): `watchNotes` and `previews` for new matches, and the `collision.scenarios` statuses — those need judgment.

## Updating data by hand

Everything lives in `data.json`:

- **Record a result**: set the match's `"result"` to `{ "us": 2, "them": 0 }` (`us` = our team's goals, whether USA or MEX). The match moves from Upcoming to Results automatically.
- **Add articles**: add to the match's `"articles"` array: `{ "title": "ESPN recap", "url": "https://..." }`
- **Update records**: edit `teams.usa.record` / `teams.mex.record` after each match.
- **Knockout matches**: add a new object to `"matches"` with the same fields, plus `"stage": "Round of 32"` (or "Round of 16", "Quarterfinal", etc.) — renders as a gold tag on the card and in results.
- **Collision tracker**: edit `collision.scenarios` — set `"status"` to `"eliminated"` (struck out, dimmed) or `"live"` (highlighted green) as the group stage resolves; `"open"` is the default. Update `"summary"` as the picture changes.

Weather is fetched live from Open-Meteo (no API key) for matches within 15 days; no updates needed.

## Deploy to Cloudflare

Cloudflare Pages, no build step: create a Pages project, point it at this folder (or connect the repo), framework preset "None", build output `/`.
