/* =====================================================================
 *  LISTENER FOUDRE BLITZORTUNG + PUSH APNs  —  Node.js always-on
 *  - écoute Blitzortung en continu, sert lightning.json + strikes.json,
 *  - envoie des PUSH APNs : orage ≤10 km (temps réel, données en mémoire)
 *    et alertes météo (alerts.json). Tout en HTTP/2 natif, zéro dépendance.
 * ===================================================================== */
'use strict';

// ╔══════════════ CONFIG (tout ce qui peut changer) ══════════════╗
const VINELZ      = { lat: 47.0552, lon: 7.1248 };
const RADIUS_KM   = 30;            // rayon "proche" pour lightning.json
const NEAR_WINDOW_S = 30 * 60;     // fenêtre éclairs proches (30 min)
const REGION = { lat_min: 35.0, lat_max: 55.5, lon_min: -5.5, lon_max: 19.0 };
const STRIKES_MAX_AGE_S = 60 * 60; // fenêtre strikes.json (60 min)
const STRIKES_MAX       = 8000;
const MAINTAIN_EVERY_MS = 30 * 1000;
const PUSH_EVERY_MS     = 30 * 1000;   // fréquence de vérif des événements à pusher
const STORM_PUSH_KM     = 10;          // seuil d'alerte orage (km)
const ALERTS_URL        = 'https://data.sevy-creations.net/alerts.json';
const BO_SERVERS = [1, 2, 3, 7, 8];
const RECONNECT_MAX_MS = 30 * 1000;
const HTTP_PORT = process.env.PORT || 3000;

// ╔══════════════ Imports (tout natif Node 24) ══════════════╗
const http  = require('http');
const fs    = require('fs');
const crypto = require('crypto');
const http2 = require('http2');
const community = require('./community'); // 🏍️ Communauté MotoWeather — lieux + virées partagés (/community/*)

// Config push APNs (apns.json déposé à côté, chmod 600, non servi par le web)
let APNS = null;
try { APNS = JSON.parse(fs.readFileSync(__dirname + '/apns.json', 'utf8')); }
catch { /* pas de config → push désactivé proprement */ }
const TOKENS_FILE = __dirname + '/push_tokens.json';
let pushTokens = [];
try { pushTokens = JSON.parse(fs.readFileSync(TOKENS_FILE, 'utf8')); } catch {}
function saveTokens() { try { fs.writeFileSync(TOKENS_FILE, JSON.stringify(pushTokens)); } catch (e) { log('save tokens: ' + e.message); } }

// ╔══════════════ État en mémoire ══════════════╗
let near = [];            // { epoch, dist } proches de Vinelz
let region = [];          // [epoch, lat, lon] régionaux
let prevNearest = null;   // pour 'trend'
let connected = false;
let totalStrikes = 0;
let wasStormNear = false; // front montant orage
let wasRaining = false;   // front montant pluie
let seenAlertIds = null;  // ids d'alertes déjà vues (null = pas encore amorcé)

// ╔══════════════ Utilitaires ══════════════╗
function log(m) { console.log(`[${new Date().toISOString()}] ${m}`); }
function iso(d) { return d.toISOString().replace(/\.\d{3}Z$/, 'Z'); }
const round1 = (x) => Math.round(x * 10) / 10;
const round4 = (x) => Math.round(x * 1e4) / 1e4;

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180;
  const dphi = (lat2 - lat1) * Math.PI / 180, dl = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

// Décompresseur LZW "maison" de Blitzortung → texte JSON
function boDecode(s) {
  if (!s) return s;
  const dict = {}; let g = s[0], f = g, out = g, p = 256;
  for (let i = 1; i < s.length; i++) {
    const cc = s.charCodeAt(i);
    const a = (cc < 256) ? s[i] : (dict[cc] !== undefined ? dict[cc] : (g + f));
    out += a; f = a[0]; dict[p++] = g + f; g = a;
  }
  return out;
}
function parseMessage(raw) {
  const text = (typeof raw === 'string') ? raw : Buffer.from(raw).toString('utf8');
  try { return JSON.parse(text); }
  catch { try { return JSON.parse(boDecode(text)); } catch { return null; } }
}

// ╔══════════════ Réception éclair + purge ══════════════╗
function handleStrike(raw) {
  const obj = parseMessage(raw);
  if (!obj || obj.lat == null || obj.lon == null) return;
  const lat = Number(obj.lat), lon = Number(obj.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
  totalStrikes++;
  const epoch = obj.time ? (obj.time / 1e9) : (Date.now() / 1000);
  if (lat >= REGION.lat_min && lat <= REGION.lat_max && lon >= REGION.lon_min && lon <= REGION.lon_max)
    region.push([Math.round(epoch), round4(lat), round4(lon)]);
  const d = haversineKm(VINELZ.lat, VINELZ.lon, lat, lon);
  if (d <= RADIUS_KM) near.push({ epoch, dist: d });
}
function prune() {
  const now = Date.now() / 1000;
  near   = near.filter((s) => s.epoch >= now - NEAR_WINDOW_S);
  region = region.filter((s) => s[0] >= now - STRIKES_MAX_AGE_S);
  if (region.length > STRIKES_MAX) region = region.slice(-STRIKES_MAX);
}

// ╔══════════════ JSON servis ══════════════╗
function buildLightning() {
  prune();
  const nowIso = iso(new Date());
  if (near.length === 0)
    return { generated_at: nowIso, status: 'calme', severity: 'none', nearest_km: null,
             strike_count: 0, window_min: NEAR_WINDOW_S / 60, trend: null, last_strike_at: null };
  const nearest = round1(Math.min(...near.map((s) => s.dist)));
  const lastEp  = Math.max(...near.map((s) => s.epoch));
  const severity = nearest < 10 ? 'critical' : nearest < 20 ? 'warning' : 'info';
  let trend = null;
  if (typeof prevNearest === 'number')
    trend = nearest < prevNearest - 2 ? 'approche' : nearest > prevNearest + 2 ? 'eloigne' : 'stable';
  return { generated_at: nowIso, status: 'orage', severity, nearest_km: nearest,
           strike_count: near.length, window_min: NEAR_WINDOW_S / 60, trend,
           last_strike_at: iso(new Date(lastEp * 1000)) };
}
function buildStrikes() {
  prune();
  return { generated_at: iso(new Date()), region, window_min: STRIKES_MAX_AGE_S / 60,
           count: region.length, strikes: region };
}
function maintain() { prevNearest = buildLightning().nearest_km; }

// ╔══════════════ APNs (JWT ES256 + HTTP/2) ══════════════╗
function b64url(x) {
  return (Buffer.isBuffer(x) ? x : Buffer.from(x)).toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
let _jwt = null, _jwtAt = 0;
function apnsJwt() {
  if (_jwt && Date.now() - _jwtAt < 50 * 60 * 1000) return _jwt;   // jeton réutilisé < 50 min
  const h = b64url(JSON.stringify({ alg: 'ES256', kid: APNS.keyId }));
  const c = b64url(JSON.stringify({ iss: APNS.teamId, iat: Math.floor(Date.now() / 1000) }));
  const input = `${h}.${c}`;
  const key = fs.readFileSync(__dirname + '/' + APNS.p8File);
  // dsaEncoding 'ieee-p1363' → signature brute R||S de 64 octets (format exigé par APNs)
  const sig = crypto.sign('sha256', Buffer.from(input), { key, dsaEncoding: 'ieee-p1363' });
  _jwt = `${input}.${b64url(sig)}`; _jwtAt = Date.now();
  return _jwt;
}
function sendPush(token, payload) {
  return new Promise((resolve) => {
    const host = APNS.production ? 'https://api.push.apple.com' : 'https://api.sandbox.push.apple.com';
    let client;
    try { client = http2.connect(host); } catch (e) { return resolve({ code: 0, body: e.message }); }
    client.on('error', (e) => resolve({ code: 0, body: e.message }));
    const req = client.request({
      ':method': 'POST', ':path': `/3/device/${token}`,
      'authorization': `bearer ${apnsJwt()}`, 'apns-topic': APNS.bundleId,
      'apns-push-type': 'alert', 'apns-priority': '10', 'content-type': 'application/json',
    });
    let status = 0, body = '';
    req.on('response', (hh) => { status = hh[':status']; });
    req.on('data', (d) => body += d);
    req.on('end', () => { try { client.close(); } catch {} resolve({ code: status, body }); });
    req.setTimeout(15000, () => { try { req.close(); client.close(); } catch {} resolve({ code: 0, body: 'timeout' }); });
    req.end(JSON.stringify(payload));
  });
}
async function notifyAll(title, body, thread) {
  if (!APNS) { log('push: APNs non configuré'); return; }
  if (pushTokens.length === 0) { log(`push « ${title} » mais aucun token enregistré`); return; }
  const payload = { aps: { alert: { title, body }, sound: 'default', 'thread-id': thread } };
  for (const tok of [...pushTokens]) {
    const r = await sendPush(tok, payload);
    if (r.code === 200) log(`✅ push « ${title} » → ${tok.slice(0, 8)}…`);
    else if (r.code === 410 || (r.code === 400 && /BadDeviceToken/.test(r.body || ''))) {
      pushTokens = pushTokens.filter((t) => t !== tok); saveTokens();
      log(`🗑️ token mort ${tok.slice(0, 8)}… (code ${r.code})`);
    } else log(`⚠️ APNs ${r.code}: ${(r.body || '').slice(0, 140)}`);
  }
}

// ╔══════════════ Détection d'événements à pusher ══════════════╗
async function checkStorm() {                       // ORAGE — données en mémoire (temps réel)
  const l = buildLightning();
  const nearNow = l.status === 'orage' && l.nearest_km != null && l.nearest_km <= STORM_PUSH_KM;
  if (nearNow && !wasStormNear) {                    // front montant uniquement
    let b = `Foudre détectée à ${Math.round(l.nearest_km)} km.`;
    if (l.trend === 'approche') b += " L'orage se rapproche.";
    await notifyAll('⚡ Orage proche de Vinelz', b, 'meteo-sevy-storm');
  }
  wasStormNear = nearNow;
}
async function checkAlerts() {                       // ALERTES MÉTÉO — alerts.json
  let bundle;
  try { const r = await fetch(`${ALERTS_URL}?t=${Date.now()}`); if (!r.ok) return; bundle = await r.json(); }
  catch { return; }
  const alerts = bundle.alerts || [];
  const ids = alerts.map((a) => a.detected_at);
  if (seenAlertIds === null) { seenAlertIds = new Set(ids); return; }  // 1er passage : amorçage sans push
  for (const a of alerts) {
    if (!a.detected_at || seenAlertIds.has(a.detected_at)) continue;
    const sev = a.severity || 'info';
    const title = sev === 'critical' ? '⚠️ Alerte critique' : sev === 'warning' ? '⚠️ Alerte météo' : 'ℹ️ Info météo';
    await notifyAll(title, a.message || '', 'meteo-sevy-alerts');
  }
  seenAlertIds = new Set(ids);
}
async function checkRain() {                          // PLUIE — meteo_data_realtime.json (station)
  let d;
  try { const r = await fetch(`https://data.sevy-creations.net/meteo_data_realtime.json?t=${Date.now()}`); if (!r.ok) return; d = await r.json(); }
  catch { return; }
  // Clés "YYYY-MM-DD HH:MM" en UTC (écrites par le collecteur Node) → epoch ms
  const pts = Object.entries(d).map(([k, v]) => ({
    t: Date.parse(k.replace(' ', 'T') + ':00Z'), rain: v.rain, rate: v.rain_rate,
  })).filter((p) => Number.isFinite(p.t)).sort((a, b) => a.t - b.t);
  const n = pts.length;
  let isRaining = false;
  if (n >= 1 && (Date.now() - pts[n - 1].t) < 30 * 60 * 1000) {     // dernier relevé < 30 min
    // pluie = cumul qui monte (precipTotal du jour) OU taux franc ≥ 0,5 mm/h
    const accum = n >= 2 && ((pts[n - 1].rain ?? 0) - (pts[n - 2].rain ?? 0) > 0);
    const strong = (pts[n - 1].rate ?? 0) >= 0.5;
    isRaining = accum || strong;
  }
  if (isRaining && !wasRaining) {                    // front montant uniquement
    const total = pts[n - 1].rain;
    const body = (total != null)
      ? `La station relève de la pluie en ce moment (${total} mm aujourd'hui).`
      : 'La station de Vinelz détecte de la pluie en ce moment.';
    await notifyAll('🌧️ Il pleut à Vinelz', body, 'meteo-sevy-rain');
  }
  wasRaining = isRaining;
}

async function checkPush() {
  try { await checkStorm(); }  catch (e) { log('checkStorm: ' + e.message); }
  try { await checkRain(); }   catch (e) { log('checkRain: ' + e.message); }
  try { await checkAlerts(); } catch (e) { log('checkAlerts: ' + e.message); }
}

// ╔══════════════ WebSocket Blitzortung + reconnexion ══════════════╗
let ws = null, serverIdx = 0, backoff = 1000;
function connect() {
  const sid = BO_SERVERS[serverIdx % BO_SERVERS.length]; serverIdx++;
  const url = `wss://ws${sid}.blitzortung.org/`;
  log(`connexion à ${url} …`);
  ws = new WebSocket(url);
  ws.onopen = () => { connected = true; backoff = 1000; ws.send(JSON.stringify({ a: 111 })); log(`✅ connecté à ${url}`); };
  ws.onmessage = (ev) => handleStrike(ev.data);
  ws.onerror = () => { try { ws.close(); } catch {} };
  ws.onclose = () => {
    connected = false;
    log(`déconnecté — reconnexion dans ${backoff / 1000}s`);
    setTimeout(connect, backoff);
    backoff = Math.min(backoff * 2, RECONNECT_MAX_MS);
  };
}

// ╔══════════════ Relais jeu Abalone (salons, tour par tour) ══════════════╗
// Greffé ici sous /abalone/* — n'interfère avec AUCUNE route météo. Zéro dépendance.
const ABALONE_ROOMS = new Map();
const ABALONE_TTL_MS = 2 * 60 * 60 * 1000;
const ABALONE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
function abaloneCode() {
  let c = '';
  for (let i = 0; i < 4; i++) c += ABALONE_ALPHABET[Math.floor(Math.random() * ABALONE_ALPHABET.length)];
  return ABALONE_ROOMS.has(c) ? abaloneCode() : c;
}
function abaloneSend(res, status, obj) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Cache-Control': 'no-store',
  });
  res.end(JSON.stringify(obj));
}
function abaloneBody(req) {
  return new Promise((resolve) => {
    let d = ''; req.on('data', (c) => { d += c; if (d.length > 1e6) req.destroy(); });
    req.on('end', () => { try { resolve(d ? JSON.parse(d) : {}); } catch { resolve(null); } });
    req.on('error', () => resolve(null));
  });
}
async function abaloneHandle(req, res, url) {
  const p = url.pathname;
  if (req.method === 'OPTIONS') return abaloneSend(res, 204, {});
  if (req.method === 'GET' && (p === '/abalone' || p === '/abalone/'))
    return abaloneSend(res, 200, { ok: true, service: 'abalone-relay', rooms: ABALONE_ROOMS.size });
  if (req.method === 'POST' && p === '/abalone/create') {
    const b = await abaloneBody(req); if (!b) return abaloneSend(res, 400, { ok: false, error: 'bad_json' });
    const code = abaloneCode();
    ABALONE_ROOMS.set(code, { variant: b.variant === 'echos' ? 'echos' : 'classic', roles: Array.isArray(b.roles) ? b.roles : [], moves: [], chat: [], guest: false, started: false, ts: Date.now() });
    return abaloneSend(res, 200, { ok: true, code, color: 'B' });
  }
  if (req.method === 'POST' && p === '/abalone/join') {
    const b = await abaloneBody(req); if (!b || !b.code) return abaloneSend(res, 400, { ok: false, error: 'bad_json' });
    const room = ABALONE_ROOMS.get(String(b.code).toUpperCase());
    if (!room) return abaloneSend(res, 404, { ok: false, error: 'not_found' });
    if (room.guest) return abaloneSend(res, 409, { ok: false, error: 'full' });
    room.guest = true; room.started = true; room.ts = Date.now();
    return abaloneSend(res, 200, { ok: true, color: 'W', variant: room.variant, roles: room.roles });
  }
  if (req.method === 'POST' && p === '/abalone/move') {
    const b = await abaloneBody(req); if (!b || !b.code || !b.move) return abaloneSend(res, 400, { ok: false, error: 'bad_json' });
    const room = ABALONE_ROOMS.get(String(b.code).toUpperCase());
    if (!room) return abaloneSend(res, 404, { ok: false, error: 'not_found' });
    room.moves.push({ color: b.color, move: b.move }); room.ts = Date.now();
    return abaloneSend(res, 200, { ok: true, seq: room.moves.length });
  }
  if (req.method === 'GET' && p === '/abalone/sync') {
    const code = String(url.searchParams.get('code') || '').toUpperCase();
    const since = parseInt(url.searchParams.get('since') || '0', 10) || 0;
    const room = ABALONE_ROOMS.get(code);
    if (!room) return abaloneSend(res, 404, { ok: false, error: 'not_found' });
    room.ts = Date.now();
    return abaloneSend(res, 200, { ok: true, started: room.started, guest: room.guest, variant: room.variant, roles: room.roles, total: room.moves.length, moves: room.moves.slice(since), chat: room.chat });
  }
  if (req.method === 'POST' && p === '/abalone/chat') {
    const b = await abaloneBody(req);
    if (!b || !b.code || typeof b.text !== 'string') return abaloneSend(res, 400, { ok: false, error: 'bad_json' });
    const room = ABALONE_ROOMS.get(String(b.code).toUpperCase());
    if (!room) return abaloneSend(res, 404, { ok: false, error: 'not_found' });
    const text = b.text.slice(0, 300);
    if (text.trim()) {
      room.chat.push({ from: b.color === 'W' ? 'W' : 'B', text, ts: Date.now() });
      if (room.chat.length > 100) room.chat = room.chat.slice(-100);
    }
    room.ts = Date.now();
    return abaloneSend(res, 200, { ok: true, count: room.chat.length });
  }
  if (req.method === 'POST' && p === '/abalone/leave') {
    const b = await abaloneBody(req); if (b && b.code) ABALONE_ROOMS.delete(String(b.code).toUpperCase());
    return abaloneSend(res, 200, { ok: true });
  }
  return abaloneSend(res, 404, { ok: false, error: 'unknown_route' });
}
setInterval(() => {
  const now = Date.now();
  for (const [c, r] of ABALONE_ROOMS) if (now - r.ts > ABALONE_TTL_MS) ABALONE_ROOMS.delete(c);
}, 5 * 60 * 1000);

// ╔══════════════ Nous2 : messagerie privée à 2 (texte ; médias/push ajoutés ensuite) ══════════════╗
// Greffé sous /msg/* — clé privée + persistance fichier. Isolé du reste.
const NOUS2_KEY = 'N2-4f9a7c2e8b1d6a3f-prive';
const NOUS2_FILE = __dirname + '/nous2.json';
let nous2 = { msgs: [] };
try { nous2 = JSON.parse(fs.readFileSync(NOUS2_FILE, 'utf8')); } catch { /* premier lancement */ }
if (!Array.isArray(nous2.msgs)) nous2.msgs = [];
if (!Array.isArray(nous2.deleted)) nous2.deleted = []; // ids supprimés (tombstones, pour synchro)
if (typeof nous2.epoch !== 'number') nous2.epoch = 0;  // bumpé à chaque « vider »
let nous2Seq = nous2.msgs.length ? nous2.msgs[nous2.msgs.length - 1].id : 0;
function nous2Save() { try { fs.writeFileSync(NOUS2_FILE, JSON.stringify(nous2)); } catch (e) { log('nous2 save: ' + e.message); } }

// Médias : stockés sur disque sous nous2_media/<id>.<ext>. Plafonds : photo 5 Mo, vidéo 15 Mo.
const NOUS2_MEDIA_DIR = __dirname + '/nous2_media';
try { fs.mkdirSync(NOUS2_MEDIA_DIR, { recursive: true }); } catch (e) { log('nous2 media dir: ' + e.message); }
const NOUS2_TYPES = {
  jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', heic: 'image/heic',
  gif: 'image/gif', webp: 'image/webp',
  mp4: 'video/mp4', mov: 'video/quicktime', m4v: 'video/x-m4v', webm: 'video/webm',
  bin: 'application/octet-stream', // médias chiffrés de bout en bout (octets bruts)
};
const NOUS2_VIDEO_EXT = new Set(['mp4', 'mov', 'm4v', 'webm', 'bin']);
const NOUS2_PHOTO_MAX = 5 * 1024 * 1024;
const NOUS2_VIDEO_MAX = 15 * 1024 * 1024;
const NOUS2_TEXT_MAX = 12000; // texte chiffré (base64) plus long que le clair

// Tokens push (E2E : le serveur ne lit pas le contenu, il notifie juste « l'autre »).
const NOUS2_TOKENS_FILE = __dirname + '/nous2_tokens.json';
let nous2Tokens = []; // [{ name, token, ts }]
try { nous2Tokens = JSON.parse(fs.readFileSync(NOUS2_TOKENS_FILE, 'utf8')); } catch {}
if (!Array.isArray(nous2Tokens)) nous2Tokens = [];
function nous2TokensSave() { try { fs.writeFileSync(NOUS2_TOKENS_FILE, JSON.stringify(nous2Tokens)); } catch (e) { log('nous2 tokens save: ' + e.message); } }

// Push Nous2 : réutilise apnsJwt() (clé team-wide) mais avec le topic Nous2 + sandbox (builds par câble).
const NOUS2_BUNDLE = 'net.sevycreations.nous2';
const NOUS2_APNS_SANDBOX = true; // installs par câble = environnement développement
function nous2Push(token, payload) {
  return new Promise((resolve) => {
    const host = NOUS2_APNS_SANDBOX ? 'https://api.sandbox.push.apple.com' : 'https://api.push.apple.com';
    let client;
    try { client = http2.connect(host); } catch (e) { return resolve({ code: 0, body: e.message }); }
    client.on('error', (e) => resolve({ code: 0, body: e.message }));
    const req = client.request({
      ':method': 'POST', ':path': `/3/device/${token}`,
      'authorization': `bearer ${apnsJwt()}`, 'apns-topic': NOUS2_BUNDLE,
      'apns-push-type': 'alert', 'apns-priority': '10', 'content-type': 'application/json',
    });
    let status = 0, body = '';
    req.on('response', (hh) => { status = hh[':status']; });
    req.on('data', (d) => body += d);
    req.on('end', () => { try { client.close(); } catch {} resolve({ code: status, body }); });
    req.setTimeout(15000, () => { try { req.close(); client.close(); } catch {} resolve({ code: 0, body: 'timeout' }); });
    req.end(JSON.stringify(payload));
  });
}
// Notifie tous les appareils SAUF ceux de l'expéditeur (par prénom). Contenu jamais révélé (E2E).
async function nous2NotifyOthers(from, urgent) {
  if (!APNS) return;
  const targets = nous2Tokens.filter((t) => t.name !== from);
  if (!targets.length) return;
  const payload = urgent
    ? { aps: { alert: { title: `🚨 URGENT — ${from}`, body: 'Message urgent 💞' }, sound: 'urgent.wav', badge: 1, 'interruption-level': 'time-sensitive', 'relevance-score': 1, 'thread-id': 'nous2' } }
    : { aps: { alert: { title: 'Nous2 💞', body: `Nouveau message de ${from}` }, sound: 'default', badge: 1, 'thread-id': 'nous2' } };
  for (const t of [...targets]) {
    const r = await nous2Push(t.token, payload);
    if (r.code === 200) log(`✅ nous2 push → ${t.name} ${t.token.slice(0, 8)}…`);
    else if (r.code === 410 || (r.code === 400 && /BadDeviceToken/.test(r.body || ''))) {
      nous2Tokens = nous2Tokens.filter((x) => x.token !== t.token); nous2TokensSave();
      log(`🗑️ nous2 token mort ${t.token.slice(0, 8)}… (code ${r.code})`);
    } else log(`⚠️ nous2 APNs ${r.code}: ${(r.body || '').slice(0, 140)}`);
  }
}
const NOUS2_ID_RE = /^[a-z0-9]+\.[a-z0-9]+$/; // <id>.<ext>, anti path-traversal
let nous2MediaCtr = 0;
function nous2MediaId(ext) {
  return (Date.now().toString(36) + (++nous2MediaCtr).toString(36) + Math.floor(Math.random() * 1e6).toString(36)) + '.' + ext;
}
// Lecteur de body à grande capacité (uploads base64) — abaloneBody plafonne à 1 Mo.
function nous2BigBody(req, max) {
  return new Promise((resolve) => {
    let d = ''; let killed = false;
    req.on('data', (c) => { d += c; if (d.length > max) { killed = true; req.destroy(); } });
    req.on('end', () => { if (killed) return resolve(null); try { resolve(d ? JSON.parse(d) : {}); } catch { resolve(null); } });
    req.on('error', () => resolve(null));
  });
}

async function nous2Handle(req, res, url) {
  const p = url.pathname;
  if (req.method === 'OPTIONS') return abaloneSend(res, 204, {});
  if (req.method === 'GET' && (p === '/msg' || p === '/msg/'))
    return abaloneSend(res, 200, { ok: true, service: 'nous2', count: nous2.msgs.length });

  // Upload d'un média (base64) -> écrit le fichier, renvoie le mediaId (<id>.<ext>).
  if (req.method === 'POST' && p === '/msg/upload') {
    const b = await nous2BigBody(req, NOUS2_VIDEO_MAX * 2); // marge base64 (~+33 %) + JSON
    if (b === null) return abaloneSend(res, 413, { ok: false, error: 'too_big' });
    if (b.key !== NOUS2_KEY) return abaloneSend(res, 403, { ok: false, error: 'forbidden' });
    const ext = String(b.ext || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    if (!NOUS2_TYPES[ext]) return abaloneSend(res, 400, { ok: false, error: 'bad_ext' });
    if (typeof b.data !== 'string' || !b.data) return abaloneSend(res, 400, { ok: false, error: 'no_data' });
    const buf = Buffer.from(b.data, 'base64');
    if (!buf.length) return abaloneSend(res, 400, { ok: false, error: 'bad_data' });
    const max = NOUS2_VIDEO_EXT.has(ext) ? NOUS2_VIDEO_MAX : NOUS2_PHOTO_MAX;
    if (buf.length > max) return abaloneSend(res, 413, { ok: false, error: 'too_big' });
    const mediaId = nous2MediaId(ext);
    try { fs.writeFileSync(NOUS2_MEDIA_DIR + '/' + mediaId, buf); }
    catch (e) { log('nous2 upload: ' + e.message); return abaloneSend(res, 500, { ok: false, error: 'write_failed' }); }
    return abaloneSend(res, 200, { ok: true, mediaId });
  }

  // Service d'un média (URL non devinable ; pas de clé pour rester compatible <Image>/<Video>).
  if (req.method === 'GET' && p.startsWith('/msg/media/')) {
    const id = decodeURIComponent(p.slice('/msg/media/'.length));
    if (!NOUS2_ID_RE.test(id)) return abaloneSend(res, 400, { ok: false, error: 'bad_id' });
    const ct = NOUS2_TYPES[id.split('.').pop()];
    if (!ct) return abaloneSend(res, 400, { ok: false, error: 'bad_ext' });
    let data;
    try { data = fs.readFileSync(NOUS2_MEDIA_DIR + '/' + id); }
    catch { return abaloneSend(res, 404, { ok: false, error: 'not_found' }); }
    res.writeHead(200, {
      'Content-Type': ct,
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': 'public, max-age=31536000, immutable',
      'Content-Length': data.length,
    });
    return res.end(data);
  }

  // Enregistrement d'un token push (par appareil).
  if (req.method === 'POST' && p === '/msg/register') {
    const b = await abaloneBody(req);
    if (!b || b.key !== NOUS2_KEY) return abaloneSend(res, 403, { ok: false, error: 'forbidden' });
    const name = String(b.name || '?').slice(0, 40);
    const token = typeof b.token === 'string' ? b.token.replace(/[^a-fA-F0-9]/g, '') : '';
    if (token.length < 32 || token.length > 200) return abaloneSend(res, 400, { ok: false, error: 'bad_token' });
    nous2Tokens = nous2Tokens.filter((t) => t.token !== token); // upsert par token
    nous2Tokens.push({ name, token, ts: Date.now() });
    if (nous2Tokens.length > 50) nous2Tokens = nous2Tokens.slice(-50);
    nous2TokensSave();
    return abaloneSend(res, 200, { ok: true });
  }

  if (req.method === 'POST' && p === '/msg/send') {
    const b = await abaloneBody(req);
    if (!b || b.key !== NOUS2_KEY) return abaloneSend(res, 403, { ok: false, error: 'forbidden' });
    const from = String(b.from || '?').slice(0, 40);
    const type = b.type === 'image' || b.type === 'video' ? b.type : 'text';
    const urgent = b.urgent === true;
    let msg;
    if (type === 'text') {
      const text = typeof b.text === 'string' ? b.text.slice(0, NOUS2_TEXT_MAX) : '';
      if (!text.trim()) return abaloneSend(res, 400, { ok: false, error: 'empty' });
      msg = { id: ++nous2Seq, from, type: 'text', text, ts: Date.now() };
    } else {
      const mediaId = typeof b.mediaId === 'string' ? b.mediaId : '';
      if (!NOUS2_ID_RE.test(mediaId)) return abaloneSend(res, 400, { ok: false, error: 'bad_media' });
      msg = { id: ++nous2Seq, from, type, mediaId, ts: Date.now() };
      const cap = typeof b.text === 'string' ? b.text.slice(0, NOUS2_TEXT_MAX) : '';
      if (cap.trim()) msg.text = cap; // légende facultative (chiffrée)
    }
    if (urgent) msg.urgent = true;
    nous2.msgs.push(msg);
    if (nous2.msgs.length > 1000) nous2.msgs = nous2.msgs.slice(-1000);
    nous2Save();
    nous2NotifyOthers(from, urgent).catch((e) => log('nous2 notify: ' + e.message)); // sans bloquer la réponse
    return abaloneSend(res, 200, { ok: true, id: msg.id });
  }

  // Suppression d'un message (pour les deux). Tombstone pour la synchro.
  if (req.method === 'POST' && p === '/msg/delete') {
    const b = await abaloneBody(req);
    if (!b || b.key !== NOUS2_KEY) return abaloneSend(res, 403, { ok: false, error: 'forbidden' });
    const id = parseInt(b.id, 10);
    if (!id) return abaloneSend(res, 400, { ok: false, error: 'bad_id' });
    const m = nous2.msgs.find((x) => x.id === id);
    if (m) {
      nous2.msgs = nous2.msgs.filter((x) => x.id !== id);
      if (m.mediaId && NOUS2_ID_RE.test(m.mediaId)) { try { fs.unlinkSync(NOUS2_MEDIA_DIR + '/' + m.mediaId); } catch {} }
      nous2.deleted.push(id);
      if (nous2.deleted.length > 2000) nous2.deleted = nous2.deleted.slice(-2000);
      nous2Save();
    }
    return abaloneSend(res, 200, { ok: true });
  }

  // Accusés de réception / lecture. On n'accuse QUE les messages reçus (from !== moi).
  // delivered = l'autre appareil a récupéré le message ; read = il l'a affiché au premier plan.
  if (req.method === 'POST' && p === '/msg/ack') {
    const b = await abaloneBody(req);
    if (!b || b.key !== NOUS2_KEY) return abaloneSend(res, 403, { ok: false, error: 'forbidden' });
    const from = String(b.from || '?').slice(0, 40);
    const state = b.state === 'read' ? 'read' : 'delivered';
    const ids = Array.isArray(b.ids) ? b.ids.map((x) => parseInt(x, 10)).filter(Boolean).slice(0, 500) : [];
    if (!ids.length) return abaloneSend(res, 200, { ok: true });
    const want = new Set(ids);
    const now = Date.now();
    let changed = false;
    for (const m of nous2.msgs) {
      if (!want.has(m.id) || m.from === from) continue; // jamais accuser ses propres messages
      if (!m.delivered) { m.delivered = now; changed = true; }
      if (state === 'read' && !m.read) { m.read = now; changed = true; }
    }
    if (changed) nous2Save();
    return abaloneSend(res, 200, { ok: true });
  }

  // Vider toute la conversation (pour les deux). Bumpe l'epoch -> reset chez les clients.
  if (req.method === 'POST' && p === '/msg/clear') {
    const b = await abaloneBody(req);
    if (!b || b.key !== NOUS2_KEY) return abaloneSend(res, 403, { ok: false, error: 'forbidden' });
    for (const m of nous2.msgs) {
      if (m.mediaId && NOUS2_ID_RE.test(m.mediaId)) { try { fs.unlinkSync(NOUS2_MEDIA_DIR + '/' + m.mediaId); } catch {} }
    }
    nous2.msgs = [];
    nous2.deleted = [];
    nous2.epoch = (nous2.epoch || 0) + 1;
    nous2Save();
    return abaloneSend(res, 200, { ok: true, epoch: nous2.epoch });
  }

  if (req.method === 'GET' && p === '/msg/list') {
    if (url.searchParams.get('key') !== NOUS2_KEY) return abaloneSend(res, 403, { ok: false, error: 'forbidden' });
    const since = parseInt(url.searchParams.get('since') || '0', 10) || 0;
    const cliEpoch = parseInt(url.searchParams.get('epoch') || '0', 10) || 0;
    // Si l'epoch a changé (conversation vidée), on renvoie tout et le client réinitialise.
    if (cliEpoch !== nous2.epoch) {
      return abaloneSend(res, 200, { ok: true, reset: true, epoch: nous2.epoch, last: nous2Seq, msgs: nous2.msgs, deleted: [] });
    }
    // Accusés des messages récents (les seuls qui comptent) — compact : {i:id, d:delivered, r:read}.
    const acks = [];
    for (const m of nous2.msgs.slice(-80)) {
      if (m.delivered || m.read) acks.push({ i: m.id, d: m.delivered || 0, r: m.read || 0 });
    }
    return abaloneSend(res, 200, { ok: true, reset: false, epoch: nous2.epoch, last: nous2Seq, msgs: nous2.msgs.filter((m) => m.id > since), deleted: nous2.deleted, acks });
  }

  return abaloneSend(res, 404, { ok: false, error: 'unknown' });
}

// ╔══════════════ Serveur HTTP ══════════════╗
const JSON_HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store',
};
http.createServer((req, res) => {
  // Relais jeu Abalone (isolé sous /abalone/*) — passe avant tout le reste
  if (req.url.startsWith('/abalone')) {
    return abaloneHandle(req, res, new URL(req.url, 'http://x'));
  }
  // Messagerie privée Nous2 (isolée sous /msg/*)
  if (req.url.startsWith('/msg')) {
    return nous2Handle(req, res, new URL(req.url, 'http://x'));
  }
  // Communauté MotoWeather (lieux + virées partagés, isolée sous /community/*)
  if (req.url.startsWith('/community')) {
    return community.tryHandle(req, res);
  }

  // JSON en direct (lus par apps + site)
  if (req.url.startsWith('/lightning.json')) { res.writeHead(200, JSON_HEADERS); return res.end(JSON.stringify(buildLightning())); }
  if (req.url.startsWith('/strikes.json'))   { res.writeHead(200, JSON_HEADERS); return res.end(JSON.stringify(buildStrikes())); }

  // Enregistrement d'un device token (POST {token, secret})
  if (req.method === 'POST' && req.url.startsWith('/register')) {
    let body = ''; req.on('data', (d) => body += d); req.on('end', () => {
      let j = {}; try { j = JSON.parse(body); } catch {}
      if (!APNS || j.secret !== APNS.register_secret) { res.writeHead(403, JSON_HEADERS); return res.end('{"error":"forbidden"}'); }
      const tok = String(j.token || '').toLowerCase();
      if (!/^[0-9a-f]{64}$/.test(tok)) { res.writeHead(400, JSON_HEADERS); return res.end('{"error":"bad token"}'); }
      if (!pushTokens.includes(tok)) {
        pushTokens.push(tok);
        if (pushTokens.length > 50) pushTokens = pushTokens.slice(-50);
        saveTokens(); log(`token enregistré ${tok.slice(0, 8)}… (${pushTokens.length} au total)`);
      }
      res.writeHead(200, JSON_HEADERS); res.end(JSON.stringify({ ok: true, count: pushTokens.length }));
    });
    return;
  }
  // Push de TEST (GET /test-push?secret=...) — pour valider toute la chaîne
  if (req.url.startsWith('/test-push')) {
    const u = new URL(req.url, 'http://x');
    if (!APNS || u.searchParams.get('secret') !== APNS.register_secret) { res.writeHead(403, JSON_HEADERS); return res.end('{"error":"forbidden"}'); }
    notifyAll('🔔 Test MeteoSevy', 'Push de test — si tu vois ça, tout marche !', 'meteo-sevy-test');
    res.writeHead(200, JSON_HEADERS); return res.end(JSON.stringify({ ok: true, tokens: pushTokens.length }));
  }

  // Page dashboard
  const l = buildLightning();
  const html = `<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="15">
<title>⚡ Listener foudre — Sevy</title><style>
  body{margin:0;background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center}
  .card{background:#161b22;border:1px solid #30363d;border-radius:16px;padding:28px 32px;max-width:520px;width:92%}
  h1{font-size:1.25rem;margin:0 0 4px}.sub{color:#8b949e;font-size:.85rem;margin-bottom:20px}
  .row{display:flex;justify-content:space-between;padding:10px 0;border-top:1px solid #21262d;font-size:.95rem}
  .k{color:#8b949e}.v{font-weight:600;color:#e6edf3}.ok{color:#3fb950}.warn{color:#d29922}.crit{color:#f85149}
  .big{font-size:1.6rem;font-weight:800;margin:8px 0 16px}a{color:#58a6ff;text-decoration:none}
</style></head><body><div class="card">
  <h1>⚡ Listener foudre Blitzortung</h1><div class="sub">Service temps réel — Sevy Créations</div>
  <div class="big ${l.status === 'orage' ? (l.severity === 'critical' ? 'crit' : 'warn') : 'ok'}">${l.status === 'orage' ? `🌩️ Orage — ${l.nearest_km} km` : '🌤️ Calme autour de Vinelz'}</div>
  <div class="row"><span class="k">Connexion Blitzortung</span><span class="v ${connected ? 'ok' : 'crit'}">${connected ? 'connecté ✅' : 'déconnecté ⏳'}</span></div>
  <div class="row"><span class="k">Éclairs proches (≤${RADIUS_KM} km, ${NEAR_WINDOW_S / 60} min)</span><span class="v">${near.length}</span></div>
  <div class="row"><span class="k">Éclairs région (${STRIKES_MAX_AGE_S / 60} min)</span><span class="v">${region.length}</span></div>
  <div class="row"><span class="k">Push : tokens enregistrés</span><span class="v">${pushTokens.length}${APNS ? '' : ' (APNs OFF)'}</span></div>
  <div class="row"><span class="k">Mis à jour</span><span class="v">${new Date().toISOString().replace('T', ' ').replace(/\..*/, '')} UTC</span></div>
  <div class="row"><span class="k">Données</span><span class="v"><a href="/lightning.json">lightning.json</a> · <a href="/strikes.json">strikes.json</a></span></div>
</div></body></html>`;
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(html);
}).listen(HTTP_PORT, () => log(`HTTP sur :${HTTP_PORT}`));

// ╔══════════════ Démarrage ══════════════╗
connect();
setInterval(maintain, MAINTAIN_EVERY_MS);
setInterval(checkPush, PUSH_EVERY_MS);
log(`listener démarré — push APNs ${APNS ? 'activé (' + (APNS.production ? 'prod' : 'sandbox') + ')' : 'OFF'}`);

// ── Collecte + analyses (modules séparés, isolés : une erreur ici ne tue pas le listener foudre) ──
try {
  const collector = require('./collector.js');
  const sky = require('./sky.js');
  const daily = require('./daily.js');
  const events = require('./events.js');

  collector.start({ alertFn: notifyAll }); // station horaire (5 min) + health 'hourly'

  const runSky    = () => sky.runOnce().catch((e) => log('sky: ' + e.message));
  const runDaily  = () => daily.runOnce().then(() => collector.markHealth('daily', 15)).catch((e) => log('daily: ' + e.message));
  const runEvents = () => events.runOnce().then(() => collector.markHealth('alerts', 30)).catch((e) => log('events: ' + e.message));

  // Démarrages échelonnés (après l'amorçage du collecteur), puis périodiques.
  setTimeout(runSky, 8000);    setInterval(runSky, 5 * 60 * 1000);    // nébulosité, 5 min
  setTimeout(runDaily, 12000); setInterval(runDaily, 15 * 60 * 1000); // meteo_data.json, 15 min
  setTimeout(runEvents, 20000); setInterval(runEvents, 15 * 60 * 1000); // alerts.json, 15 min
  log('modules collecte branchés : station + sky + daily + events');
} catch (e) { log('collecte OFF: ' + e.message); }
