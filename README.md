# World Cup Tracker — USA × México

Static site tracking the US and Mexico through the 2026 World Cup.

## Run locally

`fetch()` requires a server (file:// won't work):

```
cd WorldCupTracker
python3 -m http.server 8000
```

Open http://localhost:8000

## Updating data

Everything lives in `data.json`:

- **Record a result**: set the match's `"result"` to `{ "us": 2, "them": 0 }` (`us` = our team's goals, whether USA or MEX). The match moves from Upcoming to Results automatically.
- **Add articles**: add to the match's `"articles"` array: `{ "title": "ESPN recap", "url": "https://..." }`
- **Update records**: edit `teams.usa.record` / `teams.mex.record` after each match.
- **Knockout matches**: add a new object to `"matches"` with the same fields, plus `"stage": "Round of 32"` (or "Round of 16", "Quarterfinal", etc.) — renders as a gold tag on the card and in results.
- **Collision tracker**: edit `collision.scenarios` — set `"status"` to `"eliminated"` (struck out, dimmed) or `"live"` (highlighted green) as the group stage resolves; `"open"` is the default. Update `"summary"` as the picture changes.

Weather is fetched live from Open-Meteo (no API key) for matches within 15 days; no updates needed.

## Deploy to Cloudflare

Cloudflare Pages, no build step: create a Pages project, point it at this folder (or connect the repo), framework preset "None", build output `/`.
