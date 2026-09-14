# Original User Request

## Initial Request — 2026-09-02T19:15:58Z

Build a 3rd unified web control center combining the tactile aesthetics of the Drafting Desk with the dark control surfaces of the Studio Suite, providing full management of social accounts via session IDs, smooth animations, and a library of selectable animated backgrounds featuring interactive spinning gears.

Working directory: /storage/emulated/0/discord-bot
Integrity mode: development

## Requirements

### R1. Drafting Desk & Studio Hybrid Interface
Create a 3rd standalone web page (`social.html`) that blends the physical drafting desk feel (architectural grid, tactile paper panels, brass/steel accents, smooth micro-interactions) with the sleek dark Studio Suite control system (sidebars, status telemetry, control drawers, collapsible decks). The page must include seamless navigation connecting Drafting Desk (`/dashboard`), Studio Suite (`/studio`), and this new control center.

### R2. Social Account Management via Session IDs
Implement a multi-platform social account control hub where users can add and manage accounts (such as Instagram, Discord, X/Twitter) by providing session IDs and authentication tokens. The interface must provide status monitors, account switching, credential testing, and action controls (e.g. view active sessions, disconnect, trigger actions, view recent logs).

### R3. Interactive Animated Background Engine with Spinning Gears
Develop a high-performance, smooth animated background engine with a user-facing switcher. Background options must include:
1. **Clockwork Gears**: Interlocking mechanical cogs and gears spinning at calibrated gear ratios with smooth physics and depth.
2. **Drafting Blueprint Grid**: Floating coordinate axes, drafting lines, and subtle pulsing compass circles.
3. **Studio Dark Pulse**: Subtle ambient dark-mode gradient or particle constellation.
4. **Minimal Slate**: Clean, non-distracting background option.
The selected background state and animation parameters (speed, opacity) must persist across page reloads.

### R4. Route and Backend Wiring
Expose the new page through the Flask application in `bot.py` under clean URL routes (`/social`, `/social.html`, `/control`), alongside existing endpoints for session ID persistence and verification.

### R5. Automated Objective Verification
Provide an automated verification script that programmatically tests the page's HTML structure, verifies all required UI panels, checks CSS animation definitions and background canvas scripts, validates the Flask routing endpoints, and tests session ID storage logic without requiring manual browser interaction.

## Acceptance Criteria

### UI Architecture & Aesthetics
- [ ] The new web page file exists at `/storage/emulated/0/discord-bot/social.html` and loads with zero console errors.
- [ ] The design incorporates both Drafting Desk visual elements (tactile panels, blueprint rulers/grid accents) and Studio Suite elements (dark studio cards, status badges, modular panels).
- [ ] Navigation links exist to jump between `/dashboard`, `/studio`, and `/social`.

### Social Session Management
- [ ] Form input allowing users to input a platform type, account name, and Session ID / Auth Token.
- [ ] Accounts persist in client storage (`localStorage`) and sync with local backend JSON/storage endpoints if available.
- [ ] Active accounts list displays status indicators (Active, Expired, Idle) with options to remove, inspect, or test session validity.

### Background System & Gears Animation
- [ ] Background selector UI allows switching in real-time between at least 3 distinct animated backgrounds, including the spinning gears canvas.
- [ ] Gears animation features multiple interlocking gear teeth rotating continuously with smooth `requestAnimationFrame` timing.
- [ ] User's background choice is saved and restored automatically on page reload.

### Server & Routes
- [ ] `bot.py` serves the page at `/social` and `/social.html` with HTTP 200 responses.
- [ ] Verification script runs in the shell and exits with code 0, confirming all DOM elements, routes, and animation scripts exist.
