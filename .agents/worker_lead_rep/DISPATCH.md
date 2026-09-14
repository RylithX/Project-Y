## 2026-09-02T21:00:15Z
You are the Lead Implementation Worker for Milestones M2, M3, M4, and M5.
Working directory: `/storage/emulated/0/discord-bot/.agents/worker_lead_rep`.

Read:
- `/storage/emulated/0/discord-bot/.agents/ORIGINAL_REQUEST.md`
- `/storage/emulated/0/discord-bot/PROJECT.md`
- `/storage/emulated/0/discord-bot/TEST_INFRA.md`
- `/storage/emulated/0/discord-bot/TEST_READY.md`
- `/storage/emulated/0/discord-bot/verify_social_hub.py`
- `/storage/emulated/0/discord-bot/.agents/explorer_survey_1/handoff.md`
- `/storage/emulated/0/discord-bot/.agents/explorer_survey_2_rep/handoff.md`
- `/storage/emulated/0/discord-bot/.agents/explorer_survey_3/handoff.md`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

File Ownership:
- `/storage/emulated/0/discord-bot/social.html`
- `/storage/emulated/0/discord-bot/bot.py`
- `/storage/emulated/0/discord-bot/data/social_accounts.json`

Implementation Instructions:
1. Create `/storage/emulated/0/discord-bot/data/social_accounts.json` with initial JSON structure: `{"accounts": [], "active_id": null, "logs": []}`.
2. Implement `/storage/emulated/0/discord-bot/social.html`:
   - Complete, standalone HTML5 document.
   - Hybrid design system: Drafting Desk tactile paper cards (`.drafting-panel`, `.desk-surface`, `.paper-card`, `.paper-clip`), blueprint rulers & millimeter marks (`.blueprint-ruler`, `.grid-canvas`, `.grid-layer`), dark Studio Suite decks (`.studio-card`, `.control-deck`), telemetry badges (`.status-badge`, `.status-pill`), and 3-way navigation (`/dashboard`, `/studio`, `/social`).
   - Background Canvas Engine (`#bgCanvas` or `#gearCanvas`):
     * Clockwork Gears: Interlocking mechanical cogs and gears spinning at calibrated gear ratios ($\omega_1 r_1 = -\omega_2 r_2$), tooth profile geometry, physics, depth shadows, speed/opacity controls.
     * Drafting Blueprint Grid: Floating coordinate axes, drafting lines, compass circles.
     * Studio Dark Pulse: Ambient constellation particles and gradient glow.
     * Minimal Slate: Clean dark slate.
     * State persistence in `localStorage` (`social_hub_bg_state`, `social_hub_bg_theme`).
   - Social Account Management JS:
     * Platform selector (Instagram, Discord, X/Twitter), Account Name, Session ID input form (`#platformSelect`, `#accountName`, `#sessionIdInput`, `#addAccountBtn`).
     * Accounts list container (`#accountsList` / `#accountsGrid` / `#emptyStateMsg`) rendering account cards with status badges (`Active`, `Expired`, `Idle`).
     * Inspect modal (`#inspectModal`, `#copyTokenBtn`, `#closeModalBtn`) with masked token toggle and copy.
     * Disconnect action with confirmation.
     * Test credential action with mock/live validation.
     * Account switcher.
     * Activity Log feed (`#activityLogFeed`, `#activityList`, `#clearLogsBtn`).
     * Dual persistence (`localStorage` + `/api/social/accounts` REST sync).
3. Update `/storage/emulated/0/discord-bot/bot.py`:
   - Add routes `@app.route('/social')`, `@app.route('/social.html')`, `@app.route('/control')` rendering `social.html`.
   - Add REST API routes `/api/social/accounts` (GET/POST), `/api/social/accounts/test` (POST), `/api/social/accounts/switch` (POST), `/api/social/accounts/<account_id>` (DELETE), `/api/social/logs` (GET).
   - Thread-safe storage in `data/social_accounts.json`.
4. Verification:
   - Run `python3 /storage/emulated/0/discord-bot/verify_social_hub.py -v` to ensure all 41 test cases pass with exit code 0.
   - Write your handoff report to `/storage/emulated/0/discord-bot/.agents/worker_lead_rep/handoff.md`.
   - Send a message to parent using `send_message`.
