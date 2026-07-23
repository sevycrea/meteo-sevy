# 🎨 Design Studio — Guide des agents « conception de sites & apps »

## 🎯 Objectif

Mettre en place un **studio d'agents IA** capables de concevoir des sites web et des applications
**hors du commun** : innovants, **animés**, aux **couleurs qui donnent envie de rester**, et qui
**inspirent confiance**.

C'est une **boîte à outils générique et réutilisable** : elle ne dépend pas de Météo Sevy, mais le site
`sevy-creations.net` pourra servir de premier cas de démonstration.

> **Statut de ce document** : *stratégie documentée*. Il décrit **quels agents créer**, **quelles ressources
> externes brancher** et **comment les faire collaborer**. Il ne contient volontairement **aucun code de
> production** — la matérialisation des agents (`.claude/agents/*.md`) est décrite au chapitre 7 comme
> prochaine étape.

### 📊 Ce que le studio doit produire
- Une **direction artistique** forte et un concept mémorable pour chaque projet.
- Un **design system** concret (couleurs, typo, composants, tokens).
- Des **animations** et micro-interactions qui donnent envie d'explorer, sans nuire à la performance.
- Des **visuels** (héros, illustrations, textures) générés ou sourcés de façon cohérente.
- Une **intégration** propre, responsive, accessible et rassurante.

---

## 🧩 1. Le Studio : l'équipe d'agents

Le studio est une **chaîne d'agents spécialisés** pilotée par un **orchestrateur**. Chaque agent a une
mission claire, des **entrées**, des **sorties**, des **ressources externes branchées** et une **amorce de
prompt** (le noyau de son prompt système).

### 🎬 Directeur Artistique *(orchestrateur)*
- **Mission** : transformer le brief en **concept créatif fort** (« big idea »), coordonner les autres
  agents, arbitrer la cohérence globale.
- **Entrées** : brief (secteur, cible, émotion voulue, contraintes techniques, budget, exemples aimés/détestés).
- **Sorties** : note d'intention, moodboard textuel, concept, répartition des tâches entre agents.
- **Ressources** : les résultats de tous les autres agents.
- **Amorce de prompt** : *« Tu es directeur artistique d'un studio digital primé. À partir d'un brief, tu
  définis un concept unique et défendable, puis tu délègues aux agents spécialisés et garantis la cohérence
  entre identité, UX, motion et contenu. Tu refuses le générique : chaque projet a une signature. »*

### 🔭 Veille & Tendances
- **Mission** : nourrir l'innovation par des références et un benchmark concurrentiel.
- **Entrées** : secteur, positionnement, concurrents.
- **Sorties** : sélection de références commentées, tendances applicables, pièges à éviter.
- **Ressources** : `WebSearch` / `WebFetch` → **Awwwards, Godly, Land-book, Mobbin, Dribbble, Behance**.
- **Amorce** : *« Tu es veilleur design. Tu cites des références concrètes et récentes, tu expliques
  *pourquoi* elles fonctionnent, et tu proposes comment s'en inspirer sans copier. »*

### 🎨 Identité & Couleur
- **Mission** : définir la **palette** et la **typographie**, produire les **design tokens**.
- **Entrées** : concept du directeur artistique, émotion cible.
- **Sorties** : palette (avec rôles et contrastes), pairing typographique, tokens (`--color-*`, `--font-*`,
  échelles d'espacement/rayon/ombres).
- **Ressources** : **Google Fonts / Fontsource** (dont *variable fonts*), **Coolors**, **Realtime Colors**.
- **Amorce** : *« Tu es directeur couleur & typographie. Tu construis des palettes qui donnent envie de
  rester (harmonies chaudes/analogues + un accent), tu valides les contrastes AA/AAA, et tu livres des
  tokens réutilisables. »*

### 🧭 UX & Confiance
- **Mission** : structurer l'expérience et **installer la confiance**.
- **Entrées** : concept, cibles, objectifs de conversion.
- **Sorties** : arborescence, parcours utilisateurs, wireframes basse-fidélité, hiérarchie de l'information,
  liste de *trust signals*, exigences d'accessibilité (WCAG).
- **Ressources** : **Mobbin** (patterns UI réels), heuristiques de Nielsen, checklist WCAG 2.2.
- **Amorce** : *« Tu es UX designer orienté confiance. Tu clarifies les parcours, tu réduis la charge
  cognitive, et tu intègres des preuves (social proof, sécurité, transparence) à chaque étape sensible. »*

### 🖼️ UI Visuel
- **Mission** : produire les **maquettes haute-fidélité** et le **système de composants**.
- **Entrées** : tokens (Identité), wireframes (UX).
- **Sorties** : maquettes, grille, spacing, bibliothèque de composants.
- **Ressources** : **Tailwind CSS + shadcn/ui + Radix**, icônes **Lucide / Phosphor / Tabler**,
  **Figma (connecteur MCP)** pour aller maquette → tokens → code.
- **Amorce** : *« Tu es UI designer. Tu transformes tokens et wireframes en interfaces léchées, cohérentes,
  avec une grille rigoureuse et des composants réutilisables. »*

### ✨ Motion & Interaction
- **Mission** : donner vie à l'interface — **c'est le cœur du « animé » et du « wow »**.
- **Entrées** : maquettes UI, concept.
- **Sorties** : specs d'animations (déclencheur, **durée**, **easing**, séquence), micro-interactions,
  transitions de page, scroll-telling, fallback `prefers-reduced-motion`.
- **Ressources** : **GSAP** (gratuit, plugins inclus), **Motion One**, **Lenis** (smooth scroll),
  **Lottie / LottieFiles**, **Three.js / React Three Fiber** (3D/WebGL), **Rive** (interactif vectoriel).
- **Amorce** : *« Tu es motion designer. Tu conçois des animations qui guident l'œil et récompensent
  l'exploration, à 60 fps, avec une échelle cohérente de durées/easings et un repli accessibilité. »*

### 🌅 Direction Visuelle & Images IA
- **Mission** : créer les **visuels** (héros, illustrations, textures, arrière-plans) et garantir leur
  cohérence.
- **Entrées** : palette, concept, style souhaité.
- **Sorties** : visuels générés, prompts réutilisables, variantes, versions détourées/optimisées.
- **Ressources** *(payantes — clés API)* : **Replicate (Flux)**, **Images OpenAI**, **Stability AI**,
  **Ideogram** (texte net dans l'image), **remove.bg** (détourage), upscaler.
- **Amorce** : *« Tu es directeur visuel IA. Tu écris des prompts précis et cohérents avec la charte, tu
  produis des séries homogènes, et tu prépares les images (format, poids, détourage) pour le web. »*

### ✍️ Copy & Narration
- **Mission** : écrire des **textes qui donnent envie** et **rassurent**.
- **Entrées** : concept, cibles, ton de voix.
- **Sorties** : titres, accroches, CTA, microcopy, storytelling, versions FR.
- **Ressources** : ton de voix défini avec le directeur artistique (pas de dépendance externe requise).
- **Amorce** : *« Tu es concepteur-rédacteur. Tu écris clair, incarné et honnête ; tes CTA donnent envie de
  cliquer et ton microcopy rassure aux moments de friction. »*

### 🛠️ Intégration Front
- **Mission** : traduire les maquettes en **code** performant et responsive.
- **Entrées** : maquettes, tokens, specs de motion, visuels.
- **Sorties** : code (HTML/CSS/JS ou framework), composants intégrés, responsive.
- **Ressources** : **Vite**, **Tailwind**, la librairie de motion choisie.
- **Amorce** : *« Tu es intégrateur front. Tu produis un code fidèle aux maquettes, rapide, responsive et
  maintenable, en respectant les tokens et les specs d'animation. »*

### ✅ QA / Perf / Accessibilité / Confiance
- **Mission** : **auditer** avant livraison.
- **Entrées** : le site/app intégré.
- **Sorties** : rapport (perf, a11y, contraste, clavier, `reduced-motion`, RGPD/HTTPS/mentions légales),
  corrections prioritaires.
- **Ressources** : **Playwright / Chromium** *(déjà installé dans cet environnement : `/opt/pw-browsers`)*,
  **Lighthouse**, **axe-core**.
- **Amorce** : *« Tu es ingénieur QA design. Tu vérifies performance, accessibilité, cohérence et signaux de
  confiance, et tu listes des correctifs classés par impact. »*

> **🪶 Sous-ensemble minimal** pour démarrer léger : **Directeur Artistique + Identité & Couleur +
> UI Visuel + Motion + QA**. Les autres agents s'ajoutent quand le besoin grandit.

---

## 📦 2. Ressources externes (que brancher, et comment)

| Ressource | Usage | Coût | Comment la brancher |
|---|---|---|---|
| Google Fonts / Fontsource | Typographie, variable fonts | Gratuit | Lien `<link>` ou paquet npm (`@fontsource/*`) |
| Coolors / Realtime Colors | Génération & test de palettes | Gratuit | Web (agent Identité via WebFetch) |
| Lucide / Phosphor / Tabler | Icônes | Gratuit | npm (`lucide-react`, `@phosphor-icons/*`) |
| Tailwind CSS + shadcn/ui + Radix | Système UI / composants | Gratuit | npm + init CLI |
| GSAP | Animations avancées (+ plugins) | Gratuit | npm (`gsap`) |
| Motion One | Animations légères basées Web Animations API | Gratuit | npm (`motion`) |
| Lenis | Smooth scroll | Gratuit | npm (`lenis`) |
| Lottie / LottieFiles | Animations vectorielles JSON | Gratuit | npm (`lottie-web`) + fichiers `.json` |
| Three.js / React Three Fiber | 3D / WebGL, effets « hors du commun » | Gratuit | npm (`three`, `@react-three/fiber`) |
| Rive | Animations interactives vectorielles | Gratuit (offre) | npm (`@rive-app/*`) + éditeur Rive |
| Unsplash / Pexels (API) | Photos libres | Gratuit | Clé API (secret) |
| Lighthouse / axe-core | Audit perf & accessibilité | Gratuit | npm / CLI ; via Playwright |
| Playwright / Chromium | Captures & audit visuel | Gratuit | **Déjà installé** (`/opt/pw-browsers`) |
| **Replicate (Flux)** | **Génération d'images IA** | **Payant** | **Clé API (secret)** |
| **Images OpenAI** | **Génération / édition d'images** | **Payant** | **Clé API (secret)** |
| **Stability AI** | **Génération d'images** | **Payant** | **Clé API (secret)** |
| **Ideogram** | **Images avec texte net** | **Payant** | **Clé API (secret)** |
| **remove.bg** | **Détourage automatique** | **Payant** | **Clé API (secret)** |

> 🔐 **Sécurité** : toutes les clés API vivent dans des **secrets** (variables d'environnement, GitHub
> Actions Secrets), **jamais** en clair dans le dépôt.

---

## 🔌 3. Connecteurs MCP concrets

- **Figma** *(à connecter côté claude.ai — non installé par défaut)* : outils `get_design_context`,
  `get_code`, `get_variable_defs`, `get_screenshot`. Permet le passage **maquette → tokens → code** et sert
  d'échange avec des designers humains. C'est le connecteur le plus structurant pour l'agent **UI Visuel**.
- **Navigateur (Playwright)** : déjà disponible dans l'environnement — captures d'écran, tests visuels et
  audits d'accessibilité pour l'agent **QA**.
- **Génération d'images** : via **clés API** (Replicate / OpenAI / Stability / Ideogram) appelées depuis des
  scripts, ou via un **serveur MCP d'images** dédié si vous en connectez un.

---

## 🔄 4. Flux de collaboration

```
        Brief
          │
          ▼
   🎬 Directeur Artistique  ── définit le concept ──┐
          │                                          │ (arbitrage & cohérence
   ┌──────┼───────────────┐                          │  tout au long)
   ▼      ▼               ▼                           │
 🔭 Veille  🎨 Identité   🧭 UX & Confiance           │
          └──────┬────────┘                          │
                 ▼                                    │
            🖼️ UI Visuel                              │
   ┌─────────────┼──────────────┐                     │
   ▼             ▼              ▼                      │
 ✨ Motion   🌅 Images IA    ✍️ Copy                   │
          └──────┬────────┘                           │
                 ▼                                     │
          🛠️ Intégration Front                        │
                 ▼                                     │
      ✅ QA / Perf / A11y / Confiance ────────────────┘
                 │
                 ▼
            Itération / Livraison
```

- **En parallèle (∥)** : Veille ∥ Identité ∥ UX, puis Motion ∥ Images IA ∥ Copy.
- **En séquentiel** : concept → UI → intégration → QA.
- **Boucle** : le rapport QA relance les agents concernés jusqu'à validation.

---

## 🌟 5. Principes de design (les 4 objectifs → règles actionnables)

### Innovant / hors du commun
- Partir d'un **concept fort** et d'une **signature d'interaction** unique (un geste, un effet, un rituel).
- Oser un **layout non conventionnel** *mais maîtrisé* (grille cassée, asymétrie contrôlée).
- Doser **WebGL / scroll-telling** : au service du récit, jamais gratuit.

### Animé (donne envie d'aller plus loin)
- Combiner **micro-interactions** + **entrées au scroll** + **transitions de page**.
- Garder une **échelle cohérente** de durées et d'easings (ex. 150/250/400 ms, easing standard).
- Viser **60 fps** (animer `transform`/`opacity`), et **toujours** un repli `prefers-reduced-motion`.

### Couleurs invitantes (donnent envie de rester)
- Harmonies **chaudes / analogues** + **1 accent** vif pour l'action.
- Respecter les **contrastes AA/AAA** (lisibilité = confort = temps passé).
- Soigner le **mode sombre**, appliquer le **dosage 60-30-10** (base / secondaire / accent).

### Confiance
- **Hiérarchie claire**, promesse compréhensible en 5 secondes.
- **Preuves** (avis, logos, chiffres), **sécurité visible** (HTTPS, mentions, RGPD).
- **Cohérence** de bout en bout, **performance** et **accessibilité** (un site rapide et lisible rassure).
- **Ton honnête** : pas de sur-promesse, pas de *dark patterns*.

---

## 🚀 6. Comment utiliser le studio (workflow type)

1. **Rédiger le brief** : secteur, cible, émotion voulue, contraintes, exemples aimés/détestés, budget.
2. Lancer le **Directeur Artistique** → il produit le concept et délègue.
3. Laisser tourner les agents selon le **flux du chapitre 4** (parallèle puis séquentiel).
4. Assembler avec **Intégration Front**, auditer avec **QA**, **itérer**.
5. Décliner sur un cas réel — p. ex. la refonte de `sevy-creations.net` consommant les JSON du dépôt.

---

## 🧱 7. Prochaine étape — matérialiser les agents

Quand vous validez cette stratégie, chaque agent devient un fichier `.claude/agents/<nom>.md` :

```markdown
---
name: directeur-artistique
description: Orchestrateur créatif. Transforme un brief en concept fort et coordonne le studio.
tools: ["*"]            # ou une liste restreinte selon le rôle
model: opus             # opus pour le créatif/arbitrage ; sonnet/haiku pour l'exécution
---

Tu es directeur artistique d'un studio digital primé. À partir d'un brief, tu définis un
concept unique et défendable, puis tu délègues aux agents spécialisés (Identité, UX, UI,
Motion, Images IA, Copy, Intégration, QA) et tu garantis la cohérence. Tu refuses le
générique : chaque projet a une signature.
```

- **Orchestration** : soit le `Directeur Artistique` appelle les autres via l'outil *Agent* (en parallèle
  quand c'est possible), soit on décrit un **Workflow** déterministe (fan-out Identité/UX/Veille, puis UI,
  puis Motion/Images/Copy, puis Intégration → QA en boucle).
- **Choix des modèles** : *opus* pour le concept et l'arbitrage ; modèles plus rapides pour l'intégration et
  les tâches mécaniques.

> Créer ces fichiers `.claude/agents/*.md` (et éventuellement le Workflow) fera l'objet d'une **étape
> suivante**, sur votre feu vert.

---

## ✅ Récapitulatif

| Objectif | Agents porteurs | Ressources clés |
|---|---|---|
| Innovant | Directeur Artistique, Veille, Motion | Awwwards/Godly, Three.js, Rive |
| Animé | Motion, Intégration | GSAP, Motion One, Lenis, Lottie |
| Couleurs invitantes | Identité & Couleur, UI Visuel | Google Fonts, Coolors, tokens |
| Confiance | UX & Confiance, QA | WCAG, Lighthouse, axe-core, Playwright |
| Visuels | Direction Visuelle & Images IA | Replicate/Flux, Ideogram, remove.bg *(payant)* |
