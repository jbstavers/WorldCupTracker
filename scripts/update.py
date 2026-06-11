"""Update data.json with results, new fixtures, and recap articles.

Run by GitHub Actions on a schedule. Standard library only.
Sources: ESPN public scoreboard API (results, fixtures), Google News RSS
(recap articles, with ESPN match-summary link as fallback).
"""

import json
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data.json"
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={dates}"
NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
TOURNAMENT_START = "20260611"
TOURNAMENT_END = "20260719"

# Tracked teams, keyed by data.json team id -> ESPN abbreviation.
# To track another country: add it here AND to "teams" in data.json
# (with name, group, colors, order) — fixtures and results then flow in.
TEAM_ABBR = {"usa": "USA", "mex": "MEX", "ger": "GER"}

VENUES = {
    "Estadio Banorte": ("Estadio Azteca", "Mexico City", 19.3029, -99.1505),
    "Estadio Azteca": ("Estadio Azteca", "Mexico City", 19.3029, -99.1505),
    "Estadio Akron": ("Estadio Akron", "Guadalajara", 20.6817, -103.4625),
    "Estadio BBVA": ("Estadio BBVA", "Monterrey", 25.6693, -100.2442),
    "SoFi Stadium": ("SoFi Stadium", "Inglewood, CA", 33.9535, -118.3392),
    "Lumen Field": ("Lumen Field", "Seattle, WA", 47.5952, -122.3316),
    "Levi's Stadium": ("Levi's Stadium", "Santa Clara, CA", 37.4030, -121.9696),
    "AT&T Stadium": ("AT&T Stadium", "Arlington, TX", 32.7473, -97.0945),
    "NRG Stadium": ("NRG Stadium", "Houston, TX", 29.6847, -95.4107),
    "GEHA Field at Arrowhead Stadium": ("Arrowhead Stadium", "Kansas City, MO", 39.0489, -94.4839),
    "Arrowhead Stadium": ("Arrowhead Stadium", "Kansas City, MO", 39.0489, -94.4839),
    "Mercedes-Benz Stadium": ("Mercedes-Benz Stadium", "Atlanta, GA", 33.7554, -84.4010),
    "Hard Rock Stadium": ("Hard Rock Stadium", "Miami Gardens, FL", 25.9580, -80.2389),
    "MetLife Stadium": ("MetLife Stadium", "East Rutherford, NJ", 40.8128, -74.0742),
    "Lincoln Financial Field": ("Lincoln Financial Field", "Philadelphia, PA", 39.9008, -75.1675),
    "Gillette Stadium": ("Gillette Stadium", "Foxborough, MA", 42.0909, -71.2643),
    "BMO Field": ("BMO Field", "Toronto", 43.6332, -79.4186),
    "BC Place": ("BC Place", "Vancouver", 49.2768, -123.1119),
}

STAGE_WINDOWS = [
    ("2026-06-28", "2026-07-03", "Round of 32"),
    ("2026-07-04", "2026-07-08", "Round of 16"),
    ("2026-07-09", "2026-07-13", "Quarterfinal"),
    ("2026-07-14", "2026-07-17", "Semifinal"),
    ("2026-07-18", "2026-07-18", "Third-place match"),
    ("2026-07-19", "2026-07-19", "Final"),
]


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "WorldCupTracker/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_scoreboard(dates):
    return json.loads(http_get(SCOREBOARD.format(dates=dates)))


def stage_for_date(date_str):
    for start, end, label in STAGE_WINDOWS:
        if start <= date_str <= end:
            return label
    return None


def tv_from_broadcasts(names):
    english = next((n for n in names if n in ("FOX", "FS1")), "FOX/FS1")
    spanish = "Telemundo" if any(n in ("Tele", "Telemundo", "Universo") for n in names) else "Telemundo"
    streaming = ", ".join(n for n in names if n in ("Peacock", "Tubi")) or "FOX One, Peacock"
    if "FOX One" not in streaming:
        streaming = "FOX One, " + streaming
    return {"english": english, "spanish": spanish, "streaming": streaming}


def event_team_sides(event):
    """Return (ours_key, our_competitor, their_competitor) or None."""
    comp = event["competitions"][0]
    competitors = comp["competitors"]
    for key, abbr in TEAM_ABBR.items():
        for c in competitors:
            if c["team"]["abbreviation"] == abbr:
                other = next(x for x in competitors if x is not c)
                return key, c, other
    return None


def espn_summary_link(event):
    for link in event.get("links", []):
        if "summary" in link.get("rel", []):
            return link["href"]
    return None


def fetch_news_articles(query, limit=3):
    try:
        raw = http_get(NEWS_RSS.format(query=urllib.parse.quote(query)), timeout=20)
        root = ET.fromstring(raw)
        articles = []
        for item in root.iter("item"):
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            source = item.find("source")
            source_name = source.text if source is not None else ""
            if not link or "youtube.com" in link:
                continue
            articles.append({"title": f"{source_name}: {title}" if source_name else title, "url": link})
            if len(articles) >= limit:
                break
        return articles
    except Exception as e:
        print(f"News fetch failed ({query}): {e}", file=sys.stderr)
        return []


def match_event(data, event):
    """Find the data.json match corresponding to an ESPN event, or None."""
    sides = event_team_sides(event)
    if not sides:
        return None
    key, _, _ = sides
    event_id = event["id"]
    event_dt = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
    for m in data["matches"]:
        if m.get("espnId") == event_id:
            return m
        if m["team"] != key:
            continue
        kickoff = datetime.fromisoformat(m["kickoff"])
        if abs((kickoff - event_dt).total_seconds()) <= 6 * 3600:
            m["espnId"] = event_id
            return m
    return None


def apply_result(m, event, data):
    sides = event_team_sides(event)
    key, ours, theirs = sides
    comp = event["competitions"][0]
    if not comp["status"]["type"].get("completed"):
        return False
    us, them = int(ours["score"]), int(theirs["score"])
    m["result"] = {"us": us, "them": them}
    if ours.get("shootoutScore") is not None and theirs.get("shootoutScore") is not None:
        m["result"]["note"] = f"{ours['shootoutScore']}–{theirs['shootoutScore']} on penalties"
    team_name = data["teams"][key]["name"]
    articles = fetch_news_articles(f"{team_name} {m['opponent']} World Cup recap")
    if not articles:
        link = espn_summary_link(event)
        if link:
            articles = [{"title": "ESPN match report", "url": link}]
    m["articles"] = articles
    print(f"Result: {TEAM_ABBR[key]} {us}-{them} {m['opponent']}")
    return True


def add_fixture(data, event):
    sides = event_team_sides(event)
    key, ours, theirs = sides
    comp = event["competitions"][0]
    date_str = event["date"][:10]
    venue_raw = comp.get("venue", {}).get("fullName", "TBD")
    name, city, lat, lon = VENUES.get(venue_raw, (venue_raw, "", None, None))
    broadcasts = []
    for b in comp.get("broadcasts", []):
        broadcasts += b.get("names", [])
    fixture = {
        "team": key,
        "opponent": theirs["team"]["displayName"],
        "stage": stage_for_date(date_str),
        "kickoff": event["date"].replace("Z", "+00:00"),
        "venue": name,
        "city": city,
        "lat": lat,
        "lon": lon,
        "tv": tv_from_broadcasts(broadcasts),
        "watchNotes": "",
        "previews": [],
        "result": None,
        "articles": [],
        "espnId": event["id"],
    }
    data["matches"].append(fixture)
    print(f"New fixture: {TEAM_ABBR[key]} vs {fixture['opponent']} on {date_str} ({fixture['stage']})")


def recompute_records(data):
    for key in data["teams"]:
        w = d = l = gf = ga = 0
        for m in data["matches"]:
            if m["team"] != key or not m.get("result"):
                continue
            r = m["result"]
            gf, ga = gf + r["us"], ga + r["them"]
            if r["us"] > r["them"]:
                w += 1
            elif r["us"] < r["them"]:
                l += 1
            else:
                d += 1
        data["teams"][key]["record"] = {"w": w, "d": d, "l": l, "gf": gf, "ga": ga}


def main():
    original = DATA_PATH.read_text()
    data = json.loads(original)
    now = datetime.now(timezone.utc)

    # 1. Discover fixtures across the whole tournament (past + future),
    #    so a newly tracked team gets its full schedule backfilled.
    try:
        board = fetch_scoreboard(f"{TOURNAMENT_START}-{TOURNAMENT_END}")
        for event in board.get("events", []):
            if event_team_sides(event) is None:
                continue
            if match_event(data, event) is None:
                add_fixture(data, event)
    except Exception as e:
        print(f"Fixture discovery failed: {e}", file=sys.stderr)

    # 2. Results for any match past kickoff (ESPN's `completed` flag is
    #    the gate against recording a result early)
    pending_dates = set()
    for m in data["matches"]:
        if m.get("result"):
            continue
        kickoff = datetime.fromisoformat(m["kickoff"])
        if now > kickoff:
            d = kickoff.astimezone(timezone.utc).strftime("%Y%m%d")
            pending_dates.add(d)
            pending_dates.add((kickoff + timedelta(days=1)).strftime("%Y%m%d"))

    for dates in sorted(pending_dates):
        try:
            board = fetch_scoreboard(dates)
        except Exception as e:
            print(f"Scoreboard fetch failed ({dates}): {e}", file=sys.stderr)
            continue
        for event in board.get("events", []):
            m = match_event(data, event)
            if m is not None and not m.get("result"):
                status = event["competitions"][0]["status"]["type"]
                if not apply_result(m, event, data):
                    print(f"Not final yet: {m['team'].upper()} vs {m['opponent']} "
                          f"— ESPN status {status.get('name')} ({status.get('detail')})")

    recompute_records(data)
    data["matches"].sort(key=lambda m: m["kickoff"])

    before = {k: v for k, v in json.loads(original).items() if k != "updated"}
    after = {k: v for k, v in data.items() if k != "updated"}
    if before == after:
        print("No changes.")
        return
    data["updated"] = now.strftime("%Y-%m-%d %H:%M UTC")
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print("data.json updated.")


if __name__ == "__main__":
    main()
