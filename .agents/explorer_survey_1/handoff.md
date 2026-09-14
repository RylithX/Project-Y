# Comprehensive Investigation & Architectural Survey Report

**Target Milestone**: 3rd Unified Web Control Center (`social.html`) & Backend Wiring  
**Working Directory**: `/storage/emulated/0/discord-bot`  
**Report Artifact**: `/storage/emulated/0/discord-bot/.agents/explorer_survey_1/handoff.md`  
**Date**: 2026-09-02  

---

## 1. Observation

### 1.1 Backend & Server Architecture (`bot.py`)

#### A. Flask Initialization and Imports
- **Location**: `bot.py:236` and `bot.py:7737`
- **Code Snippet**:
  ```python
  # Line 236
  from flask import Flask, request, jsonify, render_template_string, send_file, send_from_directory

  # Line 7737
  app = Flask(__name__)
  ```

#### B. Threading and Lifecycle Architecture
- **Location**: `bot.py:8956-8992`
- **Port Discovery and Server Execution**:
  ```python
  # Lines 8956-8973
  def find_available_port(start_port=5000, max_tries=30):
      import socket
      for p in range(start_port, start_port + max_tries):
          try:
              with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                  s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                  s.bind(('0.0.0.0', p))
                  return p
          except Exception:
              continue
      return start_port

  def run_flask():
      desired_port = int(config.get("dashboard_port", 5000))
      port = find_available_port(desired_port)
      print(f"[MAIN] Web Dashboard online at http://0.0.0.0:{port}")
      app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

  # Lines 8977-8992
  if __name__ == "__main__":
      _acquire_instance_lock()
      ...
      threading.Thread(target=run_flask, daemon=True).start()
      print("[MAIN] Web Dashboard running on http://0.0.0.0:5000")
  ```
- **State Synchronization**: `bot.py` utilizes a global reentrant lock `state_lock = threading.Lock()` around global config and persona updates to ensure thread safety across Flask requests and Discord event loop tasks.

#### C. Existing HTML Page Routing Patterns
- **Studio Suite Routes** (`bot.py:7739-7754`):
  ```python
  @app.route("/")
  @app.route("/studio")
  @app.route("/studio.html")
  @app.route("/chat")
  @app.route("/chat.html")
  @app.route("/index.html")
  @app.route("/home.html")
  def studio_index():
      html_path = os.path.join(SCRIPT_DIR, "index.html")
      if not os.path.exists(html_path):
          html_path = os.path.join(SCRIPT_DIR, "dashboard.html")
      try:
          with open(html_path, "r", encoding="utf-8") as f:
              return render_template_string(f.read())
      except Exception as e:
          return f"HTML not found at {html_path}. Error: {e}", 500
  ```
- **Drafting Desk Routes** (`bot.py:7756-7770`):
  ```python
  @app.route("/dashboard")
  @app.route("/dashboard.html")
  @app.route("/drafting")
  @app.route("/drafting.html")
  @app.route("/desk")
  def drafting_page():
      html_path = os.path.join(SCRIPT_DIR, "dashboard.html")
      if not os.path.exists(html_path):
          html_path = os.path.join(SCRIPT_DIR, "index.html")
      try:
          with open(html_path, "r", encoding="utf-8") as f:
              return render_template_string(f.read())
      except Exception as e:
          return f"Drafting template read error: {e}", 500
  ```
- **Static File Fallback Catch-All** (`bot.py:8949-8954`):
  ```python
  @app.route('/<path:path>')
  def send_static_file(path):
      try:
          return send_from_directory(SCRIPT_DIR, path)
      except Exception as e:
          return str(e), 404
  ```

#### D. Social Media API Endpoints in `bot.py`
1. `GET /api/social/status` (`bot.py:8086-8125`): Returns real-time health and connection status for X, Instagram, Photon, and Media Queue.
2. `POST /api/social/x/post` (`bot.py:8127-8168`): Publishes text and media to X (Twitter) with vision-based caption generation.
3. `POST /api/social/insta/post` (`bot.py:8169-8210`): Publishes photos/reels to Instagram with multimodal analysis.
4. `GET / POST /api/social/settings` (`bot.py:8211-8275`): Reads and persists configuration for X, Instagram, and Photon. For Instagram, routes settings directly through `save_instagram_config()`.
5. `POST /api/photon/webhook` (`bot.py:8277-8300`): Ingests multi-platform webhook events from Photon Gateway.

---

### 1.2 Session Handling & Storage Engine

#### A. Instagram Configuration & Session Files
- **File 1: `data/instagram_config.json`**:
  - Contains Instagram-specific credentials, session ID, behavioral style, personality, and automation toggles (`enabled`, `username`, `session_id`, `session_file`, `proxy`, `style`, `tone`, `sass_level`, `affection_level`, `chaos_level`, `energy_level`, `auto_reply_dms`, `auto_approve_follow_requests`, `watch_follower_stories`, `auto_like_stories`, `auto_respond_likes`, `story_check_interval_minutes`, `example_responses`).
- **File 2: `data/insta_session.json`**:
  - Contains dumped Instagrapi / REST session settings (cookies, authorization headers, device UUIDs, tokens).
- **Configuration Manager (`social/config.py:79-195`)**:
  - `load_instagram_config()`: Isolates Instagram persona configuration from Discord bot personas to avoid context corruption. Parses `session_id` from JSON, environment variables, or config overrides.
  - `save_instagram_config()`: Atomically persists configuration updates to `data/instagram_config.json`.
- **Client Session Restoration (`social/insta_client.py:197-243`)**:
  - Prioritizes loading cached settings from `data/insta_session.json`.
  - If cached session is missing or expired, executes `cl.login_by_sessionid(raw_sid)` using the unquoted `session_id` string, then dumps updated session settings to disk.

#### B. Multi-Platform Session Structures
- **Instagram**: Cookie-based `sessionid` (format: `<user_id>:<token_hash>:<timestamp>:<signature>`).
- **Discord**: Bot token (format: `<bot_id>.<timestamp_hash>.<hmac_signature>`) or user token.
- **X (Twitter)**: OAuth 2.0 Bearer Token, API Key + Secret, Access Token + Secret, or Client ID/Secret.
- **Photon**: API Key + Gateway Endpoint URL (`https://api.photon.codes/v1`).

---

### 1.3 Existing Page Architectures & Aesthetics

#### A. Drafting Desk (`dashboard.html`)
- **Visual Aesthetic**:
  - Tactile architectural workspace, paper textures, subtle drop shadows, and drafting tools.
  - Linear-gradient architectural grid (`.desk-surface` with `background-image: linear-gradient(90deg, var(--grid) 1px, transparent 1px), linear-gradient(0deg, var(--grid) 1px, transparent 1px)`).
  - Tactile floating paper cards (`.paper` with `.paper-clip` and paper edges: `.paper-top`, `.paper-bottom`, `.paper-left`, `.paper-right`, `.paper-social`, `.paper-bm`).
  - Interactive desk objects: `.compass`, `.pencil`, `.ruler`, `.eraser`, `.triangle`, `.coffee-cup`, `.sticky-note`, `.polaroid`, `.glasses`.
- **Color Variables**:
  `--bg: #e8e8e4; --paper: rgba(252, 252, 248, 0.78); --paper-solid: #fafaf6; --ink: #2a2a2a; --ink-muted: #6b6b6b; --accent-sage: #8a9a8a; --accent-steel: #7a8a9a; --accent-gold: #c4a882; --grid: rgba(100, 130, 100, 0.08);`
- **Navigation**:
  - Line 155: `<a href="/studio" ... title="Open Persona Studio">Studio ↗</a>` in top header bar.

#### B. Studio Suite (`studio.html` / `index.html`)
- **Visual Aesthetic**:
  - Sleek dark-mode control center, vertical navigation sidebar (width 64px), modular card grids, status telemetry pills, drawer panels, and live chat composer.
  - Multi-theme switching engine (`dark`, `sage`, `blueprint`, `clay`, `emerald`, `rose`, `ocean`, `amber`) with translucent paint bleed transition animations.
  - High-density telemetry cards, real-time counters, search filters, and modal overlays.
- **Navigation**:
  - Line 1230-1235: `<a href="/dashboard" class="sidebar-item" id="nav-desk"><span class="sidebar-label">Drafting ↗</span></a>`
  - Lines 1277-1280, 1311, 2427: `<a href="/dashboard" class="back-to-desk-link"><span>Drafting Desk ↗</span></a>` and `<a href="/dashboard" class="btn-primary">Drafting Desk ↗</a>`

#### C. Shared Navigation Matrix
Current cross-links connect `/dashboard` and `/studio`. The new page (`social.html`) requires a 3-way navigation hub:
- **Drafting Desk** (`/dashboard`) ⇄ **Studio Suite** (`/studio`) ⇄ **Social Control Center** (`/social`).

---

## 2. Logic Chain

1. **Seamless Integration Requirement**:
   - `ORIGINAL_REQUEST.md` mandates a standalone web page `social.html` serving under clean URL routes (`/social`, `/social.html`, `/control`) that integrates Drafting Desk tactile aesthetics with Studio Suite dark telemetry.
   - Observation shows `bot.py` routes HTML pages using `render_template_string` or `send_from_directory` with explicit endpoints at lines 7739-7770.
   - Therefore, `bot.py` must register `@app.route("/social")`, `@app.route("/social.html")`, and `@app.route("/control")` pointing to `social.html`.

2. **Aesthetic Hybridization Logic**:
   - Drafting Desk contributes tactile paper texture, architectural grid background, brass/steel accents, and floating desk object widgets.
   - Studio Suite contributes dark obsidian/slate backdrop options, 64px compact icon sidebar, telemetry status badges, collapsible control drawers, and real-time account management cards.
   - Combining these produces a hybrid "Drafting Atelier & Dark Control Surface" with clean CSS variables and responsive layouts.

3. **Multi-Platform Session Management Logic**:
   - Observations of `social/config.py` and `social/insta_client.py` show that session IDs and tokens are loaded, validated, and stored in JSON structures (`data/instagram_config.json`, `data/insta_session.json`, `config.json`).
   - The UI must provide multi-account registration for Instagram, Discord, and X (Twitter):
     - Form input fields for Platform Type, Account Name, Session ID / Auth Token, Proxy, and Automation switches.
     - Active Accounts List displaying account status badges (Active, Expired, Idle), active session inspection, disconnect/switch controls, and live action triggers.
     - Dual-tier persistence: Client `localStorage` for instant client-side account state + backend sync via `/api/social/settings` and `/api/social/status`.

4. **Animated Background Engine & Spinning Gears Logic**:
   - The canvas background engine must support 4 selectable modes:
     1. **Clockwork Gears**: Multi-cog canvas animation rendering intermeshed mechanical gears with teeth, inner rings, hub spokes, and calibrated rotational velocity ratios ($\omega_2 = -\omega_1 \cdot \frac{N_1}{N_2}$).
     2. **Drafting Blueprint Grid**: Floating coordinate axes, drafting lines, isometric grid intersections, and pulsating compass circles.
     3. **Studio Dark Pulse**: Ambient dark-mode particle constellation with smooth gradient wave oscillations.
     4. **Minimal Slate**: Flat, non-distracting minimalist surface.
   - Selected background, animation speed, and opacity parameters must persist across sessions via `localStorage` and initialize immediately on DOM load.

5. **Automated Verification Logic**:
   - Requirement R5 mandates an automated objective verification script.
   - The script can be executed directly in Python to inspect `social.html` DOM elements, verify CSS variables and canvas rendering classes, validate Flask routing handlers in `bot.py`, and test session ID validation logic without manual browser interaction.

---

## 3. Caveats

1. **Instagrapi Dependency Availability**:
   - In environments where `instagrapi` is not installed, `social/insta_client.py` gracefully falls back to native REST/web session handling (`HAVE_INSTAGRAPI = False`). Session validation and persistence logic in `social.html` must account for both direct REST API responses and mock/client verification states.
2. **Discord Voice & Child Worker Isolation**:
   - In `bot.py:8979-9028`, multi-persona child bot processes run in isolated subprocesses. Backend session updates must safely acquire `state_lock` and invoke `social_manager.update_config()` without restarting child Discord worker processes.
3. **No Direct Code Modification During Investigation**:
   - This phase is strictly read-only analysis. Concrete code modifications, file creation of `social.html`, and patches to `bot.py` will be executed during the implementation milestone.

---

## 4. Conclusion & Technical Specifications

### 4.1 Page Architecture Specification (`social.html`)
- **File Path**: `/storage/emulated/0/discord-bot/social.html`
- **Layout & Structure**:
  - Full-screen container with `#bg-canvas` behind all content layers.
  - Top Navigation Bar: macOS window control dots, title `"Social Operations — Atelier Control"`, active platform telemetry pill, and fast navigation buttons (`Studio Suite ↗`, `Drafting Desk ↗`, `Settings ⚙`).
  - Left Control Surface: 64px vertical sidebar with tactile brass icons (`Overview`, `Instagram Hub`, `Discord Bots`, `X / Twitter`, `Background Engine`, `Session Vault`).
  - Main Atelier Canvas:
    - **Header Section**: Real-time telemetry cards (Active Sessions, Connected Platforms, Background Status, API Latency).
    - **Background Engine Drawer**: Interactive controls for selecting `Clockwork Gears`, `Drafting Blueprint Grid`, `Studio Dark Pulse`, or `Minimal Slate`, complete with speed and opacity sliders.
    - **Session Manager Deck**: Add new session form (Platform selector, Session ID / Bearer token, Account name, Proxy URL), and active session cards with live status monitors, validity tests, disconnect actions, and credential inspector.
    - **Live Action & Activity Drawer**: Action triggers (Test session validity, fetch DM stats, trigger test post, view audit logs).

### 4.2 Spinning Gears Canvas Engine Specification
- High-performance HTML5 `<canvas>` rendering loop using `requestAnimationFrame`.
- Gear rendering function computing pitch circles, tooth addendum/dedendum, drive pinion ratios, and gear tooth meshing with depth shadows and brass/steel color gradients.
- Responsive canvas resizing with DPR scaling for crisp display on high-density mobile and desktop screens.

### 4.3 Flask Route Wiring in `bot.py`
Add the following route definition in `bot.py` alongside `studio_index` and `drafting_page`:
```python
@app.route("/social")
@app.route("/social.html")
@app.route("/control")
def social_control_page():
    html_path = os.path.join(SCRIPT_DIR, "social.html")
    if not os.path.exists(html_path):
        html_path = os.path.join(SCRIPT_DIR, "dashboard.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return render_template_string(f.read())
    except Exception as e:
        return f"Social control template read error: {e}", 500
```

### 4.4 Shared Navigation Integration
- Add `<a href="/social" ...>Social Hub ↗</a>` to `dashboard.html` header bar.
- Add `<a href="/social" class="sidebar-item" ...><span class="sidebar-label">Social ↗</span></a>` to `studio.html` / `index.html` sidebar.
- Include corresponding links inside `social.html` pointing back to `/dashboard` and `/studio`.

---

## 5. Verification Method

To verify the survey findings and subsequent implementation independently:

1. **File Existence and Integrity**:
   ```bash
   test -f /storage/emulated/0/discord-bot/social.html && echo "social.html exists"
   ```
2. **Flask Route Registration & Response**:
   ```bash
   python3 -c "
   from bot import app
   client = app.test_client()
   for r in ['/social', '/social.html', '/control', '/dashboard', '/studio']:
       res = client.get(r)
       assert res.status_code == 200, f'Route {r} failed with {res.status_code}'
       print(f'Route {r}: OK (Status {res.status_code})')
   "
   ```
3. **Automated Script for DOM & Animation Verification**:
   Execute the automated verification script against `social.html` to confirm DOM elements, canvas gear scripts, CSS animations, and session ID storage logic.
