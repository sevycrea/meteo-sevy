<?php
/**
 * push_alerts.php
 * Déposé dans data.sevy-creations.net/ — appelé par un CRON Infomaniak (~2 min).
 *
 * Rôle : ce que faisait `AlertNotifications.checkAndNotify()` dans l'app, mais
 * CÔTÉ SERVEUR. Lit les JSON locaux (alerts/lightning/realtime), détecte les
 * FRONTS MONTANTS (nouvelle alerte, orage ≤10 km, début de pluie) et envoie un
 * PUSH APNs aux iPhones enregistrés — même app fermée.
 *
 * Fichiers voisins (même dossier) :
 *   apns_config.json   { team_id, key_id, bundle_id, key_file, production }
 *   AuthKey_XXXX.p8    clé APNs (référencée par key_file)
 *   push_tokens.json   [ "<devicetoken hex>", ... ]   ← uploadé par l'app
 *   push_state.json    état persistant (déjà-vu) — créé/maj automatiquement
 *   apns_jwt_cache.json cache du jeton provider (régénéré < 50 min)
 *
 * Sécurité : CLI (cron) uniquement, ou URL avec ?token=CRON_SECRET.
 */

date_default_timezone_set('Europe/Zurich');

define('CRON_SECRET', getenv('CRON_SECRET') ?: '');
if (php_sapi_name() !== 'cli' && CRON_SECRET) {
    $provided = $_GET['token'] ?? $_SERVER['HTTP_X_CRON_TOKEN'] ?? '';
    if (!hash_equals(CRON_SECRET, $provided)) { http_response_code(403); die('Forbidden'); }
}

$DIR        = __DIR__;
$LOG_FILE   = "$DIR/push_alerts.log";
$STATE_FILE = "$DIR/push_state.json";
$TOKENS_FILE= "$DIR/push_tokens.json";
$APNS_CFG   = "$DIR/apns_config.json";

function logmsg(string $m): void {
    global $LOG_FILE;
    $line = '[' . date('Y-m-d H:i:s') . "] $m\n";
    echo $line;
    @file_put_contents($LOG_FILE, $line, FILE_APPEND);
}
function read_json(string $path) {
    if (!file_exists($path)) return null;
    $d = json_decode(file_get_contents($path), true);
    return $d ?: null;
}

// ── Base64 URL-safe ─────────────────────────────────────────────────────────
function b64url(string $bin): string {
    return rtrim(strtr(base64_encode($bin), '+/', '-_'), '=');
}

// ── Conversion signature ECDSA DER → raw R||S (64 octets) requis par APNs ─────
function der_to_raw_ecdsa(string $der): string {
    $pos = 0;
    if (ord($der[$pos++]) !== 0x30) throw new RuntimeException('DER: pas une SEQUENCE');
    $len = ord($der[$pos++]);
    if ($len & 0x80) { $pos += ($len & 0x7f); }            // longueur longue (peu probable ici)
    $read_int = function () use ($der, &$pos): string {
        if (ord($der[$pos++]) !== 0x02) throw new RuntimeException('DER: pas un INTEGER');
        $l = ord($der[$pos++]);
        $v = substr($der, $pos, $l); $pos += $l;
        $v = ltrim($v, "\x00");                            // retire le zéro de signe
        return str_pad($v, 32, "\x00", STR_PAD_LEFT);      // pad à 32 octets
    };
    $r = $read_int();
    $s = $read_int();
    return $r . $s;
}

// ── Jeton provider APNs (JWT ES256), mis en cache < 50 min ────────────────────
function apns_jwt(array $cfg, string $dir): string {
    $cache = "$dir/apns_jwt_cache.json";
    $c = read_json($cache);
    if ($c && isset($c['iat'], $c['jwt']) && (time() - $c['iat']) < 50 * 60) {
        return $c['jwt'];
    }
    $keyPath = $cfg['key_file'][0] === '/' ? $cfg['key_file'] : "$dir/{$cfg['key_file']}";
    $pem = file_get_contents($keyPath);
    if ($pem === false) throw new RuntimeException("Clé APNs introuvable : $keyPath");
    $pkey = openssl_pkey_get_private($pem);
    if ($pkey === false) throw new RuntimeException('Clé APNs (.p8) illisible');

    $iat    = time();
    $header = b64url(json_encode(['alg' => 'ES256', 'kid' => $cfg['key_id']]));
    $claims = b64url(json_encode(['iss' => $cfg['team_id'], 'iat' => $iat]));
    $input  = "$header.$claims";
    $der = '';
    if (!openssl_sign($input, $der, $pkey, OPENSSL_ALGO_SHA256)) {
        throw new RuntimeException('Signature JWT échouée');
    }
    $jwt = "$input." . b64url(der_to_raw_ecdsa($der));
    @file_put_contents($cache, json_encode(['iat' => $iat, 'jwt' => $jwt]));
    return $jwt;
}

// ── Envoi d'un push à un token. Renvoie [code_http, corps] ────────────────────
function apns_send(string $host, string $jwt, string $bundleId, string $token, array $aps): array {
    $ch = curl_init("https://$host/3/device/$token");
    curl_setopt_array($ch, [
        CURLOPT_HTTP_VERSION   => CURL_HTTP_VERSION_2_0,    // APNs EXIGE HTTP/2
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => json_encode($aps),
        CURLOPT_HTTPHEADER     => [
            "authorization: bearer $jwt",
            "apns-topic: $bundleId",
            "apns-push-type: alert",
            "apns-priority: 10",
            "content-type: application/json",
        ],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 15,
    ]);
    $resp = curl_exec($ch);
    $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err  = curl_error($ch);
    curl_close($ch);
    if ($err) logmsg("⚠️ curl: $err");
    return [$code, $resp];
}

// ── Détection des événements (réplique de AlertNotifications de l'app) ─────────
function freshness_sec(?string $iso): ?int {
    if (!$iso) return null;
    $t = strtotime($iso);
    return $t ? (time() - $t) : null;
}

function detect_alerts(array $state): array {
    $b = read_json(__DIR__ . '/alerts.json');
    if (!$b || !isset($b['alerts'])) return [[], $state];
    $seen = $state['seenAlertIds'] ?? null;
    $ids  = array_map(fn($a) => $a['detected_at'] ?? '', $b['alerts']);
    if ($seen === null) {                       // premier run : on amorce sans notifier
        $state['seenAlertIds'] = $ids;
        return [[], $state];
    }
    $seenSet = array_flip($seen);
    $notifs = [];
    foreach ($b['alerts'] as $a) {
        $id = $a['detected_at'] ?? '';
        if ($id === '' || isset($seenSet[$id])) continue;
        $sev = $a['severity'] ?? 'info';
        $title = $sev === 'critical' ? '⚠️ Alerte critique' : ($sev === 'warning' ? '⚠️ Alerte météo' : 'ℹ️ Info météo');
        $notifs[] = ['title' => $title, 'subtitle' => $a['recommendation'] ?? '', 'body' => $a['message'] ?? '', 'thread' => 'meteo-sevy-alerts'];
    }
    $state['seenAlertIds'] = $ids;
    return [$notifs, $state];
}

function detect_storm(array $state): array {
    $i = read_json(__DIR__ . '/lightning.json');
    if (!$i) return [[], $state];
    $fresh = ($s = freshness_sec($i['generated_at'] ?? null)) !== null && $s < 20 * 60;
    $strikeRecent = ($ss = freshness_sec($i['last_strike_at'] ?? null)) === null || $ss < 30 * 60;
    $active = (($i['status'] ?? '') === 'orage') && $fresh && $strikeRecent;
    $near = $active && (($i['nearest_km'] ?? 999) <= 10);
    $was = $state['stormWasNear'] ?? false;
    $notifs = [];
    if ($near && !$was) {
        $km = $i['nearest_km'] ?? null;
        $body = $km !== null ? sprintf('Foudre détectée à %d km.', round($km)) : 'Foudre détectée à proximité.';
        if (($i['trend'] ?? '') === 'approche') $body .= " L'orage se rapproche.";
        $notifs[] = ['title' => '⚡ Orage proche de Vinelz', 'subtitle' => '', 'body' => $body, 'thread' => 'meteo-sevy-storm'];
    }
    $state['stormWasNear'] = $near;
    return [$notifs, $state];
}

function detect_rain(array $state): array {
    $d = read_json(__DIR__ . '/meteo_data_realtime.json');
    if (!$d) return [[], $state];
    $pts = [];
    foreach ($d as $p) {
        if (!isset($p['timestamp'])) continue;
        $dt = DateTime::createFromFormat('Y-m-d H:i:s', $p['timestamp'], new DateTimeZone('Europe/Zurich'));
        if ($dt) $pts[] = ['t' => $dt->getTimestamp(), 'rain' => $p['rain'] ?? null, 'rate' => $p['rain_rate'] ?? null];
    }
    usort($pts, fn($a, $b) => $a['t'] <=> $b['t']);
    $was = $state['rainWasRaining'] ?? false;
    $isRaining = false;
    $n = count($pts);
    if ($n >= 1 && (time() - $pts[$n - 1]['t']) < 30 * 60) {
        $accum = ($n >= 2) && (($pts[$n - 1]['rain'] ?? 0) - ($pts[$n - 2]['rain'] ?? 0) > 0);
        $strong = ($pts[$n - 1]['rate'] ?? 0) >= 0.5;
        $isRaining = $accum || $strong;
    }
    $notifs = [];
    if ($isRaining && !$was) {
        $total = $n ? ($pts[$n - 1]['rain'] ?? null) : null;
        $body = $total !== null ? sprintf("La station relève de la pluie en ce moment (%.1f mm aujourd'hui).", $total)
                                : 'La station de Vinelz détecte de la pluie en ce moment.';
        $notifs[] = ['title' => '🌧️ Il pleut à Vinelz', 'subtitle' => '', 'body' => $body, 'thread' => 'meteo-sevy-rain'];
    }
    $state['rainWasRaining'] = $isRaining;
    return [$notifs, $state];
}

// ── MAIN ──────────────────────────────────────────────────────────────────────
try {
    $cfg = read_json($APNS_CFG);
    if (!$cfg) { logmsg('❌ apns_config.json manquant'); exit(1); }
    $bundleId = $cfg['bundle_id'];
    $host = !empty($cfg['production']) ? 'api.push.apple.com' : 'api.sandbox.push.apple.com';

    $state = read_json($STATE_FILE) ?: [];

    [$nA, $state] = detect_alerts($state);
    [$nS, $state] = detect_storm($state);
    [$nR, $state] = detect_rain($state);
    $notifs = array_merge($nA, $nS, $nR);

    // On sauve l'état AVANT d'envoyer : si l'envoi casse, on ne re-spammera pas.
    @file_put_contents($STATE_FILE, json_encode($state));

    if (!$notifs) { logmsg('rien de neuf (' . $host . ')'); exit(0); }

    $tokens = read_json($TOKENS_FILE) ?: [];
    if (!$tokens) { logmsg('⚠️ aucun device token (push_tokens.json vide) — ' . count($notifs) . ' notif(s) non envoyée(s)'); exit(0); }

    $jwt = apns_jwt($cfg, $DIR);
    $dead = [];
    foreach ($notifs as $nf) {
        $aps = ['aps' => ['alert' => array_filter([
            'title'    => $nf['title'],
            'subtitle' => $nf['subtitle'] ?: null,
            'body'     => $nf['body'],
        ]), 'sound' => 'default', 'thread-id' => $nf['thread']]];
        foreach ($tokens as $tok) {
            [$code, $resp] = apns_send($host, $jwt, $bundleId, $tok, $aps);
            if ($code === 200) {
                logmsg("✅ push « {$nf['title']} » → " . substr($tok, 0, 8) . '…');
            } elseif ($code === 410 || ($code === 400 && strpos((string)$resp, 'BadDeviceToken') !== false)) {
                $dead[$tok] = true;                          // token expiré/invalide → purge
                logmsg("🗑️ token mort (" . substr($tok, 0, 8) . "…) code $code");
            } else {
                logmsg("⚠️ APNs code $code : " . substr((string)$resp, 0, 200));
            }
        }
    }
    if ($dead) {
        $tokens = array_values(array_filter($tokens, fn($t) => !isset($dead[$t])));
        @file_put_contents($TOKENS_FILE, json_encode($tokens));
    }
    exit(0);
} catch (Throwable $e) {
    logmsg('❌ ' . $e->getMessage());
    exit(1);
}
