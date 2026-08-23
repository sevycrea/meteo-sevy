<?php
/**
 * fetch_interior.php
 * Récupère temp/humidité du SNZB-02 via eWeLink et écrit interior.json
 * Placé dans data.sevy-creations.net/ — appelé par cron Infomaniak
 *
 * AUTH AUTONOME : login email + mot de passe eWeLink à CHAQUE run.
 * Un jeton d'accès eWeLink expire en ~30 jours ; l'ancienne version
 * s'appuyait sur un refresh token qui a fini par expirer (panne du 28.06.2026).
 * Ici on ouvre une session fraîche à chaque exécution → plus aucune
 * expiration à gérer.
 *
 * ewelink_config.json (sur le serveur, JAMAIS commité) :
 * {
 *   "app_id":       "…",
 *   "app_secret":   "…",
 *   "email":        "compte@exemple.ch",
 *   "password":     "…",
 *   "country_code": "+41"
 * }
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
$DEVICE_ID   = 'a48007565d';

// Hôtes API par région eWeLink. On démarre en EU ; si le compte vit ailleurs,
// le login renvoie error 10004 + la bonne région et on rejoue dessus.
$REGION_HOSTS = [
    'eu' => 'https://eu-apia.coolkit.cc/v2',
    'us' => 'https://us-apia.coolkit.cc/v2',
    'as' => 'https://as-apia.coolkit.cc/v2',
    'cn' => 'https://cn-apia.coolkit.cn/v2',
];

if (!file_exists($CONFIG_FILE)) {
    die("Config manquante : $CONFIG_FILE\n");
}
$cfg = json_decode(file_get_contents($CONFIG_FILE), true);
$APP_ID     = $cfg['app_id']     ?? null;
$APP_SECRET = $cfg['app_secret'] ?? null;
$EMAIL      = $cfg['email']      ?? null;
$PASSWORD   = $cfg['password']   ?? null;
$COUNTRY    = $cfg['country_code'] ?? '+41';

if (!$APP_ID || !$APP_SECRET || !$EMAIL || !$PASSWORD) {
    die("❌ Config incomplète : il faut app_id, app_secret, email, password dans $CONFIG_FILE\n");
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function ew_sign(string $message, string $secret): string {
    return base64_encode(hash_hmac('sha256', $message, $secret, true));
}

function ew_nonce(int $n = 8): string {
    $chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    $out = '';
    for ($i = 0; $i < $n; $i++) $out .= $chars[random_int(0, strlen($chars) - 1)];
    return $out;
}

function ew_get(string $url, string $token, string $appid): array {
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

// ── Login eWeLink (email + mot de passe) ───────────────────────────────────────
function ew_login(array $cfg, array $regions): array {
    $payload = [
        'email'       => $cfg['email'],
        'password'    => $cfg['password'],
        'countryCode' => $cfg['country_code'] ?? '+41',
    ];
    $body = json_encode($payload, JSON_UNESCAPED_UNICODE);
    $sign = ew_sign($body, $cfg['app_secret']);
    $headers = [
        'Content-Type: application/json',
        'X-CK-Appid: ' . $cfg['app_id'],
        'X-CK-Nonce: ' . ew_nonce(),
        'Authorization: Sign ' . $sign,
    ];

    $region = 'eu';
    for ($attempt = 0; $attempt < 2; $attempt++) {
        $base = $regions[$region];
        $ch = curl_init("$base/user/login");
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_POST           => true,
            CURLOPT_POSTFIELDS     => $body,
            CURLOPT_TIMEOUT        => 15,
            CURLOPT_HTTPHEADER     => $headers,
        ]);
        $resp = json_decode(curl_exec($ch), true) ?: [];
        curl_close($ch);

        $err = $resp['error'] ?? -1;
        if ($err === 0) {
            $at = $resp['data']['at'] ?? null;
            if ($at) {
                echo "  ✅ Session eWeLink ouverte (région $region)\n";
                return [$at, $base];
            }
            throw new Exception("Login OK mais pas de token : " . json_encode($resp));
        }
        // Mauvaise région : eWeLink indique la bonne dans data.region
        if ($err === 10004 && $attempt === 0) {
            $nr = $resp['data']['region'] ?? null;
            if ($nr && isset($regions[$nr]) && $nr !== $region) {
                echo "  ↪︎ redirection région $region → $nr\n";
                $region = $nr;
                continue;
            }
        }
        throw new Exception("Login eWeLink échoué : " . json_encode($resp));
    }
    throw new Exception("Login eWeLink : région introuvable");
}

// ── Main ──────────────────────────────────────────────────────────────────────
echo "[" . date('Y-m-d H:i:s') . "] fetch_interior démarré\n";

// 1. Session fraîche
[$token, $BASE_URL] = ew_login($cfg, $REGION_HOSTS);

// 2. Lecture appareils
$resp = ew_get("$BASE_URL/device/thing", $token, $APP_ID);
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
if ($temp !== null && $temp > 1000) $temp = round($temp / 100, 1);
elseif ($temp !== null && $temp > 100) $temp = round($temp / 10, 1);

// Normalisation humidité : même encodage que température (÷100)
// 9999 = valeur sentinelle = indisponible
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

// 4. Écriture interior.json (valeur courante)
file_put_contents($OUTPUT_FILE, json_encode($interior, JSON_UNESCAPED_UNICODE));
echo "✅ interior.json écrit\n";

// 5. Historique 48h → interior_history.json
$HISTORY_FILE = __DIR__ . '/interior_history.json';
$history = [];
if (file_exists($HISTORY_FILE)) {
    $history = json_decode(file_get_contents($HISTORY_FILE), true) ?: [];
}
// Ajoute la mesure courante
$history[] = [
    'ts'       => time(),
    'updated'  => $interior['updated'],
    'temp'     => $interior['temp'],
    'humidity' => $interior['humidity'],
    'battery'  => $interior['battery'],
];
// Garde seulement les 48 dernières heures (48 mesures × 1h)
$cutoff = time() - 48 * 3600;
$history = array_values(array_filter($history, fn($r) => ($r['ts'] ?? 0) >= $cutoff));
file_put_contents($HISTORY_FILE, json_encode($history, JSON_UNESCAPED_UNICODE));
echo "✅ interior_history.json mis à jour (" . count($history) . " points)\n";
