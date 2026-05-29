<?php
// ============================================================
// CONFIGURATION — change le mot de passe ici
// ============================================================
define('LOG_PASSWORD', 'meteo2026');   // ← ton mot de passe
define('SESSION_NAME', 'meteo_logs');

// Logs disponibles (nom affiché => fichier)
$logs = [
    '⏱️ Horaire'      => __DIR__ . '/logs/auto_wunderground_hourly.log',
    '📊 Journalier'   => __DIR__ . '/logs/auto_update_wunderground.log',
    '🔮 Prévisions'   => __DIR__ . '/logs/predictions_multihorizon.log',
    '🧠 Entraînement' => __DIR__ . '/logs/training_multihorizon.log',
    '⚠️ Événements'   => __DIR__ . '/logs/events.log',
    '📤 FTP Upload'   => __DIR__ . '/logs/ftp_upload.log',
];

$max_lines = 200; // Nombre de lignes affichées par log

// ============================================================
// AUTHENTIFICATION
// ============================================================
session_name(SESSION_NAME);
session_start();

$error = '';

if (isset($_POST['logout'])) {
    session_destroy();
    header('Location: ' . $_SERVER['PHP_SELF']);
    exit;
}

if (isset($_POST['password'])) {
    if ($_POST['password'] === LOG_PASSWORD) {
        $_SESSION['auth'] = true;
    } else {
        $error = 'Mot de passe incorrect.';
    }
}

$authenticated = isset($_SESSION['auth']) && $_SESSION['auth'] === true;

// ============================================================
// PAGE DE LOGIN
// ============================================================
if (!$authenticated) {
?><!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Météo Sevy — Logs</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0d1117;
    color: #c9d1d9;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
  }
  .login-box {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 40px;
    width: 340px;
    text-align: center;
  }
  .login-box h1 { font-size: 1.4rem; margin-bottom: 8px; color: #e6edf3; }
  .login-box p  { font-size: 0.85rem; color: #8b949e; margin-bottom: 24px; }
  input[type=password] {
    width: 100%;
    padding: 10px 14px;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    color: #e6edf3;
    font-size: 1rem;
    margin-bottom: 12px;
    outline: none;
  }
  input[type=password]:focus { border-color: #58a6ff; }
  button {
    width: 100%;
    padding: 10px;
    background: #238636;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 1rem;
    cursor: pointer;
  }
  button:hover { background: #2ea043; }
  .error { color: #f85149; font-size: 0.85rem; margin-top: 10px; }
  .icon { font-size: 2.5rem; margin-bottom: 16px; }
</style>
</head>
<body>
<div class="login-box">
  <div class="icon">🌦️</div>
  <h1>Météo Sevy — Logs</h1>
  <p>Accès réservé</p>
  <form method="post">
    <input type="password" name="password" placeholder="Mot de passe" autofocus>
    <button type="submit">Connexion</button>
    <?php if ($error): ?>
      <div class="error"><?= htmlspecialchars($error) ?></div>
    <?php endif; ?>
  </form>
</div>
</body>
</html>
<?php
    exit;
}

// ============================================================
// CAPTEUR INTÉRIEUR
// ============================================================
function get_interior() {
    $path = '/home/clients/171f38877b3223469356bb2d7409b781/sites/data.sevy-creations.net/interior.json';
    if (!file_exists($path)) return null;
    $data = json_decode(file_get_contents($path), true);
    return $data ?: null;
}

// ============================================================
// PAGE LOGS (authentifié)
// ============================================================

// Log actif (onglet)
$active_log = $_GET['log'] ?? array_key_first($logs);
if (!array_key_exists($active_log, $logs)) {
    $active_log = array_key_first($logs);
}

// Lire le contenu du log actif
function read_log($path, $max_lines) {
    if (!file_exists($path)) return null;
    $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if (!$lines) return [];
    return array_slice($lines, -$max_lines);
}

function colorize_line($line) {
    $line = htmlspecialchars($line);
    if (strpos($line, '❌') !== false || strpos($line, 'ERREUR') !== false || strpos($line, 'Error') !== false || strpos($line, 'fatal') !== false)
        return '<span class="err">' . $line . '</span>';
    if (strpos($line, '✅') !== false || strpos($line, 'SUCCESS') !== false || strpos($line, 'réussi') !== false)
        return '<span class="ok">' . $line . '</span>';
    if (strpos($line, '⚠️') !== false || strpos($line, 'Warning') !== false || strpos($line, 'ALERTE') !== false)
        return '<span class="warn">' . $line . '</span>';
    if (strpos($line, '===') !== false)
        return '<span class="sep">' . $line . '</span>';
    return $line;
}

$lines = read_log($logs[$active_log], $max_lines);
?><!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Météo Sevy — Logs</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0d1117;
    color: #c9d1d9;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    min-height: 100vh;
  }

  /* HEADER */
  header {
    background: #161b22;
    border-bottom: 1px solid #30363d;
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
  }
  .interior-widget {
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(255,255,255,.06);
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 13px;
  }
  .int-icon { font-size: 16px; }
  .int-val  { font-weight: 600; color: #e6edf3; }
  .int-sep  { color: #8b949e; }
  .int-bat  { font-size: 11px; color: #8b949e; margin-left: 4px; }
  .int-time { font-size: 11px; color: #8b949e; margin-left: 4px; }
  header h1 { font-size: 1.1rem; color: #e6edf3; }
  header .meta { font-size: 0.8rem; color: #8b949e; }
  .logout-btn {
    background: #21262d;
    border: 1px solid #30363d;
    color: #c9d1d9;
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.85rem;
  }
  .logout-btn:hover { background: #30363d; }

  /* ONGLETS */
  nav {
    display: flex;
    gap: 4px;
    padding: 16px 24px 0;
    flex-wrap: wrap;
  }
  nav a {
    text-decoration: none;
    padding: 8px 16px;
    border-radius: 8px 8px 0 0;
    font-size: 0.85rem;
    color: #8b949e;
    background: #161b22;
    border: 1px solid #30363d;
    border-bottom: none;
    transition: background 0.15s;
  }
  nav a:hover { color: #e6edf3; background: #1f2937; }
  nav a.active { color: #e6edf3; background: #1f2937; border-color: #58a6ff; border-bottom: 1px solid #1f2937; }

  /* CONTENU */
  .content {
    margin: 0 24px 24px;
    background: #1f2937;
    border: 1px solid #30363d;
    border-radius: 0 8px 8px 8px;
    padding: 0;
    overflow: hidden;
  }
  .log-header {
    padding: 12px 20px;
    background: #161b22;
    border-bottom: 1px solid #30363d;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.8rem;
    color: #8b949e;
  }
  .log-body {
    padding: 16px 20px;
    overflow-x: auto;
    max-height: 70vh;
    overflow-y: auto;
  }
  pre {
    font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
    font-size: 0.78rem;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-all;
  }
  .ok   { color: #3fb950; }
  .err  { color: #f85149; }
  .warn { color: #d29922; }
  .sep  { color: #58a6ff; opacity: 0.5; }

  .empty { color: #8b949e; font-style: italic; padding: 40px; text-align: center; }

  /* REFRESH */
  .refresh-bar {
    padding: 8px 24px;
    font-size: 0.75rem;
    color: #8b949e;
    text-align: right;
  }
</style>
</head>
<body>

<header>
  <div>
    <h1>🌦️ Météo Sevy — Supervision des logs</h1>
    <div class="meta">Rafraîchissement automatique toutes les 60 secondes</div>
  </div>
  <form method="post">
    <button class="logout-btn" name="logout" value="1">Déconnexion</button>
  </form>
  <?php $int = get_interior(); if ($int): ?>
  <div class="interior-widget">
    <span class="int-icon">🏠</span>
    <span class="int-val"><?= number_format((float)$int['temp'], 1) ?>°C</span>
    <?php if (!empty($int['humidity'])): ?>
    <span class="int-sep">·</span>
    <span class="int-val"><?= (int)$int['humidity'] ?>%</span>
    <?php endif; ?>
    <?php if (!empty($int['battery'])): ?>
    <span class="int-bat">🔋<?= (int)$int['battery'] ?>%</span>
    <?php endif; ?>
    <span class="int-time"><?= date('H:i', strtotime($int['updated'])) ?></span>
  </div>
  <?php endif; ?>
</header>

<nav>
<?php foreach ($logs as $label => $path): ?>
  <?php
    $exists = file_exists($path);
    $class  = ($label === $active_log) ? 'active' : '';
    $dot    = $exists ? '' : ' 🔴';
  ?>
  <a href="?log=<?= urlencode($label) ?>" class="<?= $class ?>">
    <?= htmlspecialchars($label . $dot) ?>
  </a>
<?php endforeach; ?>
</nav>

<div class="content">
  <div class="log-header">
    <span><?= htmlspecialchars($logs[$active_log]) ?></span>
    <span>
      <?php if ($lines !== null): ?>
        <?= count($lines) ?> dernières lignes
        — modifié le <?= date('d/m/Y H:i', filemtime($logs[$active_log])) ?>
      <?php else: ?>
        Fichier non trouvé
      <?php endif; ?>
    </span>
  </div>
  <div class="log-body">
    <?php if ($lines === null): ?>
      <div class="empty">Ce log n'existe pas encore — le workflow n'a pas encore tourné.</div>
    <?php elseif (empty($lines)): ?>
      <div class="empty">Log vide.</div>
    <?php else: ?>
      <pre><?php
        foreach (array_reverse($lines) as $line) {
            echo colorize_line($line) . "\n";
        }
      ?></pre>
    <?php endif; ?>
  </div>
</div>

<div class="refresh-bar">
  Dernière consultation : <?= date('d/m/Y à H:i:s') ?>
</div>

</body>
</html>
