"""Generate AI tactical previews for matches missing watchNotes.

Run by GitHub Actions after update.py. Requires OPENROUTER_API_KEY env var.
Uses Perplexity Sonar via OpenRouter for web-grounded match previews.
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "perplexity/sonar"
LOOKAHEAD_DAYS = 14

PREFERRED_SOURCES = (
    "The Guardian, BBC Sport, ESPN FC, FourFourTwo, The Athletic, "
    "The Ringer, Tifo Football, Zonal Marking, StatsBomb, "
    "Bundesliga.com, MLSSoccer.com, US Soccer, El País, Marca (English), "
    "NBC Sports, CBS Sports, Sky Sports, 90min, RotoWire"
)


def call_openrouter(system_prompt, user_prompt, max_tokens=200):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY not set, skipping previews", file=sys.stderr)
        return None

    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode()

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "WorldCupTracker/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"OpenRouter call failed: {e}", file=sys.stderr)
        return None


def generate_preview(team_name, opponent, stage, venue, city, kickoff_iso):
    kickoff_dt = datetime.fromisoformat(kickoff_iso)
    date_str = kickoff_dt.strftime("%B %d, %Y")

    if opponent == "TBD":
        prompt = (
            f"{team_name} have a {stage or 'knockout'} match on {date_str} "
            f"at {venue}, {city}. The opponent is not yet determined. "
            f"Write a 2-3 sentence tactical preview focusing on {team_name}'s "
            f"current form, key players, and likely tactical approach for this "
            f"stage of the 2026 FIFA World Cup. Keep it punchy and specific."
        )
    else:
        prompt = (
            f"{team_name} vs {opponent} in the {stage or 'World Cup'} on "
            f"{date_str} at {venue}, {city}. Write a 2-3 sentence tactical "
            f"preview for this 2026 FIFA World Cup match. Mention key player "
            f"matchups, tactical shape, and what to watch for. Keep it punchy "
            f"and specific — no generic filler."
        )

    system = (
        "You are a football tactics analyst writing concise match "
        "previews for a World Cup tracker website. Be specific about "
        "formations, player roles, and tactical battles. No headlines, "
        "no bullet points — just 2-3 flowing sentences."
    )

    text = call_openrouter(system, prompt)
    if text:
        text = text.strip('"')
    return text


def find_preview_links(team_name, opponent, stage):
    if opponent == "TBD":
        query = f"{team_name} {stage or 'knockout'} 2026 World Cup preview"
    else:
        query = f"{team_name} vs {opponent} 2026 World Cup preview"

    system = (
        "You are a sports research assistant. Find real, currently-accessible "
        "match preview articles from quality soccer journalism sources. "
        f"Preferred sources: {PREFERRED_SOURCES}. "
        "Avoid paywalled articles, clickbait aggregators, betting sites, "
        "AI-generated content farms, and YouTube links. "
        "Return ONLY a JSON array of objects with 'title' and 'url' fields. "
        "The title should be like 'Source Name: headline'. "
        "Return at most 3 articles. If you can't find quality previews, "
        "return an empty array []. No explanation, just JSON."
    )

    prompt = f"Find match preview articles for: {query}"

    raw = call_openrouter(system, prompt, max_tokens=400)
    if not raw:
        return []

    try:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if not match:
            return []
        articles = json.loads(match.group())
        valid = []
        for a in articles:
            if isinstance(a, dict) and a.get("title") and a.get("url"):
                url = a["url"]
                if url.startswith("http") and "youtube.com" not in url:
                    valid.append({"title": a["title"], "url": url})
        return valid[:3]
    except (json.JSONDecodeError, ValueError):
        return []


def main():
    data = json.loads(DATA_PATH.read_text())
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=LOOKAHEAD_DAYS)
    changed = False

    for m in data["matches"]:
        if m.get("result"):
            continue

        kickoff = datetime.fromisoformat(m["kickoff"])
        if kickoff > cutoff:
            continue

        team_data = data["teams"].get(m["team"])
        if not team_data:
            continue

        team_name = team_data["name"]
        needs_preview = not m.get("watchNotes")
        needs_links = not m.get("previews")

        if not needs_preview and not needs_links:
            continue

        if needs_preview:
            print(f"Generating preview: {team_name} vs {m['opponent']}...")
            text = generate_preview(
                team_name=team_name,
                opponent=m["opponent"],
                stage=m.get("stage"),
                venue=m.get("venue", "TBD"),
                city=m.get("city", ""),
                kickoff_iso=m["kickoff"],
            )
            if text:
                m["watchNotes"] = text
                changed = True
                print(f"  Preview set ({len(text)} chars)")

        if needs_links:
            print(f"Finding preview links: {team_name} vs {m['opponent']}...")
            links = find_preview_links(
                team_name=team_name,
                opponent=m["opponent"],
                stage=m.get("stage"),
            )
            if links:
                m["previews"] = links
                changed = True
                print(f"  Found {len(links)} preview links")
            else:
                print("  No quality preview links found")

    if not changed:
        print("No previews to generate.")
        return

    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print("data.json updated with new previews.")


if __name__ == "__main__":
    main()
