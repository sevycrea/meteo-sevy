/* =====================================================================
 *  COLLECTEUR STATION (Weather Underground) — module du service Node
 *  Port fidèle de auto_meteo_wunderground_hourly.py. Toutes les ~5 min :
 *  fetch la station WU → reconstruit meteo_data_hourly.json (90 j),
 *  meteo_data_realtime.json (48 h) et live.json → POST vers ingest.php
 *  (sur data.sevy-creations.net). Consommateurs (app/site/ML) inchangés.
 *
 *  État gardé EN MÉMOIRE (always-on) ; amorcé au boot depuis data.
 *  Clés temporelles en UTC (comme les runners GitHub d'origine).
 * ===================================================================== */
'use strict';
const fs = require('fs');

// ── Config (collector.json déposé à côté, chmod 600) ───────────────────────────
let CFG = {};
try { CFG = JSON.parse(fs.readFileSync(__dirname + '/collector.json', 'utf8')); }
catch { console.log('[collector] collector.json absent → collecteur OFF'); }
const WU_KEY    = CFG.wu_api_key || '';
const STATION   = CFG.station_id || 'IVINEL2';
const DATA_BASE = CFG.data_base  || 'https://data.sevy-creations.net';
const INGEST_URL = CFG.ingest_url || (DATA_BASE + '/ingest.php');
const INGEST_SECRET = CFG.ingest_secret || '';
const EVERY_MS = (CFG.every_min || 5) * 60 * 1000;
const REALTIME_HOURS = 48;
const KEEP_DAYS = 90;

const log = (m) => console.log(`[${new Date().toISOString()}] [collector] ${m}`);
const r1 = (x, n = 1) => Math.round(x * 10 ** n) / 10 ** n;
const isoZ = (d = new Date()) => d.toISOString().replace(/\.\d{3}Z$/, 'Z');

let _alertFn = null;
let _quotaAlertDate = '';

// Met à jour UN composant de health.json (lecture-modif-écriture pour PRÉSERVER
// les composants des autres producteurs, ex. `predictions` maintenu par GitHub).
const HEALTH_INTERVALS = { hourly: 15, daily: 15, alerts: 30, predictions: 360 };
async function markHealth(component, expectedMin) {
  try {
    const h = (await getJson(`${DATA_BASE}/health.json?t=${Date.now()}`, 2)) || {};
    h.components = h.components || {};
    h.components[component] = { last_run: isoZ(), status: 'ok',
      expected_interval_min: expectedMin || HEALTH_INTERVALS[component] || 30, age_min: 0, stale: false };
    const now = Date.now();
    const staleList = [];
    for (const [k, c] of Object.entries(h.components)) {
      const lr = Date.parse(c.last_run);
      c.age_min = lr ? Math.round((now - lr) / 60000) : 0;
      c.stale = c.age_min > (c.expected_interval_min || 30) * 2;
      if (c.stale) staleList.push(k);
    }
    h.generated_at = isoZ(); h.station = STATION; h.location = 'Vinelz, Suisse';
    h.stale_components = staleList; h.overall_status = staleList.length ? 'degraded' : 'ok';
    await post('health.json', h);
  } catch (e) { log(`health ${component}: ${e.message}`); }
}

// Bornes physiques plausibles (Vinelz) — hors bornes → null (sentinelles -999, etc.)
const BOUNDS = {
  temp: [-40, 50], humidity: [0, 100], wind_speed: [0, 200], wind_gust: [0, 250],
  pressure: [900, 1100], precip_rate: [0, 500], precip_total: [0, 500],
  dewpt: [-50, 40], wind_dir: [0, 360], uv: [0, 15], solar_radiation: [0, 1500],
};
function num(v, field) {
  if (v === null || v === undefined) return null;
  const x = Number(v);
  if (!Number.isFinite(x)) return null;
  const b = BOUNDS[field];
  if (b && (x < b[0] || x > b[1])) return null;
  return x;
}

// ── Horodatage UTC (comme datetime.now() sur les runners GitHub) ────────────────
const pad = (n) => String(n).padStart(2, '0');
function utcKeys(d = new Date()) {
  const Y = d.getUTCFullYear(), Mo = pad(d.getUTCMonth() + 1), D = pad(d.getUTCDate());
  const H = pad(d.getUTCHours()), Mi = pad(d.getUTCMinutes());
  return { date: `${Y}-${Mo}-${D}`, hour: `${H}:00`, min: `${Y}-${Mo}-${D} ${H}:${Mi}` };
}

// ── État en mémoire ─────────────────────────────────────────────────────────────
let hourly = {};     // meteo_data_hourly.json  { "YYYY-MM-DD": { hourly:{}, daily:{} } }
let realtime = {};   // meteo_data_realtime.json { "YYYY-MM-DD HH:MM": {...} }

// ── HTTP ─────────────────────────────────────────────────────────────────────────
async function getJson(url, attempts = 3, timeoutMs = 12000) {
  for (let i = 0; i < attempts; i++) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), timeoutMs);
      const res = await fetch(url, { signal: ctrl.signal });
      clearTimeout(t);
      if (res.ok) return await res.json();
    } catch { /* retry */ }
    if (i < attempts - 1) await new Promise((r) => setTimeout(r, 2000 * (i + 1)));
  }
  return null;
}
async function post(name, content) {
  if (process.env.COLLECTOR_DRYRUN) {   // test local : on écrit dans /tmp, aucun POST prod
    fs.writeFileSync('/tmp/collector_' + name, JSON.stringify(content, null, 1));
    log(`[DRYRUN] ${name} → /tmp/collector_${name}`);
    return;
  }
  if (!INGEST_SECRET) { log(`ingest non configuré — ${name} non envoyé`); return; }
  try {
    const res = await fetch(INGEST_URL, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ secret: INGEST_SECRET, name, content }),
    });
    if (!res.ok) log(`⚠️ ingest ${name} → HTTP ${res.status}`);
  } catch (e) { log(`⚠️ ingest ${name}: ${e.message}`); }
}

// ── WU : fetch avec détection quota (401/403/429 → erreur dédiée, pas de retry) ─
async function fetchWU(url) {
  for (let i = 0; i < 3; i++) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 10000);
      const res = await fetch(url, { signal: ctrl.signal });
      clearTimeout(t);
      if (res.ok) return await res.json();
      if (res.status === 401 || res.status === 403 || res.status === 429) {
        const e = new Error(`WU HTTP ${res.status}`); e.wuQuota = true; throw e;
      }
    } catch (e) { if (e.wuQuota) throw e; }
    if (i < 2) await new Promise((r) => setTimeout(r, 3000));
  }
  return null;
}

// ── WU : observation courante ───────────────────────────────────────────────────
async function fetchCurrent() {
  const url = `https://api.weather.com/v2/pws/observations/current?stationId=${STATION}&format=json&units=m&numericPrecision=decimal&apiKey=${WU_KEY}`;
  const data = await fetchWU(url);
  const obs = data && data.observations;
  return (obs && obs.length) ? obs[0] : null;
}
function extract(obs) {
  const m = obs.metric || {};
  return {
    temp: num(m.temp, 'temp'), humidity: num(obs.humidity, 'humidity'),
    wind_speed: num(m.windSpeed, 'wind_speed'), wind_gust: num(m.windGust, 'wind_gust'),
    pressure: num(m.pressure, 'pressure'), precip_rate: num(m.precipRate, 'precip_rate'),
    precip_total: num(m.precipTotal, 'precip_total'), dewpt: num(m.dewpt, 'dewpt'),
    wind_dir: num(obs.winddir, 'wind_dir'), uv: num(obs.uv, 'uv'),
    solar_radiation: num(obs.solarRadiation, 'solar_radiation'),
    timestamp: obs.obsTimeLocal || '',
  };
}

// ── meteo_data_hourly.json (snapshot HH:00 + agrégats daily) ────────────────────
function updateHourly(c) {
  const k = utcKeys();
  if (!hourly[k.date]) hourly[k.date] = { hourly: {}, daily: {} };
  const daily = hourly[k.date].daily;
  const disp = (key, def = 0) => (c[key] !== null && c[key] !== undefined ? c[key] : def);

  hourly[k.date].hourly[k.hour] = {
    temp: r1(disp('temp'), 1), hum: r1(disp('humidity'), 0), wind: r1(disp('wind_speed'), 1),
    gust: r1(disp('wind_gust'), 1), wind_dir: Math.trunc(disp('wind_dir')),
    pressure: r1(disp('pressure'), 1), rain: r1(disp('precip_total'), 1),
    rain_rate: c.precip_rate !== null ? r1(c.precip_rate, 1) : null,
    timestamp: c.timestamp || '',
  };
  if (c.temp !== null) {
    daily.temp_min = Math.min(daily.temp_min ?? c.temp, c.temp);
    daily.temp_max = Math.max(daily.temp_max ?? c.temp, c.temp);
    daily.temp_sum = (daily.temp_sum || 0) + c.temp;
    daily.temp_count = (daily.temp_count || 0) + 1;
    daily.temp_avg = r1(daily.temp_sum / daily.temp_count, 1);
  }
  if (c.precip_total !== null) daily.rain_total = Math.max(daily.rain_total ?? c.precip_total, c.precip_total);
  if (c.wind_gust !== null) daily.wind_max = Math.max(daily.wind_max ?? c.wind_gust, c.wind_gust);
  if (c.pressure !== null) {
    daily.pressure_sum = (daily.pressure_sum || 0) + c.pressure;
    daily.pressure_count = (daily.pressure_count || 0) + 1;
    daily.pressure_avg = r1(daily.pressure_sum / daily.pressure_count, 1);
  }
  if (c.humidity !== null) {
    daily.humidity_sum = (daily.humidity_sum || 0) + c.humidity;
    daily.humidity_count = (daily.humidity_count || 0) + 1;
    daily.humidity_avg = r1(daily.humidity_sum / daily.humidity_count, 0);
  }
}

// ── meteo_data_realtime.json (fenêtre glissante 48 h) ───────────────────────────
function updateRealtime(c) {
  const k = utcKeys();
  const rt = (f, n) => (c[f] !== null ? r1(c[f], n) : null);
  realtime[k.min] = {
    temp: rt('temp', 1), hum: rt('humidity', 0), wind: rt('wind_speed', 1),
    gust: rt('wind_gust', 1), wind_dir: c.wind_dir !== null ? Math.trunc(c.wind_dir) : null,
    pressure: rt('pressure', 1), rain: rt('precip_total', 1), rain_rate: rt('precip_rate', 1),
    timestamp: c.timestamp || '',
  };
  const cutoff = utcKeys(new Date(Date.now() - REALTIME_HOURS * 3600 * 1000)).min;
  for (const key of Object.keys(realtime)) if (key < cutoff) delete realtime[key];
}

// ── live.json (source unique header live app+site) ──────────────────────────────
function buildLive(c) {
  if (c.temp === null || c.pressure === null || c.humidity === null) return null;
  const n = (k, nd, def = null) => (c[k] !== null ? r1(c[k], nd) : def);
  const wind = c.wind_speed !== null ? r1(c.wind_speed, 1) : 0;
  const wdir = c.wind_dir !== null ? Math.trunc(c.wind_dir) : null;
  const rate = n('precip_rate', 1);
  const ts = c.timestamp || '';
  return { success: true, data: {
    ts, obsTimeLocal: ts, timestamp: ts,
    temp: r1(c.temp, 1), humidity: r1(c.humidity, 0), hum: r1(c.humidity, 0),
    windSpeed: wind, wind, windDir: wdir, wind_dir: wdir, pressure: r1(c.pressure, 1),
    gust: n('wind_gust', 1), rain: n('precip_total', 1), rain_rate: rate, rainRate: rate,
    precipRate: rate, precipTotal: n('precip_total', 1), uv: n('uv', 1),
    solar_radiation: n('solar_radiation', 1), solarRadiation: n('solar_radiation', 1),
    solar: n('solar_radiation', 1), dewpt: n('dewpt', 1),
  } };
}

// ── Enrichissement gust_max horaire (windgustHigh historique WU, 3 j UTC) ───────
async function enrichGustMax() {
  try {
    let observations = [];
    for (let off = 0; off < 3; off++) {
      const d = new Date(Date.now() - off * 86400000);
      const ds = `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`;
      const url = `https://api.weather.com/v2/pws/history/all?stationId=${STATION}&format=json&units=m&numericPrecision=decimal&date=${ds}&apiKey=${WU_KEY}`;
      const data = await getJson(url, 2, 30000);
      observations = observations.concat((data && data.observations) || []);
    }
    if (!observations.length) return;
    const buckets = {};
    for (const o of observations) {
      const epoch = o.epoch; let g = (o.metric || {}).windgustHigh;
      if (epoch == null || g == null) continue;
      g = Number(g); if (!Number.isFinite(g) || g < 0 || g > 250) continue;
      const dt = new Date(Number(epoch) * 1000);
      const key = `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}|${pad(dt.getUTCHours())}:00`;
      if (g > (buckets[key] ?? -1)) buckets[key] = g;
    }
    for (const [key, gmax] of Object.entries(buckets)) {
      const [dkey, hkey] = key.split('|');
      const h = hourly[dkey] && hourly[dkey].hourly;
      if (h && h[hkey]) h[hkey].gust_max = r1(gmax, 1);
    }
  } catch (e) { log(`gust_max: ${e.message}`); }
}

function cleanup() {
  const dates = Object.keys(hourly).sort();
  if (dates.length > KEEP_DAYS) for (const d of dates.slice(0, dates.length - KEEP_DAYS)) delete hourly[d];
}

// ── Amorçage au boot : on récupère l'état actuel publié (ne rien perdre) ────────
async function seed() {
  const h = await getJson(`${DATA_BASE}/meteo_data_hourly.json?t=${Date.now()}`, 2);
  if (h && typeof h === 'object') hourly = h;
  const rt = await getJson(`${DATA_BASE}/meteo_data_realtime.json?t=${Date.now()}`, 2);
  if (rt && typeof rt === 'object') realtime = rt;
  log(`amorcé : ${Object.keys(hourly).length} jours, ${Object.keys(realtime).length} pts realtime`);
}

// ── Cycle ────────────────────────────────────────────────────────────────────────
async function cycle() {
  try {
    const obs = await fetchCurrent();
    if (!obs) { log('WU inaccessible — cycle sauté'); return; }
    const c = extract(obs);
    if (c.temp === null && c.humidity === null && c.pressure === null) { log('obs WU vide — sautée'); return; }
    updateHourly(c);
    await enrichGustMax();
    updateRealtime(c);
    cleanup();
    await post('meteo_data_hourly.json', hourly);
    await post('meteo_data_realtime.json', realtime);
    const live = buildLive(c);
    if (live) await post('live.json', live);
    await markHealth('hourly', 15);
    log(`OK temp=${c.temp}°C  realtime=${Object.keys(realtime).length}pts`);
  } catch (e) {
    if (e.wuQuota) {
      log(`⚠️ Quota WU atteint (${e.message}) — collecte suspendue`);
      const today = new Date().toISOString().slice(0, 10);
      if (_alertFn && _quotaAlertDate !== today) {
        _quotaAlertDate = today;
        _alertFn('⚠️ Quota WU dépassé', 'La collecte météo station est suspendue. Elle reprend automatiquement à minuit UTC.', 'meteo-system');
      }
    } else { log(`cycle: ${e.message}`); }
  }
}

// ── Intervalle adaptatif : 5 min de 6h à 22h (heure Zurich), 30 min la nuit ─────
function localHour() {
  return parseInt(new Intl.DateTimeFormat('fr-CH', {
    timeZone: 'Europe/Zurich', hour: 'numeric', hour12: false,
  }).format(new Date()), 10);
}
function nextIntervalMs() {
  const h = localHour();
  return (h >= 6 && h < 22) ? 5 * 60 * 1000 : 30 * 60 * 1000;
}
function scheduleNext() {
  const ms = nextIntervalMs();
  log(`prochain cycle dans ${ms / 60000} min (${localHour()}h locale)`);
  setTimeout(() => cycle().then(scheduleNext), ms);
}

// ── Démarrage du collecteur ──────────────────────────────────────────────────────
function start(opts = {}) {
  _alertFn = opts.alertFn || null;
  if (!WU_KEY || !INGEST_SECRET) { log('clé WU ou secret ingest manquant → collecteur NON démarré'); return; }
  log(`démarrage (station ${STATION}, cycle adaptatif 5 min jour / 30 min nuit)`);
  seed().then(() => cycle().then(scheduleNext));
}

module.exports = { start, markHealth };
