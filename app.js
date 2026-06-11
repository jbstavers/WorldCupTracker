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
  renderTeamMeta(data);
  renderMatches(data);
  renderCollision(data.collision);
  fetchWeather(data.matches);
}

function renderTeamMeta(data) {
  for (const key of ["usa", "mex"]) {
    const t = data.teams[key];
    const r = t.record;
    document.getElementById(`meta-${key}`).textContent =
      `Group ${t.group} · ${r.w}W ${r.d}D ${r.l}L · vs ${t.groupOpponents.join(", ")}`;
  }
}

function fmtKickoff(iso) {
  const d = new Date(iso);
  return d.toLocaleString([], {
    weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit"
  });
}

function relativeBadge(iso) {
  const now = new Date();
  const d = new Date(iso);
  const days = Math.floor((d - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
  if (d < now && days <= 0) return { text: "Today", soon: true };
  if (days === 0) return { text: "Today", soon: true };
  if (days === 1) return { text: "Tomorrow", soon: true };
  if (days <= 3) return { text: `In ${days} days`, soon: true };
  return { text: `In ${days} days`, soon: false };
}

function renderMatches(data) {
  const containers = {
    usa: { up: document.getElementById("upcoming-usa"), done: document.getElementById("results-usa") },
    mex: { up: document.getElementById("upcoming-mex"), done: document.getElementById("results-mex") }
  };
  const sorted = [...data.matches].sort((a, b) => new Date(a.kickoff) - new Date(b.kickoff));
  const firstUpcoming = {};

  for (const m of sorted) {
    if (m.result) {
      containers[m.team].done.appendChild(resultCard(m, data.teams[m.team]));
    } else {
      const isNext = !firstUpcoming[m.team];
      firstUpcoming[m.team] = true;
      containers[m.team].up.appendChild(matchCard(m, isNext));
    }
  }

  for (const key of ["usa", "mex"]) {
    if (!containers[key].up.children.length)
      containers[key].up.innerHTML = `<p class="empty-note">Group stage complete — see results below.</p>`;
    if (!containers[key].done.children.length)
      containers[key].done.innerHTML = `<p class="empty-note">No matches played yet.</p>`;
  }
}

function matchCard(m, isNext) {
  const card = document.createElement("div");
  card.className = "match-card" + (isNext ? ` next-${m.team}` : "");
  const badge = relativeBadge(m.kickoff);
  const badgeClass = badge.soon ? (m.team === "mex" ? "badge-soon-mex" : "badge-soon") : "badge-later";
  const stageTag = m.stage ? `<div class="stage-tag-row"><span class="stage-tag">${m.stage}</span></div>` : "";
  card.innerHTML = `
    ${stageTag}
    <div class="match-top">
      <span class="match-opp">vs ${m.opponent}</span>
      <span class="badge ${badgeClass}">${badge.text}</span>
    </div>
    <div class="match-when">${fmtKickoff(m.kickoff)} · ${m.venue}, ${m.city}</div>
    <div class="match-row">
      <span class="weather" data-id="${m.kickoff}|${m.lat}|${m.lon}"><span class="ico">☁</span> Loading forecast…</span>
    </div>
    <div class="match-row">
      <span><span class="ico">📺</span> ${m.tv.english} (Eng) · ${m.tv.spanish} (Esp)</span>
      <span><span class="ico">▶</span> ${m.tv.streaming}</span>
    </div>
    <p class="watch-notes">${m.watchNotes}</p>
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
    <div class="result-score"><span class="${outcome}">${team.shortName} ${r.us}–${r.them}</span> ${m.opponent}${m.stage ? ` <span class="stage-tag">${m.stage}</span>` : ""}</div>
    <div class="result-meta">${fmtKickoff(m.kickoff)} · ${m.venue}, ${m.city}</div>
    ${links ? `<div class="result-articles">${links}</div>` : ""}`;
  return card;
}

function renderCollision(c) {
  document.getElementById("collision-summary").textContent = c.summary;
  const wrap = document.getElementById("collision-scenarios");
  for (const s of c.scenarios) {
    const row = document.createElement("div");
    row.className = `scenario scenario-${s.status || "open"}`;
    row.innerHTML = `
      <div>
        <div class="scenario-label">${s.label}</div>
        <div class="scenario-detail">${s.detail}</div>
      </div>
      <span class="scenario-meeting">${s.meeting}</span>`;
    wrap.appendChild(row);
  }
}

async function fetchWeather(matches) {
  const upcoming = matches.filter(m => !m.result);
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
