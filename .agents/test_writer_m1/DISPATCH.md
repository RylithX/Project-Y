## 2026-09-02T19:42:47Z
You are the E2E Test Suite Creator for Milestone M1.
Working directory: `/storage/emulated/0/discord-bot/.agents/test_writer_m1`.
Read:
- `/storage/emulated/0/discord-bot/.agents/ORIGINAL_REQUEST.md`
- `/storage/emulated/0/discord-bot/PROJECT.md`
- `/storage/emulated/0/discord-bot/TEST_INFRA.md`
- `/storage/emulated/0/discord-bot/.agents/explorer_survey_3/handoff.md`

Your task:
1. Create the comprehensive, standalone automated verification script at `/storage/emulated/0/discord-bot/verify_social_hub.py`.
   It must use standard Python 3 (zero external test runner dependencies; using `unittest`, `re`, `html.parser`, `json`, `urllib.request` or Flask test client if available).
   The test suite must cover:
   - DOM & UI structure of `social.html` (hybrid tactile paper panels, blueprint rulers/grid, dark studio cards, telemetry badges, 3-way navigation between `/dashboard`, `/studio`, and `/social`).
   - CSS variables, animations, and typography tokens.
   - Canvas animation engine (interlocking spinning gears physics, gear ratios, blueprint grid, studio dark pulse, minimal slate, localStorage persistence).
   - Social Account Management (multi-platform Instagram/Discord/X, form inputs, session IDs, status badges Active/Expired/Idle, inspect modal, disconnect, test action, sync).
   - Flask server routes (`/social`, `/social.html`, `/control` returning HTTP 200, and `/api/social/accounts` endpoints).
2. Create `/storage/emulated/0/discord-bot/TEST_READY.md` summarizing test tiers and runner instructions.
3. Write your handoff report to `/storage/emulated/0/discord-bot/.agents/test_writer_m1/handoff.md` and send a message back with your results.
