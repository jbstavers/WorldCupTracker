const WEATHER_CODES = {
  0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
  45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Drizzle",
  61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
  71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Showers", 81: "Showers",
  82: "Heavy showers", 95: "Thunderstorms", 96: "Thunderstorms", 99: "Thunderstorms"
};

async function init() {
  const res = await fetch("data.json");
  const data = await res.json();
  function nextKickoff(key) {
    const upcoming = data.matches
      .filter(m => m.team === key && !m.result)
      .map(m => new Date(m.kickoff).getTime());
    return upcoming.length ? Math.min(...upcoming) : Infinity;
  }
  const order = Object.keys(data.teams).sort((a, b) => {
    const diff = nextKickoff(a) - nextKickoff(b);
    if (diff !== 0) return diff;
    return (data.teams[a].order || 99) - (data.teams[b].order || 99);
  });
  renderMasthead(data, order);
  renderColumns(data, order);
  renderCollision(data, order);
  fetchWeather(data.matches);
}

function renderMasthead(data, order) {
  document.getElementById("masthead-title").innerHTML =
    order.map(k => data.teams[k].name).join(' <span class="x">×</span> ');
  const stripes = document.getElementById("masthead-stripes");
  for (const k of order) {
    const c = data.teams[k].colors;
    for (const color of [c.banner, c.trim]) {
      const s = document.createElement("span");
      s.className = "stripe";
      s.style.background = color;
      stripes.appendChild(s);
    }
  }
}

function teamStyle(t) {
  const c = t.colors;
  return `--t-banner:${c.banner};--t-trim:${c.trim};--t-light:${c.light};--t-text:${c.text};`;
}

function renderColumns(data, order) {
  const scarf = document.getElementById("scarf");
  scarf.style.gridTemplateColumns = `repeat(${order.length}, minmax(0, 1fr))`;
  const sorted = [...data.matches].sort((a, b) => new Date(a.kickoff) - new Date(b.kickoff));

  for (const key of order) {
    const t = data.teams[key];
    const r = t.record;
    const col = document.createElement("section");
    col.className = "team-col";
    col.setAttribute("aria-label", t.name);
    col.style.cssText = teamStyle(t);
    col.innerHTML = `
      <div class="team-banner">
        <div>
          <h2>${t.name}</h2>
          <p class="team-meta">Group ${t.group} · ${r.w}W ${r.d}D ${r.l}L</p>
        </div>
        <span class="crest" aria-hidden="true">${t.shortName.slice(0, 2)}</span>
      </div>
      <div class="team-body">
        <h3 class="section-label">Upcoming</h3>
        <div class="upcoming"></div>
        <h3 class="section-label">Results</h3>
        <div class="results"></div>
      </div>`;
    const up = col.querySelector(".upcoming");
    const done = col.querySelector(".results");
    let isNext = true;
    for (const m of sorted) {
      if (m.team !== key) continue;
      if (m.result) {
        done.appendChild(resultCard(m, t));
      } else {
        up.appendChild(matchCard(m, isNext));
        isNext = false;
      }
    }
    if (!up.children.length) up.innerHTML = `<p class="empty-note">No matches scheduled — check back after this round.</p>`;
    if (!done.children.length) done.innerHTML = `<p class="empty-note">No matches played yet.</p>`;
    scarf.appendChild(col);
  }
}

function fmtKickoff(iso) {
  const d = new Date(iso);
  const pt = d.toLocaleString("en-US", {
    weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
    timeZone: "America/Los_Angeles"
  });
  const mx = d.toLocaleString("en-US", {
    hour: "numeric", minute: "2-digit",
    timeZone: "America/Mexico_City"
  });
  return `${pt} PT / ${mx} MX`;
}

function relativeBadge(iso) {
  const now = new Date();
  const d = new Date(iso);
  const days = Math.floor((d - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
  if (days <= 0) return { text: "Today", soon: true };
  if (days === 1) return { text: "Tomorrow", soon: true };
  return { text: `In ${days} days`, soon: days <= 3 };
}

function matchCard(m, isNext) {
  const card = document.createElement("div");
  card.className = "match-card" + (isNext ? " next" : "");
  const badge = relativeBadge(m.kickoff);
  const stageTag = m.stage ? `<div class="stage-tag-row"><span class="stage-tag">${m.stage}</span></div>` : "";
  card.innerHTML = `
    ${stageTag}
    <div class="match-top">
      <span class="match-opp">vs ${m.opponent}</span>
      <span class="badge ${badge.soon ? "badge-soon" : "badge-later"}">${badge.text}</span>
    </div>
    <div class="match-when">${fmtKickoff(m.kickoff)} · ${m.venue}${m.city ? ", " + m.city : ""}</div>
    ${m.lat != null ? `<div class="match-row">
      <span class="weather" data-id="${m.kickoff}|${m.lat}|${m.lon}"><span class="ico">☁</span> Loading forecast…</span>
    </div>` : ""}
    <div class="match-row">
      <span><span class="ico">📺</span> ${m.tv.english} (Eng) · ${m.tv.spanish} (Esp)</span>
      <span><span class="ico">▶</span> ${m.tv.streaming}</span>
    </div>
    ${m.watchNotes ? `<p class="watch-notes">${m.watchNotes}</p>` : ""}
    ${previewLinks(m)}`;
  return card;
}

function previewLinks(m) {
  if (!m.previews || !m.previews.length) return "";
  const links = m.previews
    .map(p => `<a href="${p.url}" target="_blank" rel="noopener">${p.title}</a>`)
    .join(" · ");
  return `<div class="preview-links"><span class="preview-label">Previews:</span> ${links}</div>`;
}

function resultCard(m, team) {
  const card = document.createElement("div");
  card.className = "result-card";
  const r = m.result;
  const outcome = r.us > r.them ? "win" : r.us < r.them ? "loss" : "draw";
  const links = (m.articles || [])
    .map(a => `<a href="${a.url}" target="_blank" rel="noopener">${a.title}</a>`)
    .join(" · ");
  card.innerHTML = `
    <div class="result-score"><span class="${outcome}">${team.shortName} ${r.us}–${r.them}</span> ${m.opponent}${r.note ? ` <span class="result-note">(${r.note})</span>` : ""}${m.stage ? ` <span class="stage-tag">${m.stage}</span>` : ""}</div>
    <div class="result-meta">${fmtKickoff(m.kickoff)} · ${m.venue}${m.city ? ", " + m.city : ""}</div>
    ${links ? `<div class="result-articles">${links}</div>` : ""}`;
  return card;
}

function renderCollision(data, order) {
  const wrap = document.getElementById("collision-pairs");
  for (const pair of data.collision.pairs) {
    const [a, b] = pair.teams.map(k => data.teams[k]);
    const block = document.createElement("div");
    block.className = "pair-block";
    block.innerHTML = `
      <h3 class="pair-title">
        <span style="color:${a.colors.banner}">${a.shortName}</span>
        <span class="x">×</span>
        <span style="color:${b.colors.banner}">${b.shortName}</span>
      </h3>
      <p class="pair-summary">${pair.summary}</p>
      <div class="pair-scenarios"></div>`;
    const list = block.querySelector(".pair-scenarios");
    for (const s of pair.scenarios) {
      const row = document.createElement("div");
      row.className = `scenario scenario-${s.status || "open"}`;
      row.innerHTML = `
        <div>
          <div class="scenario-label">${s.label}</div>
          <div class="scenario-detail">${s.detail}</div>
        </div>
        <span class="scenario-meeting">${s.meeting}</span>`;
      list.appendChild(row);
    }
    wrap.appendChild(block);
  }
}

async function fetchWeather(matches) {
  const upcoming = matches.filter(m => !m.result && m.lat != null);
  for (const m of upcoming) {
    const el = document.querySelector(`.weather[data-id="${m.kickoff}|${m.lat}|${m.lon}"]`);
    if (!el) continue;
    const kickoff = new Date(m.kickoff);
    const daysOut = (kickoff - new Date()) / 86400000;
    if (daysOut > 15) {
      el.innerHTML = `<span class="ico">☁</span> Forecast available closer to kickoff`;
      continue;
    }
    try {
      const dateStr = m.kickoff.slice(0, 10);
      const url = `https://api.open-meteo.com/v1/forecast?latitude=${m.lat}&longitude=${m.lon}` +
        `&hourly=temperature_2m,weather_code,precipitation_probability` +
        `&temperature_unit=fahrenheit&timezone=auto&start_date=${dateStr}&end_date=${dateStr}`;
      const res = await fetch(url);
      const w = await res.json();
      const hourLocal = new Date(kickoff.toLocaleString("en-US", { timeZone: w.timezone })).getHours();
      const i = Math.min(hourLocal, w.hourly.time.length - 1);
      const temp = Math.round(w.hourly.temperature_2m[i]);
      const cond = WEATHER_CODES[w.hourly.weather_code[i]] || "—";
      const rain = w.hourly.precipitation_probability ? w.hourly.precipitation_probability[i] : null;
      el.innerHTML = `<span class="ico">☁</span> ${temp}°F, ${cond}` +
        (rain != null ? ` · ${rain}% rain` : "");
    } catch {
      el.innerHTML = `<span class="ico">☁</span> Forecast unavailable`;
    }
  }
}

init();
