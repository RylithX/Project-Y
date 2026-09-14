# Architecture & Design Report: 3rd Unified Web Control Center (`social.html`) & Interactive Background Canvas Engine

**Target Project**: `/storage/emulated/0/discord-bot`  
**Artifact**: Architecture, Design System & Canvas Engine Survey  
**Author**: Explorer Survey Agent 2  
**Date**: 2026-09-02  

---

## 1. Observation

### 1.1 Existing Aesthetic & Codebase Survey
Direct source inspection of existing web interfaces across `/storage/emulated/0/discord-bot` reveals two distinct design paradigms currently operating in parallel:

#### A. Drafting Desk Aesthetic (`dashboard.html`, lines 8–20, 21–86, 93–140)
- **Typography**:
  ```css
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
  ```
  - Display / Headings: `'Playfair Display', serif` (elegant physical drafting desk feel).
  - UI & Body: `'Inter', system-ui, sans-serif` (clean editorial typography).
  - Code & Telemetry: `'JetBrains Mono', 'Consolas', monospace`.
- **Color Palette & CSS Variables (`dashboard.html:11-20`)**:
  ```css
  :root {
      --bg: #e8e8e4;
      --bg-warm: #e2e2dc;
      --paper: rgba(252, 252, 248, 0.78);
      --paper-solid: #fafaf6;
      --ink: #2a2a2a;
      --ink-muted: #6b6b6b;
      --ink-faint: #9a9a9a;
      --accent-sage: #8a9a8a;
      --accent-steel: #7a8a9a;
      --accent-clay: #b8a898;
      --accent-gold: #c4a882;
      --grid: rgba(100, 130, 100, 0.08);
      --shadow-soft: rgba(0, 0, 0, 0.06);
      --shadow-medium: rgba(0, 0, 0, 0.10);
      --shadow-deep: rgba(0, 0, 0, 0.18);
      --transition-smooth: cubic-bezier(0.25, 0.46, 0.45, 0.94);
      --transition-bounce: cubic-bezier(0.34, 1.56, 0.64, 1);
      --transition-dramatic: cubic-bezier(0.16, 1, 0.3, 1);
  }
  ```
- **Physical Desk & Drafting Visual Motifs**:
  - **Grid Surface (`dashboard.html:22`)**: `linear-gradient(90deg, var(--grid) 1px, transparent 1px), linear-gradient(0deg, var(--grid) 1px, transparent 1px); background-size: 40px 40px;`
  - **Tactile Paper Drawers & Clips (`dashboard.html:36-86`)**: Slide-out paper sheets with metallic clip (`.paper-clip`), border radius `6px`, realistic shadows (`0 24px 56px rgba(0,0,0,0.25)`), and header titles.
  - **Physical Desk Objects (`dashboard.html:93-132`)**: Drafting compass with brass joint, wooden pencil with graphite tip, drafting ruler with millimeter markings, triangular ruler, eraser, and Polaroid photo frame.

#### B. Dark Studio Suite Aesthetic (`studio.html`, lines 10–82, 109–250, 267–333)
- **Primary Studio Dark Palette (`studio.html:10-31`)**:
  ```css
  :root {
      --sidebar-bg: #0f0f0f;
      --sidebar-active: #e85d5d;
      --sidebar-text: #888;
      --sidebar-text-active: #fff;
      --main-bg: #1a1a1a;
      --card-bg: #252525;
      --card-border: #333;
      --text-primary: #fff;
      --text-secondary: #aaa;
      --text-muted: #666;
      --accent: #e85d5d;
      --accent-soft: rgba(232, 93, 93, 0.15);
      --empty-border: #444;
      --input-bg: #1e1e1e;
      --input-border: #333;
      --input-focus: #e85d5d;
      --chat-top-bg: #202020;
      --chat-bubble-ai: #282828;
      --chat-bubble-user: #382525;
      --chat-composer-bg: #1e1e1e;
  }
  ```
- **Studio Multi-Theme Matrix (`studio.html:33-81`)**:
  - `data-theme="sage"`: Forest sage dark (`--sidebar-bg: #222722; --main-bg: #2b332b; --accent: #8a9a8a`)
  - `data-theme="blueprint"`: Deep drafting blueprint dark (`--sidebar-bg: #071322; --main-bg: #0c1e36; --card-bg: #122a4a; --accent: #38bdf8`)
  - `data-theme="clay"`: Warm terracotta dark (`--sidebar-bg: #1e1714; --main-bg: #2a201c; --accent: #b87a54`)
  - `data-theme="emerald"`: Emerald studio dark (`--sidebar-bg: #0f1c15; --main-bg: #16271e; --accent: #2e8b57`)
  - `data-theme="rose"`: Crimson velvet dark (`--sidebar-bg: #1f1113; --main-bg: #2b181b; --accent: #e06c75`)
  - `data-theme="ocean"`: Oceanic azure dark (`--sidebar-bg: #0d1a24; --main-bg: #132433; --accent: #3a7bd5`)
  - `data-theme="amber"`: Antique brass amber dark (`--sidebar-bg: #1f1b10; --main-bg: #2b2516; --accent: #d4a017`)
- **Studio Modular Components**:
  - **Modular Cards (`.char-card`, `.bot-row-card`, `.tuning-accordion`)**: Deep elevation (`0 6px 20px rgba(0,0,0,0.4)`), sleek hover lift (`translate3d(0, -3px, 0)`), bordered frames.
  - **Telemetry & Status Badges**: Status indicators (`.latest-badge`, online/offline dot indicators, interaction counters).
  - **Navigation & Switcher**: Top action bar with quick swatches and back links (`.top-action-bar`, `.back-to-desk-link`).

#### C. Backend Routing & Social Subsystem (`bot.py:8085-8275`, `social/config.py:28-195`)
- Route `/api/social/status`: Returns configured status for X/Twitter, Instagram, Photon, and Media Queue.
- Route `/api/social/settings` (GET / POST): Persists Instagram session ID, proxy, personality, tone sliders (`sass_level`, `affection_level`, `chaos_level`, `energy_level`), and automation flags (`auto_reply_dms`, `watch_follower_stories`, `auto_like_stories`) to `data/instagram_config.json`.
- Navigation routes: `bot.py` currently serves `/dashboard`, `/studio`, `/chat`, `/vrm_viewer.html`.

---

## 2. Logic Chain

### 2.1 Hybrid Design System: Drafting Desk × Dark Studio
To synthesize a cohesive 3rd control center (`social.html`), the interface must bridge the physical tactile charm of the Drafting Desk with the dark control density of the Studio Suite:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP NAVIGATION BAR: Window Dots | Page Title | Animated BG Switcher | Theme Swatches    │
├───────────────────┬────────────────────────────────────────────┬───────────────────────┤
│ LEFT DECK         │ CENTER VIEWPORT                            │ RIGHT DRAWER          │
│ - Account Switcher│ - Active Session Telemetry Card            │ - Tactile Paper Panel │
│ - Platform Matrix │ - Real-Time Logs & Activity Stream         │ - Tone & Sass Sliders │
│ - Token / Session │ - Direct Action Drawer (Post, DM, Sync)    │ - Example Responses   │
│   Input Modal     │ - Queue Monitor & Automation Toggles       │ - Memory Inspector    │
└───────────────────┴────────────────────────────────────────────┴───────────────────────┘
```

#### Unified Design Tokens (`CSS Variables`)
```css
:root {
  /* Surface & Depth */
  --desk-dark-base: #121316;
  --desk-panel-bg: rgba(26, 28, 32, 0.88);
  --desk-card-bg: rgba(36, 39, 45, 0.75);
  --desk-paper-sheet: #fbfbf7;
  --desk-paper-ink: #1f2022;
  
  /* Precision Borders & Metallic Accents */
  --brass-primary: #d4a86a;
  --brass-glow: rgba(212, 168, 106, 0.25);
  --steel-accent: #788896;
  --steel-border: rgba(120, 136, 150, 0.25);
  --blueprint-line: rgba(56, 189, 248, 0.12);
  --blueprint-cyan: #38bdf8;
  
  /* Status Semantics */
  --status-active: #10b981;
  --status-active-glow: rgba(16, 185, 129, 0.25);
  --status-idle: #f59e0b;
  --status-expired: #ef4444;
  --status-expired-glow: rgba(239, 68, 68, 0.25);
  
  /* Physical Shadows */
  --elevation-low: 0 2px 8px rgba(0, 0, 0, 0.35);
  --elevation-medium: 0 8px 24px rgba(0, 0, 0, 0.45);
  --elevation-high: 0 16px 48px rgba(0, 0, 0, 0.60);
}
```

---

### 2.2 Interactive Animated Background Engine Architecture

The background engine runs on a dedicated, fixed HTML5 `<canvas id="bgCanvas">` rendered behind the UI (`z-index: 0; pointer-events: none;`).

```
                              ┌─────────────────────────────┐
                              │  Background Engine Manager  │
                              └──────────────┬──────────────┘
                                             │
               ┌─────────────────────────────┼─────────────────────────────┐
               ▼                             ▼                             ▼
   ┌───────────────────────┐     ┌───────────────────────┐     ┌───────────────────────┐
   │ 1. Clockwork Gears    │     │ 2. Blueprint Grid     │     │ 3. Studio Dark Pulse  │
   │ - Multi-gear train    │     │ - Coordinate crosshair│     │ - Sinusoidal gradient │
   │ - Calibrated ratios   │     │ - Rotating compass arc│     │ - Constellation dust  │
   │ - Involute tooth poly │     │ - Drafting lines & dim│     │ - Distance node graph │
   └───────────────────────┘     └───────────────────────┘     └───────────────────────┘
                                             │
                                             ▼
                                 ┌───────────────────────┐
                                 │ 4. Minimal Slate      │
                                 │ - Subtle matte grain  │
                                 │ - Low power / static  │
                                 └───────────────────────┘
```

#### Engine A: Clockwork Gears Kinematics & Geometry Formulation

1. **Gear Tooth Geometry**:
   A gear $G$ is parameterized by $N$ (number of teeth), module $m$ (tooth size scale), and center $(x_0, y_0)$:
   - **Pitch Radius**: $R_p = \frac{N \cdot m}{2}$
   - **Addendum (Tooth Tip Radius)**: $R_a = R_p + 1.0 \cdot m$
   - **Dedendum (Root Valley Radius)**: $R_d = R_p - 1.2 \cdot m$
   - **Angular Pitch per Tooth**: $\theta_p = \frac{2\pi}{N}$

2. **Involute / Trapezoidal Tooth Polygon Generation**:
   For each tooth index $i \in [0, N-1]$, let the base tooth angle be $\phi_i = i \cdot \theta_p + \theta(t)$.
   Each tooth profile is traced through four discrete angular subdivisions:
   - Root Start: $\alpha_1 = \phi_i - 0.22 \cdot \theta_p \implies (x, y) = (x_0 + R_d \cos \alpha_1, y_0 + R_d \sin \alpha_1)$
   - Tip Crest Left: $\alpha_2 = \phi_i - 0.10 \cdot \theta_p \implies (x, y) = (x_0 + R_a \cos \alpha_2, y_0 + R_a \sin \alpha_2)$
   - Tip Crest Right: $\alpha_3 = \phi_i + 0.10 \cdot \theta_p \implies (x, y) = (x_0 + R_a \cos \alpha_3, y_0 + R_a \sin \alpha_3)$
   - Root End: $\alpha_4 = \phi_i + 0.22 \cdot \theta_p \implies (x, y) = (x_0 + R_d \cos \alpha_4, y_0 + R_d \sin \alpha_4)$

3. **Interlocking Center Distance & Speed Ratio Kinematics**:
   Two gears $G_1(x_1, y_1, N_1)$ and $G_2(x_2, y_2, N_2)$ with identical module $m$ mesh smoothly without clipping if:
   $$\text{Center Distance } D = R_{p1} + R_{p2} = \frac{(N_1 + N_2) \cdot m}{2}$$
   $$\text{Rotational Velocity Ratio } \frac{\omega_2}{\omega_1} = -\frac{N_1}{N_2}$$

4. **Mesh Phase Contact Equation**:
   Let the contact vector angle from $G_1$ to $G_2$ be $\phi_{\text{mesh}} = \operatorname{atan2}(y_2 - y_1, x_2 - x_1)$.
   To ensure tooth enters valley at the exact contact line:
   $$\theta_2(t) = -\frac{N_1}{N_2} \left(\theta_1(t) - \phi_{\text{mesh}}\right) + \phi_{\text{mesh}} + \pi + \frac{\pi}{N_2}$$

5. **Multi-Gear Interlocking Train Configuration**:
   ```javascript
   const GEAR_TRAIN = [
     { id: 'master', xRatio: 0.85, yRatio: 0.25, N: 32, m: 7.0, isMaster: true, speed: 0.008, color: 'brass' },
     { id: 'follower_1', parentId: 'master', angle: Math.PI * 0.72, N: 20, m: 7.0, color: 'steel' },
     { id: 'follower_2', parentId: 'follower_1', angle: Math.PI * 0.35, N: 28, m: 7.0, color: 'copper' },
     { id: 'pinion', parentId: 'master', angle: -Math.PI * 0.65, N: 14, m: 7.0, color: 'steel' },
     { id: 'large_wheel', parentId: 'pinion', angle: -Math.PI * 0.20, N: 40, m: 7.0, color: 'brass' }
   ];
   ```

6. **Depth, Shading & Mechanical Cutouts**:
   - Metallic Shading: Dynamic linear/radial gradients mimicking brushed brass (`#d4af37` $\to$ `#85580a`), burnished steel (`#64748b` $\to$ `#1e293b`), and antique copper (`#b45309` $\to$ `#78350f`).
   - Cutout Windows: Circular or teardrop spoke apertures cut out using `ctx.arc()` with `ctx.stroke()` and counter-rotating highlights.
   - Central Hub & Brass Rivet: Concentric brass washer and center fastener with specular reflection highlight.

---

#### Engine B: Drafting Blueprint Grid Architecture
1. **Dynamic Grid**: Primary grid (80px squares in `rgba(56, 189, 248, 0.08)`) and secondary subdivision grid (20px squares in `rgba(56, 189, 248, 0.03)`).
2. **Coordinate Axes & Crosshairs**: Slowly drifting intersection crosshairs with millimeter tic marks and numeric technical dimensioning labels (e.g. `X: 420.50mm`, `Y: 108.20mm`, `TOL ±0.02`).
3. **Compass Drafting Sweep**: Concentric dashed circles (`ctx.setLineDash([4, 6])`) with an animated rotating compass needle drawing radial arcs and tangent guide lines.

---

#### Engine C: Studio Dark Pulse Architecture
1. **Sinusoidal Gradient Breathing**:
   $$L(t) = 0.15 + 0.08 \cdot \sin(2\pi \cdot f \cdot t)$$
   Deep dark radial gradient anchored at viewport center pulsing between obsidian and dark crimson/azure.
2. **Constellation Particle Graph**:
   - 45 floating particles moving with randomized velocities $\vec{v} \in [-0.3, +0.3]\text{px/frame}$.
   - Distance calculation $d = \sqrt{(x_i - x_j)^2 + (y_i - y_j)^2}$.
   - For $d < 110\text{px}$, render connecting lines with opacity $\alpha = 1.0 - (d / 110)$.

---

#### Engine D: Minimal Slate Architecture
1. Clean, static dark charcoal vignette (`linear-gradient(135deg, #141518 0%, #0d0e10 100%)`).
2. Zero continuous render loops (`requestAnimationFrame` throttled / idle) to maximize battery life on mobile devices.

---

### 2.3 State Persistence & Interactive Controls Architecture
The background engine state must seamlessly persist across navigation and reload via `localStorage`:

```javascript
const BG_CONFIG_KEY = 'unified_control_bg_settings';

const defaultBgSettings = {
  theme: 'gears',      // 'gears' | 'blueprint' | 'pulse' | 'slate'
  speed: 1.0,          // 0.2x to 3.0x multiplier
  opacity: 0.85,       // 0.10 to 1.00 alpha
  fpsLimit: 60         // 30 | 60 | uncapped
};

function saveBgSettings(settings) {
  localStorage.setItem(BG_CONFIG_KEY, JSON.stringify(settings));
}

function loadBgSettings() {
  try {
    const raw = localStorage.getItem(BG_CONFIG_KEY);
    return raw ? { ...defaultBgSettings, ...JSON.parse(raw) } : defaultBgSettings;
  } catch(e) {
    return defaultBgSettings;
  }
}
```

---

### 2.4 Hybrid UI Structure for `social.html`
The recommended DOM layout organizes the page into standard modular zones:

```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <!-- Google Fonts: Playfair Display, Inter, JetBrains Mono -->
</head>
<body>
  <!-- Fixed Background Canvas -->
  <canvas id="bgCanvas" class="bg-canvas"></canvas>

  <!-- Top Action & Navigation Bar -->
  <header class="top-nav-bar">
    <div class="nav-brand">
      <div class="window-dots">
        <span class="dot dot-red"></span>
        <span class="dot dot-yellow"></span>
        <span class="dot dot-green"></span>
      </div>
      <h1 class="nav-title">Unified Control Center — Social Suite</h1>
    </div>
    
    <!-- Background Engine Controls -->
    <div class="bg-engine-controls">
      <select id="bgThemeSelect" class="bg-select">
        <option value="gears">⚙️ Clockwork Gears</option>
        <option value="blueprint">📐 Drafting Blueprint</option>
        <option value="pulse">✨ Studio Dark Pulse</option>
        <option value="slate">⬛ Minimal Slate</option>
      </select>
      <div class="bg-slider-wrap">
        <label for="bgSpeed">Speed</label>
        <input type="range" id="bgSpeed" min="0.2" max="3" step="0.1" value="1">
      </div>
      <div class="bg-slider-wrap">
        <label for="bgOpacity">Opacity</label>
        <input type="range" id="bgOpacity" min="0.1" max="1" step="0.05" value="0.85">
      </div>
    </div>

    <!-- Cross-Page Navigation Links -->
    <div class="nav-links">
      <a href="/dashboard" class="nav-link">Drafting Desk ↗</a>
      <a href="/studio" class="nav-link">Studio Suite ↗</a>
    </div>
  </header>

  <!-- Main Multi-Column Control Surface -->
  <main class="control-surface-layout">
    <!-- Section 1: Telemetry & Status Badges -->
    <section class="telemetry-deck">
      <div class="telemetry-card">
        <div class="telemetry-header">Instagram Node</div>
        <div class="status-badge active" id="instaStatus">🟢 Active Connected</div>
        <div class="telemetry-stat" id="instaUser">@ur._.yunaa</div>
      </div>
      <div class="telemetry-card">
        <div class="telemetry-header">X / Twitter Gateway</div>
        <div class="status-badge idle" id="xStatus">🟡 Idle</div>
        <div class="telemetry-stat" id="xUser">--</div>
      </div>
      <div class="telemetry-card">
        <div class="telemetry-header">Media Queue</div>
        <div class="status-badge" id="queueStatus">📦 0 Pending</div>
        <div class="telemetry-stat">Auto-Sync 4s</div>
      </div>
    </section>

    <!-- Section 2: Session ID & Auth Credentials Deck -->
    <section class="auth-credential-deck">
      <!-- Session input forms for Instagram, Discord, X -->
    </section>

    <!-- Section 3: Tactile Persona & Tone Drawer (Drafting Desk Style) -->
    <aside class="tactile-paper-drawer" id="personaDrawer">
      <div class="paper-clip"></div>
      <div class="paper-header">📸 Persona &amp; Tone Suite</div>
      <!-- Sliders, textareas, example responses -->
    </aside>
  </main>
</body>
</html>
```

---

## 3. Caveats

1. **Hardware Acceleration & Pixel Ratio**:
   - On high-DPI displays (retina / mobile devices), `canvas.width` and `canvas.height` must be multiplied by `window.devicePixelRatio` while CSS dimensions remain 100vw/100vh. Failing to do this causes blurry gear rendering.
2. **Mobile CPU/Battery Throttling**:
   - When the user selects `slate` or when the tab is blurred / inactive (`document.hidden`), the `requestAnimationFrame` loop must pause or drop to an event-driven tick to conserve mobile battery.
3. **Session ID Security & Storage**:
   - `localStorage` handles client-side UI persistence, but authentication tokens must also sync with `data/instagram_config.json` and `data/config.json` via `/api/social/settings` for background bot daemons to utilize them.

---

## 4. Conclusion

1. **Aesthetic Synthesis**: The 3rd control center (`social.html`) should use a hybrid dark slate glassmorphism container (`rgba(26, 28, 32, 0.88)`) accented with Drafting Desk brass fasteners (`#d4a86a`), steel borders (`#788896`), blueprint grid overlays, and slide-out tactile paper panels (`#fbfbf7`) with realistic paper clips.
2. **Canvas Background Engine**: The 4-mode engine (Clockwork Gears, Drafting Blueprint, Studio Dark Pulse, Minimal Slate) must be governed by an object-oriented `BackgroundEngine` class that handles resize events, calibrated gear ratio kinematics, tooth polygon rendering, and `localStorage` persistence.
3. **Navigation & Routes**: The page must be accessible via `/social`, `/social.html`, and `/control` in `bot.py`, with top-bar hyperlinks jumping to `/dashboard` and `/studio`.

---

## 5. Verification Method

To verify the implementation of this architectural specification:

### 5.1 Verification Commands
```bash
# 1. Verify that social.html exists and contains all required structural identifiers
test -f /storage/emulated/0/discord-bot/social.html && echo "social.html exists"

# 2. Check for the existence of the Background Canvas and Gears Engine Script
grep -n "bgCanvas" /storage/emulated/0/discord-bot/social.html
grep -n "Clockwork" /storage/emulated/0/discord-bot/social.html
grep -n "bgThemeSelect" /storage/emulated/0/discord-bot/social.html

# 3. Check for Flask route registration in bot.py
grep -n "@app.route(\"/social\")" /storage/emulated/0/discord-bot/bot.py
grep -n "@app.route(\"/social.html\")" /storage/emulated/0/discord-bot/bot.py

# 4. Verify API response from Flask social status and settings
curl -s http://localhost:5000/api/social/status | grep '"ok"'
```

### 5.2 Invalidation Conditions
- Any gear teeth visual clipping or desynchronized rotational speeds.
- Loss of background switcher selection upon page refresh (`localStorage` failure).
- Broken or missing navigation routes between `/dashboard`, `/studio`, and `/social`.
