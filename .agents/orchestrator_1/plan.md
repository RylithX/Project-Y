# Orchestration Plan: Unified Social Web Control Center (`social.html`)

## Goal
Design, implement, wire, and objectively verify a 3rd web control center (`social.html`) combining Drafting Desk tactile aesthetics with Studio Suite dark control surfaces, multi-platform social account management via Session IDs, interactive mechanical gear physics / background animation engine, Flask backend routing in `bot.py`, and comprehensive automated verification test suite.

## Phases
1. **Phase 0: Survey & Codebase Exploration**
   - Explorer 1: Codebase structure, `bot.py`, existing routes, server setup, existing HTML files (`dashboard.html`, `studio.html`), session endpoints.
   - Explorer 2: UI/UX & Visual System Analysis (Drafting desk tactile design, Studio Suite dark theme, layout, fonts, CSS variables, gear canvas engine requirements).
   - Explorer 3: Functional Requirements & Backend / Test Architecture (Social session lifecycle, credential format, persistence model, Flask endpoints, verification runner).

2. **Phase 1: Project Decomposition & Specification**
   - Synthesize findings into `PROJECT.md` and `TEST_INFRA.md`.
   - Define module interfaces, file boundaries, and acceptance criteria.

3. **Phase 2: Dual Track Execution**
   - E2E Testing Track: Build comprehensive automated verification script (`verify_social_hub.py` or similar) testing HTML, CSS, JS canvas, session logic, and Flask routes.
   - Implementation Track:
     - Milestone 1: Core UI Layout & Hybrid Aesthetics (`social.html`) with tactile panels, rulers, dark cards, badges, navigation between `/dashboard`, `/studio`, `/social`.
     - Milestone 2: Background Canvas Engine (`social.html` inline JS/modules) with interlocking spinning gears, calibrated gear ratios, blueprint grid, studio dark pulse, minimal slate, and persistence.
     - Milestone 3: Social Account Hub logic (`social.html`) with session ID input, multi-platform support (Instagram, Discord, X/Twitter), status monitors, localStorage persistence, backend sync, and actions (remove, inspect, test).
     - Milestone 4: Backend Wiring in `bot.py` (`/social`, `/social.html`, `/control`, session persistence & test endpoints).

4. **Phase 3: E2E Integration, Review, Challenger Stress-Testing, and Forensic Audit**
   - Reviewers (2) and Challengers (2) evaluate full system.
   - Forensic Auditor conducts authenticity, integrity, and anti-facade checks.
   - Gate verification.

5. **Phase 4: Synthesis & Final Handoff**
   - Produce final completion report with verified evidence and pass results.
