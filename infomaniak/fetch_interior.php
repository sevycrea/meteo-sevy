<?php
/**
 * fetch_interior.php
 * Récupère temp/humidité du SNZB-02 via eWeLink et écrit interior.json
 * Placé dans data.sevy-creations.net/ — appelé par cron Infomaniak
 *
 * AUTH OAUTH AUTO-RENOUVELÉE.
 * L'app eWeLink (cet AppID) n'autorise que le flux OAuth. On garde donc
 * un refresh token, mais — contrairement à l'ancienne version — on :
 *   1. utilise le BON endpoint de refresh (/v2/user/refresh) ;
 *   2. PERSISTE le nouveau refresh token à chaque rotation (ewelink_token.json).
 * Tant que le cron tourne (< durée de vie du refresh token), la session se
 * renouvelle indéfiniment, sans intervention manuelle.
 *
 * Bootstrap (une fois) : mettre un refresh token frais dans ewelink_config.json
 * (obtenu via le flux OAuth). Ensuite le script s'auto-entretient.
 *
 * ewelink_config.json (sur le serveur, JAMAIS commité) :
 * { "app_id":"…", "app_secret":"…", "refresh_token":"…" }
 */

// ── Sécurité basique ──────────────────────────────────────────────────────────
define('CRON_SECRET', getenv('CRON_SECRET') ?: '');
if (php_sapi_name() !== 'cli' && CRON_SECRET) {
    $provided = $_GET['token'] ?? $_SERVER['HTTP_X_CRON_TOKEN'] ?? '';
    if (!hash_equals(CRON_SECRET, $provided)) { http_response_code(403); die('Forbidden'); }
}

// ── Config ────────────────────────────────────────────────────────────────────
$CONFIG_FILE = __DIR__ . '/ewelink_config.json';
$TOKEN_FILE  = __DIR__ . '/ewelink_token.json';
$OUTPUT_FILE = __DIR__ . '/interior.json';
$HISTORY_FILE = __DIR__ . '/interior_history.json';
$DEVICE_ID   = 'a48007565d';
$BASE_URL    = 'https://eu-apia.coolkit.cc/v2';

if (!file_exists($CONFIG_FILE)) die("Config manquante : $CONFIG_FILE\n");
$cfg = json_decode(file_get_contents($CONFIG_FILE), true);
$APP_ID     = $cfg['app_id']     ?? null;
$APP_SECRET = $cfg['app_secret'] ?? null;
if (!$APP_ID || !$APP_SECRET) die("❌ app_id / app_secret manquants dans $CONFIG_FILE\n");

// ── Helpers ───────────────────────────────────────────────────────────────────
function ew_sign(string $message, string $secret): string {
    return base64_encode(hash_hmac('sha256', $message, $secret, true));
}
function ew_nonce(int $n = 8): string {
    $c = 'abcdefghijklmnopqrstuvwxyz0123456789'; $o = '';
    for ($i = 0; $i < $n; $i++) $o .= $c[random_int(0, strlen($c) - 1)];
    return $o;
}
function ew_get(string $url, string $token, string $appid): array {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 15,
        CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . $token, 'X-CK-Appid: ' . $appid],
    ]);
    $r = curl_exec($ch); curl_close($ch);
    return json_decode($r, true) ?: [];
}

// ── Jetons ──────────────────────────────────────────────────────────────────
function load_tokens(string $TOKEN_FILE, array $cfg): array {
    // Priorité au fichier de jetons (rotation) ; fallback config (bootstrap).
    if (file_exists($TOKEN_FILE)) {
        $d = json_decode(file_get_contents($TOKEN_FILE), true) ?: [];
        if (!empty($d['rt'])) return $d;
    }
    return [
        'at' => $cfg['access_token'] ?? null,
        'rt' => $cfg['refresh_token'] ?? null,
        'at_expires' => 0,
    ];
}
function save_tokens(string $TOKEN_FILE, string $at, string $rt, int $at_expires): void {
    file_put_contents($TOKEN_FILE, json_encode([
        'at' => $at, 'rt' => $rt, 'at_expires' => $at_expires, 'saved_at' => time(),
    ], JSON_PRETTY_PRINT));
}
function refresh_tokens(string $base, string $appid, string $secret, string $rt): array {
    $body = json_encode(['rt' => $rt], JSON_UNESCAPED_UNICODE);
    $ch = curl_init("$base/user/refresh");
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true, CURLOPT_POST => true, CURLOPT_POSTFIELDS => $body,
        CURLOPT_TIMEOUT => 15,
        CURLOPT_HTTPHEADER => [
            'Content-Type: application/json',
            'X-CK-Appid: ' . $appid,
            'X-CK-Nonce: ' . ew_nonce(),
            'Authorization: Sign ' . ew_sign($body, $secret),
        ],
    ]);
    $resp = json_decode(curl_exec($ch), true) ?: [];
    curl_close($ch);
    return $resp;
}

// ── Obtention d'un access token valide ────────────────────────────────────────
function get_valid_token(array $args): string {
    [$base, $appid, $secret, $TOKEN_FILE, $cfg] = $args;
    $tok = load_tokens($TOKEN_FILE, $cfg);

    // Access token encore valide (> 1h de marge) → on l'utilise tel quel.
    if (!empty($tok['at']) && ($tok['at_expires'] ?? 0) > time() + 3600) {
        return $tok['at'];
    }
    // Sinon on rafraîchit avec le refresh token.
    if (empty($tok['rt'])) {
        die("❌ Aucun refresh token. Refaire le flux OAuth (ewelink_auth_setup).\n");
    }
    echo "  → refresh du token eWeLink…\n";
    $resp = refresh_tokens($base, $appid, $secret, $tok['rt']);
    if (($resp['error'] ?? -1) !== 0) {
        die("❌ Refresh échoué : " . json_encode($resp) . "\n   → refaire le flux OAuth.\n");
    }
    $data = $resp['data'] ?? [];
    $at = $data['at'] ?? null;
    $rt = $data['rt'] ?? $tok['rt'];                 // certains retours ne renvoient pas de nouveau rt
    $at_exp = isset($data['atExpiredTime']) ? (int)($data['atExpiredTime'] / 1000) : time() + 25 * 86400;
    if (!$at) die("❌ Refresh OK mais pas d'access token : " . json_encode($resp) . "\n");
    save_tokens($TOKEN_FILE, $at, $rt, $at_exp);
    echo "  ✅ token rafraîchi (valide jusqu'au " . date('d.m.Y', $at_exp) . ")\n";
    return $at;
}

// ── Main ──────────────────────────────────────────────────────────────────────
echo "[" . date('Y-m-d H:i:s') . "] fetch_interior démarré\n";

$token = get_valid_token([$BASE_URL, $APP_ID, $APP_SECRET, $TOKEN_FILE, $cfg]);

// Lecture appareils (avec un refresh forcé si le token est rejeté)
$resp = ew_get("$BASE_URL/device/thing", $token, $APP_ID);
if (($resp['error'] ?? -1) !== 0) {
    echo "  ⚠️ token rejeté ({$resp['error']}), refresh forcé…\n";
    @unlink($TOKEN_FILE);   // force un vrai refresh au prochain get_valid_token
    $token = get_valid_token([$BASE_URL, $APP_ID, $APP_SECRET, $TOKEN_FILE, $cfg]);
    $resp = ew_get("$BASE_URL/device/thing", $token, $APP_ID);
}
if (($resp['error'] ?? -1) !== 0) die("❌ Liste appareils : " . json_encode($resp) . "\n");

$params = null;
foreach ($resp['data']['thingList'] ?? [] as $item) {
    if (($item['itemData']['deviceid'] ?? '') === $DEVICE_ID) { $params = $item['itemData']['params'] ?? []; break; }
}
if ($params === null) {
    $ids = array_column(array_column($resp['data']['thingList'] ?? [], 'itemData'), 'deviceid');
    die("❌ Device $DEVICE_ID introuvable. Dispo : " . implode(', ', $ids) . "\n");
}
echo "  Params bruts : " . json_encode($params) . "\n";

// Normalisation
$temp_raw = $params['temperature'] ?? $params['currentTemperature'] ?? null;
$humi_raw = $params['humidity']    ?? $params['currentHumidity']    ?? null;
$bat      = $params['battery']     ?? null;

$temp = $temp_raw !== null ? (float)$temp_raw : null;
if ($temp !== null && $temp > 1000) $temp = round($temp / 100, 1);
elseif ($temp !== null && $temp > 100) $temp = round($temp / 10, 1);

$humi = null;
if ($humi_raw !== null) {
    $h = (float)$humi_raw;
    if ($h === 9999.0) $humi = null;
    elseif ($h > 100)  $humi = (int)round($h / 100);
    else               $humi = (int)round($h);
}

$interior = [
    'updated'  => gmdate('Y-m-d\TH:i:s\Z'),
    'temp'     => $temp,
    'humidity' => $humi,
    'battery'  => $bat !== null ? (int)$bat : null,
    'device'   => 'SNZB-02',
];
echo "  → {$interior['temp']} °C  {$interior['humidity']} %  bat {$interior['battery']}\n";

file_put_contents($OUTPUT_FILE, json_encode($interior, JSON_UNESCAPED_UNICODE));
echo "✅ interior.json écrit\n";

// Historique 48h
$history = file_exists($HISTORY_FILE) ? (json_decode(file_get_contents($HISTORY_FILE), true) ?: []) : [];
$history[] = [
    'ts' => time(), 'updated' => $interior['updated'],
    'temp' => $interior['temp'], 'humidity' => $interior['humidity'], 'battery' => $interior['battery'],
];
$cutoff = time() - 48 * 3600;
$history = array_values(array_filter($history, fn($r) => ($r['ts'] ?? 0) >= $cutoff));
file_put_contents($HISTORY_FILE, json_encode($history, JSON_UNESCAPED_UNICODE));
echo "✅ interior_history.json mis à jour (" . count($history) . " points)\n";
