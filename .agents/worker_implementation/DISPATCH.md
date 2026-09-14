## 2026-09-02T20:24:10Z

You are the Primary Implementation Worker for Milestones M2, M3, M4, and M5.
Working directory: `/storage/emulated/0/discord-bot/.agents/worker_implementation`.

Read:
- `/storage/emulated/0/discord-bot/.agents/ORIGINAL_REQUEST.md`
- `/storage/emulated/0/discord-bot/PROJECT.md`
- `/storage/emulated/0/discord-bot/TEST_INFRA.md`
- `/storage/emulated/0/discord-bot/TEST_READY.md`
- `/storage/emulated/0/discord-bot/.agents/explorer_survey_1/handoff.md`
- `/storage/emulated/0/discord-bot/.agents/explorer_survey_2_rep/handoff.md`
- `/storage/emulated/0/discord-bot/.agents/explorer_survey_3/handoff.md`
- `/storage/emulated/0/discord-bot/verify_social_hub.py`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Ownership:
- `/storage/emulated/0/discord-bot/social.html`
- `/storage/emulated/0/discord-bot/bot.py`
- `/storage/emulated/0/discord-bot/data/social_accounts.json`

Implementation Objectives:
1. Create `/storage/emulated/0/discord-bot/social.html`:
   - Standalone, fully functional web control center.
   - Design System: Blends Drafting Desk tactile paper panels, paper clip accents, blueprint millimeter rulers, and coordinate grid lines with Dark Studio Suite cards, telemetry badges, and 3-way navigation (`/dashboard`, `/studio`, `/social`).
   - Background Canvas Engine: Interactive HTML5 canvas (`#bgCanvas` or `#gearCanvas`) featuring 4 selectable modes:
     1. Clockwork Gears: Interlocking mechanical cogs and gears spinning at calibrated gear ratios with realistic physics, involute tooth profiles, pitch circles, and shadow depth.
     2. Drafting Blueprint Grid: Floating coordinate axes, drafting lines, compass circles.
     3. Studio Dark Pulse: Ambient constellation particles and gradient glow.
     4. Minimal Slate: Clean dark slate.
     - Interactive controls for background mode switching, speed, and opacity, persisted in `localStorage`.
   - Social Account Session Hub:
     - Platform select (Instagram, Discord, X/Twitter), Account Name, and Session ID / Auth Token input form.
     - Active accounts list rendering status badges (`Active`, `Expired`, `Idle`).
     - Inspect modal with token reveal toggle, raw token copy button, and metadata.
     - Disconnect action with confirmation.
     - Test credential action (mock/live validator).
     - Account switcher setting active account.
     - Real-time Activity Logs feed with timestamped audit entries and clear logs option.
     - Dual persistence (`localStorage` + Flask `/api/social/accounts` REST synchronization).

2. Update `/storage/emulated/0/discord-bot/bot.py`:
   - Register routes `@app.route('/social')`, `@app.route('/social.html')`, `@app.route('/control')` rendering `social.html` with HTTP 200.
   - Add REST API endpoints:
     - `GET /api/social/accounts`
     - `POST /api/social/accounts`
     - `POST /api/social/accounts/test`
     - `POST /api/social/accounts/switch`
     - `DELETE /api/social/accounts/<account_id>`
     - `GET /api/social/logs`
   - Implement thread-safe persistence in `data/social_accounts.json`.

3. Verification:
   - Run `python3 /storage/emulated/0/discord-bot/verify_social_hub.py -v` and ensure all 41 test cases pass with exit code 0.
   - Run any additional checks.
   - Write your comprehensive handoff report to `/storage/emulated/0/discord-bot/.agents/worker_implementation/handoff.md`.
   - Send completion message to parent via `send_message`.
