# Project: Unified Social Web Control Center (`social.html`)

## Architecture
The 3rd Unified Web Control Center (`social.html`) combines the tactile, physical aesthetics of the Drafting Desk (`dashboard.html`) with the dark control surfaces, telemetry badges, and modular density of the Studio Suite (`studio.html`). The system provides multi-platform social account management via Session IDs, an interactive animated background engine featuring interlocking spinning gears with real-time physics and gear ratio kinematics, complete Flask backend wiring in `bot.py`, and an automated objective verification test harness.

### Data Flow & Architecture Diagram
```
+-----------------------------------------------------------------------------------+
|                                  Browser Client                                   |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |              Tactile Drafting Desk × Dark Studio Hybrid Interface           |  |
|  |  - 3-Way Navigation: [/dashboard] <-> [/studio] <-> [/social]               |  |
|  |  - Tactile Paper Panels, Brass/Steel Clips, Blueprint Rulers & Grid Accents |  |
|  |  - Dark Studio Decks, Modular Cards, Telemetry Badges, Activity Log        |  |
|  +-----------------------------------------------------------------------------+  |
|                                         |                                         |
|  +-----------------------------------+  |  +-----------------------------------+  |
|  |  Interactive Canvas Engine (R3)   |  |  |  Social Account Hub Logic (R2)    |  |
|  |  1. Clockwork Gears (Kinematics)  |  |  |  - Multi-Platform Session Input   |  |
|  |  2. Drafting Blueprint Grid       |  |  |  - State: Active / Expired / Idle |  |
|  |  3. Studio Dark Pulse             |  |  |  - Inspect, Disconnect, Test     |  |
|  |  4. Minimal Slate                 |  |  |  - localStorage + Backend Sync    |  |
|  +-----------------------------------+  |  +-----------------------------------+  |
+-----------------------------------------|-----------------------------------------+
                                          | HTTP REST APIs (R4)
+-----------------------------------------v-----------------------------------------+
|                               Flask Backend (bot.py)                              |
|  - Routes: /social, /social.html, /control -> serves social.html                  |
|  - API Endpoints:                                                                 |
|    * GET /api/social/accounts         (Retrieve persisted accounts)               |
|    * POST /api/social/accounts        (Add/update session credentials)            |
|    * POST /api/social/accounts/test   (Test credential validity)                  |
|    * POST /api/social/accounts/switch  (Set active account)                       |
|    * DELETE /api/social/accounts/<id> (Remove account)                            |
|    * GET /api/social/logs             (Retrieve audit logs)                       |
|  - Storage: data/social_accounts.json, data/instagram_config.json                 |
+-----------------------------------------------------------------------------------+
```

## Feature Inventory
| # | Feature | Description | Milestone | Source | Status |
|---|---------|-------------|-----------|--------|--------|
| 1 | Hybrid Layout & Navigation | Standalone `social.html` with drafting desk tactile panels, blueprint rulers/grid, dark studio cards, and 3-way navigation (`/dashboard`, `/studio`, `/social`) | M2 | ORIGINAL_REQUEST §R1 | DONE |
| 2 | Clockwork Gears Canvas Engine | Canvas-based interlocking spinning cogs with calibrated gear ratios ($\omega_1 r_1 = -\omega_2 r_2$), tooth profile geometry, physics, and depth | M3 | ORIGINAL_REQUEST §R3 | DONE |
| 3 | Multi-Theme Background Switcher | Switcher for 4 themes (Clockwork Gears, Blueprint Grid, Studio Dark Pulse, Minimal Slate) with localStorage persistence | M3 | ORIGINAL_REQUEST §R3 | DONE |
| 4 | Social Account Session Input | Form to add accounts for Instagram, Discord, X/Twitter via session IDs & auth tokens | M4 | ORIGINAL_REQUEST §R2 | DONE |
| 5 | Account Lifecycle & Status Monitoring | Active accounts list with status badges (Active, Expired, Idle), Inspect modal (with token copy/reveal), Disconnect, and Test action | M4 | ORIGINAL_REQUEST §R2 | DONE |
| 6 | Dual-Layer Persistence & Sync | Client-side `localStorage` cache synchronized with Flask REST endpoints | M4 | ORIGINAL_REQUEST §R2 | DONE |
| 7 | Flask Server Routes & Backend API | Routes `/social`, `/social.html`, `/control` and JSON API endpoints in `bot.py` | M5 | ORIGINAL_REQUEST §R4 | DONE |
| 8 | Automated Objective Test Suite | Zero-dependency verification script testing DOM, CSS animations, Canvas gear physics, Flask HTTP 200 routes, and session persistence | M1 / M6 | ORIGINAL_REQUEST §R5 | DONE |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: E2E Test Suite (`verify_social_hub.py`) | Automated headless test harness covering DOM structure, CSS rules, canvas engine script, Flask routes, session state machine | none | DONE |
| 2 | M2: Hybrid UI Structure & Aesthetics | `social.html` HTML skeleton, CSS hybrid tokens, drafting desk tactile panels, studio cards, rulers, badges, 3-way navigation | M1 | DONE |
| 3 | M3: Animated Canvas Engine (Gears & Themes) | HTML5 Canvas engine with interlocking gears math ($\omega_1 r_1 = -\omega_2 r_2$), blueprint grid, dark pulse, minimal slate, and UI controls | M2 | DONE |
| 4 | M4: Social Account Hub & Session Management | JS session manager, multi-platform input, status state machine (Active/Expired/Idle), modal inspect/copy, disconnect, test, activity logs, localStorage sync | M2, M3 | DONE |
| 5 | M5: Flask Server Wiring & Backend REST API | `bot.py` route handlers (`/social`, `/social.html`, `/control`), account CRUD REST APIs, persistence in `data/social_accounts.json` | M4 | DONE |
| 6 | M6: Full E2E Verification, Stress Test & Forensic Audit | Execution of `verify_social_hub.py`, Reviewer review, Challenger stress tests, Forensic Auditor integrity verification | M1, M2, M3, M4, M5 | DONE |

## Interface Contracts
### Client ↔ Server REST API
- `GET /api/social/accounts`
  - Response: `{"success": true, "accounts": [...], "active_id": "..."}`
- `POST /api/social/accounts`
  - Body: `{"platform": "instagram|discord|twitter", "account_name": "...", "session_id": "...", "status": "active|idle|expired", "metadata": {...}}`
  - Response: `{"success": true, "account": {...}}`
- `POST /api/social/accounts/test`
  - Body: `{"account_id": "...", "platform": "...", "session_id": "..."}`
  - Response: `{"success": true, "status": "active|expired|invalid", "message": "...", "timestamp": "..."}`
- `POST /api/social/accounts/switch`
  - Body: `{"account_id": "..."}`
  - Response: `{"success": true, "active_id": "..."}`
- `DELETE /api/social/accounts/<account_id>`
  - Response: `{"success": true, "deleted_id": "..."}`
- `GET /api/social/logs`
  - Response: `{"success": true, "logs": [...]}`

### Code Layout
- `social.html` — Standalone unified control center web page at project root `/storage/emulated/0/discord-bot/social.html`
- `bot.py` — Flask application route registration and API handlers at `/storage/emulated/0/discord-bot/bot.py`
- `verify_social_hub.py` — Automated verification script at `/storage/emulated/0/discord-bot/verify_social_hub.py`
- `data/social_accounts.json` — Persisted social account sessions database at `/storage/emulated/0/discord-bot/data/social_accounts.json`
