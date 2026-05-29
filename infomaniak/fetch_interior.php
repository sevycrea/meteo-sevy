<?php
/**
 * fetch_interior.php
 * Récupère temp/humidité du SNZB-02 via eWeLink et écrit interior.json
 * Placé dans data.sevy-creations.net/ — appelé par cron Infomaniak
 *
 * Sécurité : appel uniquement depuis localhost (cron CLI) ou avec token secret
 */

// ── Sécurité basique ──────────────────────────────────────────────────────────
define('CRON_SECRET', getenv('CRON_SECRET') ?: '');  // optionnel via env
if (php_sapi_name() !== 'cli' && CRON_SECRET) {
    $provided = $_GET['token'] ?? $_SERVER['HTTP_X_CRON_TOKEN'] ?? '';
    if (!hash_equals(CRON_SECRET, $provided)) {
        http_response_code(403);
        die('Forbidden');
    }
}

// ── Config ────────────────────────────────────────────────────────────────────
$CONFIG_FILE = __DIR__ . '/ewelink_config.json';
$OUTPUT_FILE = __DIR__ . '/interior.json';
$DEVICE_ID   = 'a480075689';
$BASE_URL     = 'https://eu-apia.coolkit.cc/v2';

if (!file_exists($CONFIG_FILE)) {
    die("Config manquante : $CONFIG_FILE\n");
}
$cfg = json_decode(file_get_contents($CONFIG_FILE), true);
$APP_ID    = $cfg['app_id'];
$APP_SECRET = $cfg['app_secret'];
$TOKEN_FILE = __DIR__ . '/ewelink_token.json';

// ── Helpers ───────────────────────────────────────────────────────────────────
function ew_sign(string $message, string $secret): string {
    return base64_encode(hash_hmac('sha256', $message, $secret, true));
}

function ew_get(string $url, string $token, string $appid): array {
    global $APP_ID;
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 15,
        CURLOPT_HTTPHEADER     => [
            'Authorization: Bearer ' . $token,
            'X-CK-Appid: ' . $appid,
        ],
    ]);
    $resp = curl_exec($ch);
    curl_close($ch);
    return json_decode($resp, true) ?: [];
}

function ew_post(string $url, array $payload, string $appid, string $secret): array {
    $body = json_encode($payload, JSON_UNESCAPED_UNICODE);
    $sign = ew_sign($body, $secret);
    $ch   = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => $body,
        CURLOPT_TIMEOUT        => 15,
        CURLOPT_HTTPHEADER     => [
            'Content-Type: application/json',
            'X-CK-Appid: ' . $appid,
            'Authorization: Sign ' . $sign,
        ],
    ]);
    $resp = curl_exec($ch);
    curl_close($ch);
    return json_decode($resp, true) ?: [];
}

// ── Gestion du token ──────────────────────────────────────────────────────────
function load_token(): ?string {
    global $TOKEN_FILE;
    if (!file_exists($TOKEN_FILE)) return null;
    $d = json_decode(file_get_contents($TOKEN_FILE), true);
    // Valide si expire dans > 1h
    if (isset($d['token']) && isset($d['expires_at']) && time() < $d['expires_at'] - 3600) {
        return $d['token'];
    }
    return null;
}

function save_token(string $token, int $expires_at): void {
    global $TOKEN_FILE;
    file_put_contents($TOKEN_FILE, json_encode([
        'token'      => $token,
        'expires_at' => $expires_at,
        'saved_at'   => time(),
    ]));
}

function refresh_token(array $cfg): ?string {
    global $BASE_URL;
    $rt = $cfg['refresh_token'] ?? null;
    if (!$rt) return null;

    // Tentative 1 : signer le body
    $resp = ew_post("$BASE_URL/user/oauth/token",
        ['grantType' => 'refresh_token', 'rt' => $rt],
        $cfg['app_id'], $cfg['app_secret']
    );
    if (($resp['error'] ?? -1) === 0) {
        $at  = $resp['data']['accessToken'] ?? null;
        $exp = $resp['data']['atExpiredTime'] ?? (time() + 30 * 86400);
        if ($at) { save_token($at, (int)$exp); return $at; }
    }
    echo "  Refresh tentative 1 : " . json_encode($resp) . "\n";

    // Tentative 2 : signer le RT lui-même
    $body = json_encode(['rt' => $rt], JSON_UNESCAPED_UNICODE);
    $sign = ew_sign($rt, $cfg['app_secret']);
    $ch   = curl_init("$BASE_URL/user/oauth/token");
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => $body,
        CURLOPT_TIMEOUT        => 15,
        CURLOPT_HTTPHEADER     => [
            'Content-Type: application/json',
            "X-CK-Appid: {$cfg['app_id']}",
            "Authorization: Sign $sign",
        ],
    ]);
    $resp2 = json_decode(curl_exec($ch), true) ?: [];
    curl_close($ch);
    echo "  Refresh tentative 2 : " . json_encode($resp2) . "\n";
    if (($resp2['error'] ?? -1) === 0) {
        $at  = $resp2['data']['accessToken'] ?? null;
        $exp = $resp2['data']['atExpiredTime'] ?? (time() + 30 * 86400);
        if ($at) { save_token($at, (int)$exp); return $at; }
    }

    return null;
}

// ── Main ──────────────────────────────────────────────────────────────────────
echo "[" . date('Y-m-d H:i:s') . "] fetch_interior démarré\n";

// 1. Token
$token = load_token();
if (!$token) {
    echo "  Token expiré/absent → tentative refresh…\n";
    $token = refresh_token($cfg);
}
if (!$token) {
    // Dernier recours : token brut depuis config
    $token = $cfg['access_token'] ?? null;
}
if (!$token) {
    die("❌ Pas de token disponible. Relance ewelink_auth_setup.py\n");
}
echo "  Token : " . substr($token, 0, 8) . "…\n";

// 2. Lecture appareils
$resp = ew_get("$BASE_URL/device/thing", $token, $APP_ID);
if (($resp['error'] ?? -1) !== 0) {
    // Token invalide → essai refresh forcé
    echo "  Token invalide ({$resp['error']}), refresh forcé…\n";
    $token = refresh_token($cfg);
    if ($token) {
        $resp = ew_get("$BASE_URL/device/thing", $token, $APP_ID);
    }
}
if (($resp['error'] ?? -1) !== 0) {
    die("❌ Liste appareils : " . json_encode($resp) . "\n");
}

$params = null;
foreach ($resp['data']['thingList'] ?? [] as $item) {
    if (($item['itemData']['deviceid'] ?? '') === $DEVICE_ID) {
        $params = $item['itemData']['params'] ?? [];
        break;
    }
}
if ($params === null) {
    $ids = array_column(array_column($resp['data']['thingList'] ?? [], 'itemData'), 'deviceid');
    die("❌ Device $DEVICE_ID introuvable. Dispo : " . implode(', ', $ids) . "\n");
}

echo "  Params bruts : " . json_encode($params) . "\n";

// 3. Normalisation
$temp_raw = $params['temperature'] ?? $params['currentTemperature'] ?? null;
$humi_raw = $params['humidity']    ?? $params['currentHumidity']    ?? null;
$bat      = $params['battery']     ?? null;

$temp = $temp_raw !== null ? (float)$temp_raw : null;
if ($temp !== null && $temp > 100) $temp = round($temp / 10, 1);

$interior = [
    'updated'  => gmdate('Y-m-d\TH:i:s\Z'),
    'temp'     => $temp,
    'humidity' => $humi_raw !== null ? (int)$humi_raw : null,
    'battery'  => $bat      !== null ? (int)$bat      : null,
    'device'   => 'SNZB-02',
];
echo "  → {$interior['temp']} °C  {$interior['humidity']} %  bat {$interior['battery']}\n";

// 4. Écriture
file_put_contents($OUTPUT_FILE, json_encode($interior, JSON_UNESCAPED_UNICODE));
echo "✅ interior.json écrit\n";
