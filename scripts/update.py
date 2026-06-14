"""Update data.json with results, new fixtures, and recap articles.

Run by GitHub Actions on a schedule. Standard library only.
Sources: football-data.org (fixtures and results), Google News RSS (recap articles).
"""

import json
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data.json"
NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
TOURNAMENT_START_DATE = "2026-06-11"
TOURNAMENT_END_DATE = "2026-07-19"

# football-data.org is the sole data source for fixtures and results.
# To track another country: add it here AND to "teams" in data.json.
FOOTBALL_DATA_TOKEN = "0def0cbd236d4dfeafc8701aaa44672c"
FD_MATCHES = ("https://api.football-data.org/v4/competitions/WC/matches"
              "?dateFrom={lo}&dateTo={hi}")
FD_TEAM_NAMES = {
    "usa": {"united states", "usa", "united states of america"},
    "mex": {"mexico", "méxico"},
    "ger": {"germany", "deutschland"},
}

# Default TV info for newly discovered fixtures (knockout round games etc.)
DEFAULT_TV = {
    "english": "FOX/FS1",
    "spanish": "Telemundo",
    "streaming": "FOX One, Peacock",
}

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


def stage_for_date(date_str):
    for start, end, label in STAGE_WINDOWS:
        if start <= date_str <= end:
            return label
    return None


def fetch_fd_matches(lo, hi):
    req = urllib.request.Request(
        FD_MATCHES.format(lo=lo, hi=hi),
        headers={"X-Auth-Token": FOOTBALL_DATA_TOKEN,
                 "User-Agent": "WorldCupTracker/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()).get("matches", [])


def fd_tracked_team(fm):
    """Return (team_key, opponent_name) if an FD match involves a tracked team, else None."""
    home_raw = (fm.get("homeTeam") or {}).get("name") or ""
    away_raw = (fm.get("awayTeam") or {}).get("name") or ""
    home_lower = home_raw.lower()
    away_lower = away_raw.lower()
    for key, names in FD_TEAM_NAMES.items():
        if home_lower in names:
            return key, away_raw
        if away_lower in names:
            return key, home_raw
    return None


def find_local_match(data, fm):
    """Find the data.json match for an FD match (by team + kickoff proximity), or None."""
    result = fd_tracked_team(fm)
    if not result:
        return None
    key, _ = result
    fd_dt = datetime.fromisoformat(fm["utcDate"].replace("Z", "+00:00"))
    for m in data["matches"]:
        if m["team"] != key:
            continue
        kickoff = datetime.fromisoformat(m["kickoff"])
        if abs((kickoff - fd_dt).total_seconds()) <= 6 * 3600:
            return m
    return None


def find_fd_match(fd_matches, m):
    """Find the FD match for a data.json fixture, or None."""
    names = FD_TEAM_NAMES.get(m["team"], set())
    kickoff = datetime.fromisoformat(m["kickoff"])
    for fm in fd_matches:
        home = ((fm.get("homeTeam") or {}).get("name") or "").lower()
        away = ((fm.get("awayTeam") or {}).get("name") or "").lower()
        if home not in names and away not in names:
            continue
        fd_dt = datetime.fromisoformat(fm["utcDate"].replace("Z", "+00:00"))
        if abs((fd_dt - kickoff).total_seconds()) <= 6 * 3600:
            return fm
    return None


def add_fixture_fd(data, fm):
    result = fd_tracked_team(fm)
    if not result:
        return
    key, opponent = result
    kickoff = fm["utcDate"].replace("Z", "+00:00")
    date_str = kickoff[:10]
    venue_raw = fm.get("venue") or "TBD"
    name, city, lat, lon = VENUES.get(venue_raw, (venue_raw, "", None, None))
    fixture = {
        "team": key,
        "opponent": opponent,
        "stage": stage_for_date(date_str),
        "kickoff": kickoff,
        "venue": name,
        "city": city,
        "lat": lat,
        "lon": lon,
        "tv": DEFAULT_TV,
        "watchNotes": "",
        "previews": [],
        "result": None,
        "articles": [],
    }
    data["matches"].append(fixture)
    print(f"New fixture: {key.upper()} vs {opponent} on {date_str} ({fixture['stage']})")


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


def apply_result_fd(m, fm, data):
    names = FD_TEAM_NAMES.get(m["team"], set())
    home = ((fm.get("homeTeam") or {}).get("name") or "").lower()
    score = fm.get("score") or {}
    ft = score.get("fullTime") or {}
    home_goals, away_goals = ft.get("home"), ft.get("away")
    if home_goals is None or away_goals is None:
        return False
    we_are_home = home in names
    us = home_goals if we_are_home else away_goals
    them = away_goals if we_are_home else home_goals
    m["result"] = {"us": us, "them": them}
    pens = score.get("penalties") or {}
    if score.get("duration") == "PENALTIES" and pens.get("home") is not None:
        ph, pa = pens["home"], pens["away"]
        us_p, them_p = (ph, pa) if we_are_home else (pa, ph)
        m["result"]["note"] = f"{us_p}–{them_p} on penalties"
    team_name = data["teams"][m["team"]]["name"]
    articles = fetch_news_articles(f"{team_name} {m['opponent']} World Cup recap")
    m["articles"] = articles
    print(f"Result: {m['team'].upper()} {us}-{them} {m['opponent']}")
    return True


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

    # Fetch today's matches — all we need for otherMatches and same-day results
    today_str = now.strftime("%Y-%m-%d")
    try:
        fd_today = fetch_fd_matches(today_str, today_str)
    except Exception as e:
        print(f"football-data fetch failed: {e}", file=sys.stderr)
        fd_today = []

    # Apply results for tracked matches past kickoff
    pending = [m for m in data["matches"]
               if not m.get("result")
               and now > datetime.fromisoformat(m["kickoff"])]
    # Separate pending into today vs older (older need their own fetch)
    pending_today = [m for m in pending if m["kickoff"][:10] == today_str]
    pending_older = [m for m in pending if m["kickoff"][:10] != today_str]
    fd_older = []
    if pending_older:
        kicks = [datetime.fromisoformat(m["kickoff"]).astimezone(timezone.utc) for m in pending_older]
        lo = (min(kicks) - timedelta(days=1)).strftime("%Y-%m-%d")
        hi = (max(kicks) + timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            fd_older = fetch_fd_matches(lo, hi)
        except Exception as e:
            print(f"football-data fetch failed (older results): {e}", file=sys.stderr)
    fd_all = fd_today + fd_older
    for m in pending:
        fm = find_fd_match(fd_all, m)
        if fm is None:
            print(f"No FD match found: {m['team'].upper()} vs {m['opponent']}")
        elif fm.get("status") != "FINISHED":
            print(f"Not final yet: {m['team'].upper()} vs {m['opponent']} "
                  f"— FD status {fm.get('status')}")
        else:
            apply_result_fd(m, fm, data)

    # Discover new fixtures for tracked teams from today's data
    for fm in fd_today:
        if fd_tracked_team(fm) is None:
            continue
        if find_local_match(data, fm) is None:
            add_fixture_fd(data, fm)

    recompute_records(data)
    data["matches"].sort(key=lambda m: m["kickoff"])

    # Rebuild non-tracked match list for the Today's Games page
    other_matches = []
    for fm in fd_today:
        if fd_tracked_team(fm) is not None:
            continue
        home_raw = (fm.get("homeTeam") or {}).get("name") or "?"
        away_raw = (fm.get("awayTeam") or {}).get("name") or "?"
        kickoff = fm["utcDate"].replace("Z", "+00:00")
        venue_raw = fm.get("venue") or ""
        name, city, _, _ = VENUES.get(venue_raw, (venue_raw, "", None, None))
        score = fm.get("score") or {}
        ft = score.get("fullTime") or {}
        result = None
        if fm.get("status") == "FINISHED" and ft.get("home") is not None:
            result = {"home": ft["home"], "away": ft["away"]}
            pens = score.get("penalties") or {}
            if score.get("duration") == "PENALTIES" and pens.get("home") is not None:
                result["note"] = f"{pens['home']}–{pens['away']} on penalties"
        other_matches.append({
            "home": home_raw,
            "away": away_raw,
            "kickoff": kickoff,
            "venue": name,
            "city": city,
            "result": result,
        })
    other_matches.sort(key=lambda m: m["kickoff"])
    data["otherMatches"] = other_matches

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
