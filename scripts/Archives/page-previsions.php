<?php
/**
 * Template Name: Prévisions Météo IA
 * Template Post Type: page
 * Description: Page de prévisions météo générées par Intelligence Artificielle
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// Enqueue des assets
wp_enqueue_style(
    'previsions-style',
    get_stylesheet_directory_uri() . '/prevision-meteo/previsions-style.css',
    array(),
    time()
);

wp_enqueue_script(
    'previsions-script',
    get_stylesheet_directory_uri() . '/prevision-meteo/previsions-script.js',
    array( 'jquery' ),
    time(),
    true
);

wp_localize_script(
    'previsions-script',
    'wp_previsions_vars',
    array(
        'theme_uri' => get_stylesheet_directory_uri(),
        'ajax_url' => admin_url('admin-ajax.php')
    )
);

get_header();
?>

<div id="primary" class="content-area previsions-ia-page">
    <main id="main" class="site-main">
        
        <article class="previsions-container">
            
            <!-- En-tête -->
            <header class="previsions-header">
                <h1>🤖 Prévisions Météo IA</h1>
                <p class="subtitle">Prédictions générées par Intelligence Artificielle</p>
                <p class="location">📍 Station IVINEL2 - Winterthur, Suisse</p>
            </header>

            <!-- Navigation -->
            <div class="page-nav">
                <a href="<?php echo home_url('/meteo-pro/'); ?>" class="nav-link">
                    🏔️ Données Réelles
                </a>
                <span class="nav-link active">
                    🤖 Prévisions IA
                </span>
            </div>

            <!-- Carte principale : Prévisions Demain -->
            <section class="forecast-main">
                <div class="forecast-card">
                    <h2>📅 Prévisions pour Demain</h2>
                    
                    <div id="forecastLoading" class="loading">
                        <div class="spinner"></div>
                        <p>Chargement des prévisions...</p>
                    </div>
                    
                    <div id="forecastContent" style="display: none;">
                        <!-- Date -->
                        <div class="forecast-date">
                            <div class="day-name" id="dayName">-</div>
                            <div class="date-num" id="dateNum">-</div>
                        </div>

                        <!-- Température -->
                        <div class="forecast-temp">
                            <div class="temp-icon">🌡️</div>
                            <div class="temp-value" id="tempValue">--°C</div>
                            <div class="temp-range" id="tempRange">-- à --°C</div>
                        </div>

                        <!-- Pluie -->
                        <div class="forecast-rain">
                            <div class="rain-icon" id="rainIcon">🌧️</div>
                            <div class="rain-prob" id="rainProb">--%</div>
                            <div class="rain-label">de probabilité de pluie</div>
                        </div>

                        <!-- Confiance -->
                        <div class="forecast-confidence">
                            <div class="confidence-label">Niveau de confiance</div>
                            <div class="confidence-bar">
                                <div class="confidence-fill" id="confidenceFill" style="width: 0%"></div>
                            </div>
                            <div class="confidence-value" id="confidenceValue">--%</div>
                        </div>
                    </div>

                    <div id="forecastError" style="display: none;" class="error-message">
                        ❌ Impossible de charger les prévisions
                    </div>
                </div>
            </section>

            <!-- Performance du Modèle -->
            <section class="model-performance">
                <div class="performance-card">
                    <h3>📊 Performance du Modèle IA</h3>
                    
                    <div class="performance-grid">
                        <div class="performance-item">
                            <div class="perf-label">Précision Température</div>
                            <div class="perf-value" id="tempAccuracy">--</div>
                        </div>
                        
                        <div class="performance-item">
                            <div class="perf-label">Précision Pluie</div>
                            <div class="perf-value" id="rainAccuracy">--</div>
                        </div>
                        
                        <div class="performance-item">
                            <div class="perf-label">Dernière Mise à Jour</div>
                            <div class="perf-value" id="lastUpdate">--</div>
                        </div>
                        
                        <div class="performance-item">
                            <div class="perf-label">Données Utilisées</div>
                            <div class="perf-value">270 jours</div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- Comment ça marche -->
            <section class="how-it-works">
                <div class="info-card">
                    <h3>🧠 Comment ça Fonctionne ?</h3>
                    
                    <div class="info-grid">
                        <div class="info-item">
                            <div class="info-icon">📊</div>
                            <div class="info-title">Données Historiques</div>
                            <div class="info-text">Le modèle analyse 270 jours de données réelles de la station IVINEL2</div>
                        </div>
                        
                        <div class="info-item">
                            <div class="info-icon">🤖</div>
                            <div class="info-title">Machine Learning</div>
                            <div class="info-text">Algorithme RandomForest entraîné sur les patterns météorologiques locaux</div>
                        </div>
                        
                        <div class="info-item">
                            <div class="info-icon">🔄</div>
                            <div class="info-title">Auto-Apprentissage</div>
                            <div class="info-text">Le modèle se ré-entraîne automatiquement chaque nuit avec les nouvelles données</div>
                        </div>
                        
                        <div class="info-item">
                            <div class="info-icon">🎯</div>
                            <div class="info-title">Prédictions</div>
                            <div class="info-text">Nouvelles prévisions générées chaque matin à 6h pour la journée suivante</div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- Disclaimer -->
            <section class="disclaimer">
                <div class="disclaimer-card">
                    <p><strong>ℹ️ Note importante</strong></p>
                    <p>Ces prévisions sont générées par un modèle d'Intelligence Artificielle entraîné sur des données locales. Elles sont fournies à titre indicatif et ne remplacent pas les prévisions officielles de services météorologiques professionnels.</p>
                </div>
            </section>

        </article>
        
    </main>
</div>

<?php get_footer(); ?>
