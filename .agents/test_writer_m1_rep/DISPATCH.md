## 2026-09-02T20:20:16Z
You are the E2E Test Suite Creator for Milestone M1.
Working directory: `/storage/emulated/0/discord-bot/.agents/test_writer_m1_rep`.
Read:
- `/storage/emulated/0/discord-bot/.agents/ORIGINAL_REQUEST.md`
- `/storage/emulated/0/discord-bot/PROJECT.md`
- `/storage/emulated/0/discord-bot/TEST_INFRA.md`
- `/storage/emulated/0/discord-bot/.agents/explorer_survey_3/handoff.md`

Your task:
1. Create `/storage/emulated/0/discord-bot/verify_social_hub.py`.
   Use standard Python 3 (`unittest`, `re`, `html.parser`, `json`, `urllib.request`). Zero external test runner dependencies.
   The script must define 5 test suites:
   - `TestHTMLAndDOMStructure`: Checks `social.html` exists, contains hybrid drafting paper panels (`.drafting-panel`, `.desk-surface`, etc.), blueprint rulers/grid accents (`.blueprint-ruler`, `.grid-canvas` / `.grid-layer`), dark studio cards (`.studio-card`, `.control-deck`), status badges (`.status-badge`), 3-way navigation (`/dashboard`, `/studio`, `/social`), account form (`#platformSelect`, `#accountName`, `#sessionIdInput`, `#addAccountBtn`), account list (`#accountsList`), modal (`#inspectModal`), canvas (`#gearCanvas` or `#bgCanvas`), theme switcher (`.theme-btn` or `.bg-switch-btn`).
   - `TestCSSVariablesAndAnimations`: Checks keyframe animations (`@keyframes gearRotate` / spin / float / pulse), hybrid CSS variables (`--bg`, `--paper`, `--card-bg`, `--accent`, etc.), responsive layout rules.
   - `TestCanvasGearKinematicsAndThemes`: Checks JavaScript functions for canvas initialization, gear ratio kinematics calculation ($\omega_1 r_1 = -\omega_2 r_2$ or rotational tooth relationship), 4 background modes (Clockwork Gears, Drafting Blueprint Grid, Studio Dark Pulse, Minimal Slate), `requestAnimationFrame` loop, and `localStorage` keys (`social_hub_bg_state` / `social_hub_bg_theme`).
   - `TestSocialSessionLifecycle`: Checks JS session manager for multi-platform support (Instagram `sessionid`, Discord tokens, X/Twitter `auth_token`), state transitions (Active, Expired, Idle), inspect modal toggle/copy, disconnect, credential test, and dual-layer persistence (`localStorage` + Flask API).
   - `TestFlaskRoutingAndAPIs`: Checks `bot.py` routes (`/social`, `/social.html`, `/control` return HTTP 200 via Flask test client or route definitions) and REST APIs (`/api/social/accounts`, `/api/social/accounts/test`, `/api/social/accounts/switch`, `/api/social/logs`).
   Ensure when run directly (`python3 verify_social_hub.py`), it executes `unittest.main()`.
2. Create `/storage/emulated/0/discord-bot/TEST_READY.md` summarizing the test tiers and runner command.
3. Write your handoff report to `/storage/emulated/0/discord-bot/.agents/test_writer_m1_rep/handoff.md`.
4. Immediately send a message to parent using `send_message`.
