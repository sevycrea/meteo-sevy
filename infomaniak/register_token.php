<?php
/**
 * register_token.php
 * Déposé dans data.sevy-creations.net/ — l'app iOS y POST son device token APNs.
 * Stocke les tokens (dédupliqués) dans push_tokens.json, lu par push_alerts.php.
 *
 * Sécurité : secret partagé avec l'app (léger, suffisant pour un usage perso) +
 * validation stricte du format (64 hex) + plafond du nombre de tokens.
 */
header('Content-Type: application/json');

define('REG_SECRET', getenv('REG_SECRET') ?: 'CHANGE_ME');  // DOIT matcher la valeur dans l'app

$body   = json_decode(file_get_contents('php://input'), true) ?: $_POST;
$secret = $body['secret'] ?? '';
$token  = strtolower(trim($body['token'] ?? ''));

if (!hash_equals(REG_SECRET, (string)$secret)) {
    http_response_code(403); echo json_encode(['error' => 'forbidden']); exit;
}
if (!preg_match('/^[0-9a-f]{64}$/', $token)) {
    http_response_code(400); echo json_encode(['error' => 'bad token']); exit;
}

$file   = __DIR__ . '/push_tokens.json';
$tokens = file_exists($file) ? (json_decode(file_get_contents($file), true) ?: []) : [];
if (!in_array($token, $tokens, true)) {
    $tokens[] = $token;
    if (count($tokens) > 50) $tokens = array_slice($tokens, -50);  // plafond anti-spam
    file_put_contents($file, json_encode($tokens));
}
echo json_encode(['ok' => true, 'count' => count($tokens)]);
