# E2E Test Infra: Unified Social Web Control Center

## Test Philosophy
- Opaque-box, requirement-driven automated verification.
- Zero external testing dependencies: executes with standard Python 3.14 stdlib (`unittest`, `html.parser`, `re`, `urllib.request` / `Flask.test_client()`).
- Methodology: Category-Partition, Boundary Value Analysis, Pairwise Combinations, State Machine transition testing, and Flask endpoint verification.

## Feature Inventory & Test Mapping
| # | Feature | Requirement | Tier 1 (Unit/DOM) | Tier 2 (Boundaries) | Tier 3 (Interactions) | Tier 4 (E2E Integration) |
|---|---------|-------------|:-----------------:|:-------------------:|:---------------------:|:------------------------:|
| F1 | Hybrid UI Structure | R1, R5 | 5 | 5 | ✓ | ✓ |
| F2 | Navigation Links | R1, R5 | 5 | 5 | ✓ | ✓ |
| F3 | Clockwork Gears Canvas | R3, R5 | 5 | 5 | ✓ | ✓ |
| F4 | Background Mode Switcher | R3, R5 | 5 | 5 | ✓ | ✓ |
| F5 | Social Account Form & Platforms | R2, R5 | 5 | 5 | ✓ | ✓ |
| F6 | Status Lifecycle & Actions | R2, R5 | 5 | 5 | ✓ | ✓ |
| F7 | Dual-Layer Sync Protocol | R2, R4 | 5 | 5 | ✓ | ✓ |
| F8 | Flask Routes & REST APIs | R4, R5 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Script Location**: `/storage/emulated/0/discord-bot/verify_social_hub.py`
- **Execution Command**: `python3 /storage/emulated/0/discord-bot/verify_social_hub.py`
- **Exit Code**: 0 on full pass, non-zero on any failure.
- **Pass Semantics**:
  - Validates `social.html` exists and parses cleanly.
  - Confirms all required DOM elements (tactile panels, blueprint rulers, dark cards, telemetry badges, modal dialogs, platform selectors, gear canvas, theme buttons).
  - Confirms CSS keyframe animations, styling variables, and responsive layout classes.
  - Validates JavaScript functions for interlocking gears math, animation loop, theme persistence, and session CRUD state machine.
  - Starts or imports Flask test client on `bot.py` to assert HTTP 200 on `/social`, `/social.html`, `/control` and JSON REST API responses.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Multi-Platform Session Lifecycle | Add Instagram, Discord, X accounts -> Test credentials -> Switch Active -> Inspect modal -> Disconnect | High |
| 2 | Background Engine & Parameter Tuning | Switch between Gears, Blueprint, Dark Pulse, Minimal -> Adjust Speed / Opacity -> Reload -> Validate restored state | Medium |
| 3 | Flask Backend Synchronization | Client adds account -> Syncs to `/api/social/accounts` -> File written to `data/social_accounts.json` -> Fetch endpoint matches | High |
| 4 | 3-Way Navigation Interoperability | Verify route links between `/dashboard`, `/studio`, and `/social` load correctly with HTTP 200 | Medium |
