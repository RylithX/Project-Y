## 2026-09-02T19:17:08Z

<USER_REQUEST>
Investigate the social account session management lifecycle and verification harness requirements for `/storage/emulated/0/discord-bot`.
Read `/storage/emulated/0/discord-bot/.agents/ORIGINAL_REQUEST.md`.
Analyze requirement R2 (Social Account Management via Session IDs: Instagram, Discord, X/Twitter, token input, status monitor Active/Expired/Idle, account switching, credential testing, inspect modal, disconnect, recent activity logs, localStorage + backend sync) and R5 (Automated Objective Verification script).
Design the exact specification for:
1. Client-side session storage schema and sync protocol with Flask backend.
2. Mock / live credential validation logic and state machine (Active, Expired, Idle).
3. Automated headless verification test suite structure (`verify_social_hub.py` or similar) that verifies DOM structure, UI elements, CSS rules/animations, canvas scripts, Flask routes HTTP 200, and session ID storage logic without requiring manual browser interaction.
Write your detailed report to `/storage/emulated/0/discord-bot/.agents/explorer_survey_3/handoff.md`.
</USER_REQUEST>
