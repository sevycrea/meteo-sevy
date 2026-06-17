<?php
/**
 * ingest.php — reçoit un JSON du collecteur Node (HTTPS POST) et l'écrit en LOCAL
 * sur data.sevy-creations.net. Permet à Node (qui ne peut pas FTP) d'alimenter
 * les fichiers que l'app/le site/le ML lisent déjà ici — sans rien repointer.
 *
 * Sécurité : secret partagé + LISTE BLANCHE de noms + écriture atomique.
 * Body JSON attendu : { "secret": "...", "name": "meteo_data_hourly.json", "content": { ... } }
 */
header('Content-Type: application/json');

define('INGEST_SECRET', getenv('INGEST_SECRET') ?: '4762b323c7725087436157cf630902b5');
$ALLOWED = [
  'meteo_data_hourly.json',
  'meteo_data_realtime.json',
  'live.json',
  'meteo_data.json',
  'sky.json',
  'alerts.json',
  'health.json',
  'ingest_test.json',   // pour les tests
];

$body = json_decode(file_get_contents('php://input'), true);
if (!is_array($body)) { http_response_code(400); echo '{"error":"bad body"}'; exit; }
if (!hash_equals(INGEST_SECRET, (string)($body['secret'] ?? ''))) { http_response_code(403); echo '{"error":"forbidden"}'; exit; }

$name = $body['name'] ?? '';
if (!in_array($name, $ALLOWED, true)) { http_response_code(400); echo '{"error":"name not allowed"}'; exit; }

if (!array_key_exists('content', $body)) { http_response_code(400); echo '{"error":"no content"}'; exit; }
$json = json_encode($body['content'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
if ($json === false) { http_response_code(400); echo '{"error":"bad json"}'; exit; }

$path = __DIR__ . '/' . $name;
$tmp  = $path . '.tmp';
if (file_put_contents($tmp, $json, LOCK_EX) === false) { http_response_code(500); echo '{"error":"write failed"}'; exit; }
rename($tmp, $path);  // bascule atomique
echo json_encode(['ok' => true, 'name' => $name, 'bytes' => strlen($json)]);
