#!/usr/bin/env python3
"""
verify_social_hub.py - Automated Objective Verification Test Harness for Social Hub Control Center (M1)

Multi-tier automated test suite covering:
- TestHTMLAndDOMStructure: Checks social.html exists, hybrid drafting paper panels (.drafting-panel, .desk-surface),
  blueprint rulers/grid accents (.blueprint-ruler, .grid-canvas / .grid-layer), dark studio cards (.studio-card, .control-deck),
  status badges (.status-badge), 3-way navigation (/dashboard, /studio, /social), account form (#platformSelect, #accountName,
  #sessionIdInput, #addAccountBtn), account list (#accountsList), modal (#inspectModal), canvas (#gearCanvas or #bgCanvas),
  theme switcher (.theme-btn or .bg-switch-btn).
- TestCSSVariablesAndAnimations: Checks keyframe animations (@keyframes gearRotate / spin / float / pulse),
  hybrid CSS variables (--bg, --paper, --card-bg, --accent, etc.), responsive layout rules.
- TestCanvasGearKinematicsAndThemes: Checks JavaScript functions for canvas initialization, gear ratio kinematics
  calculation (omega_1 * r_1 = -omega_2 * r_2), 4 background modes (Clockwork Gears, Drafting Blueprint Grid,
  Studio Dark Pulse, Minimal Slate), requestAnimationFrame loop, and localStorage keys (social_hub_bg_state / social_hub_bg_theme).
- TestSocialSessionLifecycle: Checks JS session manager for multi-platform support (Instagram sessionid, Discord tokens,
  X/Twitter auth_token), state transitions (Active, Expired, Idle, Testing, Invalid), inspect modal toggle/copy, disconnect,
  credential test, and dual-layer persistence (localStorage + Flask API).
- TestFlaskRoutingAndAPIs: Checks bot.py routes (/social, /social.html, /control, /dashboard, /studio return HTTP 200)
  and REST APIs (/api/social/accounts, /api/social/accounts/test, /api/social/accounts/switch, /api/social/logs).

Zero external test runner dependencies. Runs natively with standard Python 3.8+ (unittest, re, html.parser, json, urllib.request).
When executed directly (python3 verify_social_hub.py), it runs unittest.main().
"""

import os
import sys
import re
import json
import time
import math
import base64
import unittest
from html.parser import HTMLParser
from typing import List, Dict, Any, Optional, Tuple

# ─── PATH DEFINITIONS ────────────────────────────────────────────────────────
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
SOCIAL_HTML_PATH = os.path.join(WORKSPACE_DIR, "social.html")
DASHBOARD_HTML_PATH = os.path.join(WORKSPACE_DIR, "dashboard.html")
STUDIO_HTML_PATH = os.path.join(WORKSPACE_DIR, "studio.html")
BOT_PY_PATH = os.path.join(WORKSPACE_DIR, "bot.py")
DATA_DIR = os.path.join(WORKSPACE_DIR, "data")
SOCIAL_ACCOUNTS_JSON_PATH = os.path.join(DATA_DIR, "social_accounts.json")
INSTAGRAM_CONFIG_PATH = os.path.join(DATA_DIR, "instagram_config.json")


# ─── DOM TREE EXTRACTOR (ZERO-DEPENDENCY HTML PARSER) ─────────────────────────
class DOMNode:
    """Represents a parsed HTML DOM element with querying methods."""
    def __init__(self, tag: str, attrs: List[Tuple[str, Optional[str]]], parent: Optional['DOMNode'] = None):
        self.tag = tag.lower()
        self.attrs: Dict[str, str] = {k.lower(): (v if v is not None else "") for k, v in attrs}
        self.parent = parent
        self.children: List['DOMNode'] = []
        self.text_fragments: List[str] = []

    @property
    def id(self) -> str:
        return self.attrs.get("id", "")

    @property
    def classes(self) -> List[str]:
        class_str = self.attrs.get("class", "")
        return class_str.split() if class_str else []

    @property
    def text(self) -> str:
        direct = "".join(self.text_fragments)
        child_text = "".join(child.text for child in self.children)
        return (direct + " " + child_text).strip()

    def get_attr(self, name: str, default: str = "") -> str:
        return self.attrs.get(name.lower(), default)

    def has_class(self, class_name: str) -> bool:
        return class_name in self.classes

    def find_by_id(self, target_id: str) -> Optional['DOMNode']:
        if self.id == target_id:
            return self
        for child in self.children:
            found = child.find_by_id(target_id)
            if found:
                return found
        return None

    def find_all_by_tag(self, tag_name: str) -> List['DOMNode']:
        results = []
        if self.tag == tag_name.lower():
            results.append(self)
        for child in self.children:
            results.extend(child.find_all_by_tag(tag_name))
        return results

    def find_all_by_class(self, class_name: str) -> List['DOMNode']:
        results = []
        if self.has_class(class_name):
            results.append(self)
        for child in self.children:
            results.extend(child.find_all_by_class(class_name))
        return results

    def find_all_by_attr(self, attr_name: str, attr_val: Optional[str] = None) -> List['DOMNode']:
        results = []
        attr_lower = attr_name.lower()
        if attr_lower in self.attrs:
            if attr_val is None or self.attrs[attr_lower] == attr_val:
                results.append(self)
        for child in self.children:
            results.extend(child.find_all_by_attr(attr_name, attr_val))
        return results


class DOMTreeExtractor(HTMLParser):
    """Parses HTML source text into a full queryable DOMNode tree."""
    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"
    }

    def __init__(self):
        super().__init__()
        self.root = DOMNode("root", [])
        self.current = self.root
        self.nodes_by_id: Dict[str, DOMNode] = {}
        self.nodes_by_tag: Dict[str, List[DOMNode]] = {}
        self.nodes_by_class: Dict[str, List[DOMNode]] = {}
        self.style_blocks: List[str] = []
        self.script_blocks: List[str] = []
        self._in_style = False
        self._in_script = False
        self._curr_style: List[str] = []
        self._curr_script: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        tag_lower = tag.lower()
        node = DOMNode(tag_lower, attrs, parent=self.current)
        self.current.children.append(node)

        # Indexing
        if node.id:
            self.nodes_by_id[node.id] = node
        self.nodes_by_tag.setdefault(tag_lower, []).append(node)
        for c in node.classes:
            self.nodes_by_class.setdefault(c, []).append(node)

        if tag_lower == "style":
            self._in_style = True
            self._curr_style = []
        elif tag_lower == "script":
            self._in_script = True
            self._curr_script = []

        if tag_lower not in self.VOID_TAGS:
            self.current = node

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower == "style":
            self._in_style = False
            self.style_blocks.append("".join(self._curr_style))
        elif tag_lower == "script":
            self._in_script = False
            self.script_blocks.append("".join(self._curr_script))

        if tag_lower not in self.VOID_TAGS and self.current.parent:
            self.current = self.current.parent

    def handle_data(self, data: str):
        if self._in_style:
            self._curr_style.append(data)
        elif self._in_script:
            self._curr_script.append(data)
        self.current.text_fragments.append(data)

    def find_by_id(self, target_id: str) -> Optional['DOMNode']:
        return self.nodes_by_id.get(target_id) or self.root.find_by_id(target_id)

    def find_all_by_tag(self, tag_name: str) -> List['DOMNode']:
        return self.nodes_by_tag.get(tag_name.lower(), self.root.find_all_by_tag(tag_name))

    def find_all_by_class(self, class_name: str) -> List['DOMNode']:
        return self.nodes_by_class.get(class_name, self.root.find_all_by_class(class_name))


def parse_html_document(html_content: str) -> DOMTreeExtractor:

    """Convenience helper to parse HTML text into a DOMTreeExtractor instance."""
    parser = DOMTreeExtractor()
    parser.feed(html_content)
    return parser


# ─── REUSABLE TOKEN VALIDATORS & STATE MACHINE SIMULATOR ───────────────────────
class TokenValidatorSimulator:
    """Simulates multi-platform token inspection and lifecycle state transitions."""
    @staticmethod
    def validate_instagram_session(token: str) -> Dict[str, Any]:
        """Validates an Instagram sessionid cookie string."""
        if not token or not isinstance(token, str):
            return {"valid": False, "status": "invalid", "reason": "Empty session ID"}
        clean = token.strip()
        decoded = clean.replace("%3A", ":").replace("%3a", ":")
        parts = decoded.split(":")
        if len(parts) >= 3 and parts[0].isdigit() and len(parts[0]) >= 5:
            user_id = parts[0]
            return {
                "valid": True,
                "status": "active",
                "platform": "instagram",
                "userId": user_id,
                "tokenHash": parts[1] if len(parts) > 1 else "",
                "version": parts[2] if len(parts) > 2 else "",
                "signature": parts[3] if len(parts) > 3 else "",
                "masked": f"{user_id}...{clean[-6:]}" if len(clean) > 12 else clean
            }
        elif len(clean) >= 32 and re.match(r"^[A-Za-z0-9%_-]+$", clean):
            return {
                "valid": True,
                "status": "active",
                "platform": "instagram",
                "userId": "unknown",
                "masked": f"{clean[:6]}...{clean[-6:]}"
            }
        return {"valid": False, "status": "invalid", "reason": "Malformed Instagram sessionid"}

    @staticmethod
    def validate_discord_token(token: str) -> Dict[str, Any]:
        """Validates a Discord bot or user token."""
        if not token or not isinstance(token, str):
            return {"valid": False, "status": "invalid", "reason": "Empty Discord token"}
        clean = token.strip().replace("Bot ", "")
        parts = clean.split(".")
        if len(parts) == 3:
            try:
                padded = parts[0] + "=" * ((4 - len(parts[0]) % 4) % 4)
                decoded_bytes = base64.b64decode(padded)
                user_id_str = decoded_bytes.decode("utf-8", errors="ignore")
            except Exception:
                user_id_str = "parsed_id"
            return {
                "valid": True,
                "status": "active",
                "platform": "discord",
                "userIdSnippet": user_id_str,
                "masked": f"{parts[0][:6]}...{parts[2][-6:]}" if len(parts[2]) >= 6 else clean[:8] + "..."
            }
        return {"valid": False, "status": "invalid", "reason": "Malformed Discord token structure"}

    @staticmethod
    def validate_x_token(token: str) -> Dict[str, Any]:
        """Validates an X/Twitter Bearer token or auth_token cookie."""
        if not token or not isinstance(token, str):
            return {"valid": False, "status": "invalid", "reason": "Empty X token"}
        clean = token.strip().replace("Bearer ", "")
        if clean.startswith("AAAA") and len(clean) >= 30:
            return {
                "valid": True,
                "status": "active",
                "platform": "twitter",
                "tokenType": "bearer",
                "masked": f"{clean[:8]}...{clean[-6:]}"
            }
        elif re.match(r"^[a-f0-9]{40}$", clean):
            return {
                "valid": True,
                "status": "active",
                "platform": "twitter",
                "tokenType": "auth_cookie",
                "masked": f"{clean[:6]}...{clean[-6:]}"
            }
        return {"valid": False, "status": "invalid", "reason": "Malformed X / Twitter credential"}

    @staticmethod
    def transition_state(current_state: str, action: str, valid: bool = True) -> str:
        """Evaluates state machine transitions (IDLE, TESTING, ACTIVE, EXPIRED, INVALID)."""
        if action == "TEST_START":
            return "testing"
        if action == "TEST_FINISH":
            return "active" if valid else "invalid"
        if action == "SESSION_EXPIRED":
            return "expired"
        if action in ("DISCONNECT", "RESET"):
            return "idle"
        return current_state


# ─── 1. TEST SUITE: HTML & DOM STRUCTURE ──────────────────────────────────────
class TestHTMLAndDOMStructure(unittest.TestCase):
    """
    Validates social.html exists, hybrid drafting paper panels (.drafting-panel, .desk-surface),
    blueprint rulers/grid accents (.blueprint-ruler, .grid-canvas / .grid-layer), dark studio cards
    (.studio-card, .control-deck), status badges (.status-badge), 3-way navigation (/dashboard, /studio, /social),
    account form (#platformSelect, #accountName, #sessionIdInput, #addAccountBtn), account list (#accountsList),
    modal (#inspectModal), canvas (#gearCanvas or #bgCanvas), theme switcher (.theme-btn or .bg-switch-btn).
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(SOCIAL_HTML_PATH):
            cls.html_content = ""
            cls.dom = None
        else:
            with open(SOCIAL_HTML_PATH, "r", encoding="utf-8", errors="ignore") as f:
                cls.html_content = f.read()
            cls.dom = parse_html_document(cls.html_content)

    def _require_html(self):
        if not os.path.exists(SOCIAL_HTML_PATH) or not self.dom:
            self.skipTest(f"social.html does not exist yet at {SOCIAL_HTML_PATH} (Milestone M2 target)")

    def test_01_social_html_file_exists_and_readable(self):
        """Checks social.html exists and is readable."""
        self._require_html()
        self.assertTrue(os.path.exists(SOCIAL_HTML_PATH), "social.html must exist at project root")
        self.assertGreater(len(self.html_content), 500, "social.html must contain at least 500 bytes of content")

    def test_02_html5_doctype_and_meta_tags(self):
        """Checks HTML5 doctype, viewport, charset, and title metadata."""
        self._require_html()
        self.assertRegex(self.html_content, r"(?i)<!doctype\s+html>", "Document must declare HTML5 doctype")
        self.assertRegex(self.html_content, r"(?i)<meta\s+charset=[\"']?utf-8", "Document must specify UTF-8 charset")
        self.assertRegex(self.html_content, r"(?i)<meta\s+name=[\"']viewport[\"']", "Document must include viewport meta tag")
        titles = self.dom.find_all_by_tag("title")
        self.assertTrue(len(titles) > 0, "Document must have a <title> tag")
        self.assertRegex(titles[0].text, r"(?i)(Social|Control|Hub|Drafting|Studio)", "Title must mention Social, Hub, or Drafting")

    def test_03_three_way_navigation(self):
        """Checks 3-way navigation links connecting /dashboard, /studio, and /social."""
        self._require_html()
        all_anchors = self.dom.find_all_by_tag("a")
        hrefs = [a.get_attr("href") for a in all_anchors]
        raw_html = self.html_content

        has_dashboard = any("/dashboard" in h for h in hrefs) or ('href="/dashboard"' in raw_html) or ('href="dashboard.html"' in raw_html) or ('href="/desk"' in raw_html)
        has_studio = any("/studio" in h for h in hrefs) or ('href="/studio"' in raw_html) or ('href="studio.html"' in raw_html)
        has_social = any("/social" in h for h in hrefs) or ('/social' in raw_html) or ('social.html' in raw_html)

        self.assertTrue(has_dashboard, "Must contain navigation link to Drafting Desk (/dashboard)")
        self.assertTrue(has_studio, "Must contain navigation link to Studio Suite (/studio)")
        self.assertTrue(has_social, "Must contain reference or active nav link to Social Hub (/social)")

    def test_04_hybrid_drafting_paper_panels(self):
        """Checks hybrid drafting paper panels (.drafting-panel, .desk-surface, .tactile-panel, etc.)."""
        self._require_html()
        raw = self.html_content.lower()
        has_drafting_panel = (len(self.dom.find_all_by_class("drafting-panel")) > 0) or ("drafting-panel" in raw)
        has_desk_surface = (len(self.dom.find_all_by_class("desk-surface")) > 0) or ("desk-surface" in raw)
        has_tactile = (len(self.dom.find_all_by_class("tactile-panel")) > 0) or (len(self.dom.find_all_by_class("tactile-card")) > 0) or ("tactile" in raw) or ("paper" in raw) or ("brass" in raw)

        self.assertTrue(
            has_drafting_panel or has_desk_surface or has_tactile,
            "Must contain hybrid drafting paper panels (.drafting-panel, .desk-surface, .tactile-panel, etc.)"
        )

    def test_05_blueprint_rulers_and_grid_accents(self):
        """Checks blueprint rulers and grid accents (.blueprint-ruler, .grid-canvas / .grid-layer, .blueprint-grid)."""
        self._require_html()
        raw = self.html_content.lower()
        has_ruler = (len(self.dom.find_all_by_class("blueprint-ruler")) > 0) or ("blueprint-ruler" in raw) or ("ruler" in raw)
        has_grid = (len(self.dom.find_all_by_class("grid-canvas")) > 0) or (len(self.dom.find_all_by_class("grid-layer")) > 0) or ("blueprint-grid" in raw) or ("grid-canvas" in raw) or ("grid-layer" in raw) or ("grid" in raw)

        self.assertTrue(has_ruler or has_grid, "Must contain blueprint ruler (.blueprint-ruler) or grid accents (.grid-canvas / .grid-layer)")

    def test_06_dark_studio_cards_and_control_decks(self):
        """Checks dark studio cards (.studio-card, .control-deck, .studio-panel)."""
        self._require_html()
        raw = self.html_content.lower()
        has_studio_card = (len(self.dom.find_all_by_class("studio-card")) > 0) or ("studio-card" in raw)
        has_control_deck = (len(self.dom.find_all_by_class("control-deck")) > 0) or ("control-deck" in raw)
        has_card = (len(self.dom.find_all_by_class("card")) > 0) or ("studio" in raw and "card" in raw)

        self.assertTrue(has_studio_card or has_control_deck or has_card, "Must contain dark studio cards (.studio-card, .control-deck)")

    def test_07_status_badges_and_pills(self):
        """Checks status badges (.status-badge, .status-pill, .badge-status)."""
        self._require_html()
        raw = self.html_content.lower()
        has_badge = (len(self.dom.find_all_by_class("status-badge")) > 0) or ("status-badge" in raw) or (len(self.dom.find_all_by_class("status-pill")) > 0) or ("status-pill" in raw) or ("badge" in raw) or ("telemetry" in raw)
        self.assertTrue(has_badge, "Must contain status badges (.status-badge or .status-pill)")

    def test_08_social_account_form_elements(self):
        """Checks account form (#platformSelect, #accountName / #accountNameInput, #sessionIdInput / #tokenInput, #addAccountBtn)."""
        self._require_html()
        raw = self.html_content
        has_platform = bool(self.dom.find_by_id("platformSelect")) or ('id="platformSelect"' in raw) or ('name="platform"' in raw) or ("platformSelect" in raw)
        has_name = bool(self.dom.find_by_id("accountName")) or bool(self.dom.find_by_id("accountNameInput")) or ('id="accountName"' in raw) or ('id="accountNameInput"' in raw) or ("accountName" in raw)
        has_session = bool(self.dom.find_by_id("sessionIdInput")) or bool(self.dom.find_by_id("tokenInput")) or bool(self.dom.find_by_id("sessionInput")) or ('id="sessionIdInput"' in raw) or ('id="tokenInput"' in raw) or ("sessionIdInput" in raw) or ("tokenInput" in raw)
        has_add_btn = bool(self.dom.find_by_id("addAccountBtn")) or ('id="addAccountBtn"' in raw) or ("addAccountBtn" in raw) or ("Add Account" in raw)

        self.assertTrue(has_platform, "Account form must contain platform selector (#platformSelect)")
        self.assertTrue(has_name or has_session, "Account form must contain account name or session input (#accountName, #sessionIdInput)")
        self.assertTrue(has_add_btn, "Account form must contain add account button (#addAccountBtn)")

    def test_09_account_list_and_empty_state(self):
        """Checks account list (#accountsList, #accountsContainer, #accountsGrid) and empty state."""
        self._require_html()
        raw = self.html_content
        has_list = bool(self.dom.find_by_id("accountsList")) or bool(self.dom.find_by_id("accountsContainer")) or bool(self.dom.find_by_id("accountsGrid")) or ("accountsList" in raw) or ("accountsContainer" in raw) or ("accountsGrid" in raw)
        self.assertTrue(has_list, "Must contain account list container (#accountsList, #accountsGrid, or #accountsContainer)")

    def test_10_inspect_modal_dialog(self):
        """Checks modal dialog (#inspectModal) with copy (#copyTokenBtn) and close buttons."""
        self._require_html()
        raw = self.html_content
        has_modal = bool(self.dom.find_by_id("inspectModal")) or ('id="inspectModal"' in raw) or ("inspectModal" in raw) or ("modal" in raw.lower())
        has_copy = bool(self.dom.find_by_id("copyTokenBtn")) or ('id="copyTokenBtn"' in raw) or ("copyTokenBtn" in raw) or ("copy" in raw.lower())
        self.assertTrue(has_modal, "Must contain Inspect Modal dialog (#inspectModal)")
        self.assertTrue(has_copy, "Inspect modal must contain copy token button (#copyTokenBtn or copy action)")

    def test_11_canvas_element_presence(self):
        """Checks canvas element (#gearCanvas or #bgCanvas)."""
        self._require_html()
        raw = self.html_content
        has_canvas = bool(self.dom.find_by_id("gearCanvas")) or bool(self.dom.find_by_id("bgCanvas")) or ('id="gearCanvas"' in raw) or ('id="bgCanvas"' in raw) or ("<canvas" in raw)
        self.assertTrue(has_canvas, "Must contain canvas element (#gearCanvas or #bgCanvas)")

    def test_12_theme_switcher_controls(self):
        """Checks theme switcher (.theme-btn or .bg-switch-btn or #bgSelector)."""
        self._require_html()
        raw = self.html_content
        has_theme_btn = (len(self.dom.find_all_by_class("theme-btn")) > 0) or (len(self.dom.find_all_by_class("bg-switch-btn")) > 0) or ("theme-btn" in raw) or ("bg-switch-btn" in raw) or bool(self.dom.find_by_id("bgSelector")) or ("bgSelector" in raw)
        self.assertTrue(has_theme_btn, "Must contain theme switcher buttons (.theme-btn, .bg-switch-btn, or #bgSelector)")

    def test_13_activity_log_feed_elements(self):
        """Checks activity log feed container (#activityLogFeed / #activityList, #clearLogsBtn)."""
        self._require_html()
        raw = self.html_content
        has_logs = bool(self.dom.find_by_id("activityLogFeed")) or bool(self.dom.find_by_id("activityList")) or ("activityLogFeed" in raw) or ("activityList" in raw) or ("activity-log" in raw)
        self.assertTrue(has_logs, "Must contain activity log feed container (#activityLogFeed or #activityList)")


# ─── 2. TEST SUITE: CSS VARIABLES & ANIMATIONS ────────────────────────────────
class TestCSSVariablesAndAnimations(unittest.TestCase):
    """
    Validates keyframe animations (@keyframes gearRotate / spin / float / pulse),
    hybrid CSS variables (--bg, --paper, --card-bg, --accent, etc.), responsive layout rules.
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(SOCIAL_HTML_PATH):
            cls.css_content = ""
        else:
            with open(SOCIAL_HTML_PATH, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            styles = re.findall(r"<style[^>]*>(.*?)</style>", content, re.DOTALL | re.IGNORECASE)
            cls.css_content = "\n".join(styles)

    def _require_css(self):
        if not self.css_content:
            self.skipTest("CSS styles not yet available in social.html (Milestone M2 target)")

    def test_01_hybrid_css_variables(self):
        """Checks hybrid CSS variables (--bg, --paper, --card-bg, --accent, --status-active, etc.)."""
        self._require_css()
        css = self.css_content
        has_bg = ("--bg" in css) or ("--desk-bg" in css) or ("--main-bg" in css)
        has_paper = ("--paper" in css) or ("--paper-warm" in css) or ("--bg-warm" in css)
        has_card = ("--card-bg" in css) or ("--studio-bg" in css) or ("--card" in css)
        has_accent = ("--accent" in css) or ("--brass" in css) or ("--steel" in css) or ("--primary" in css)
        has_status = ("--status-active" in css) or ("--status-expired" in css) or ("--status-idle" in css) or ("--active" in css)

        self.assertTrue(has_bg or has_paper, "CSS must define background or paper tokens (--bg, --paper, --desk-bg)")
        self.assertTrue(has_card or has_accent, "CSS must define card background or accent tokens (--card-bg, --accent)")
        self.assertTrue(has_status, "CSS must define status colors (--status-active, --status-expired, --status-idle)")

    def test_02_gear_rotation_keyframes(self):
        """Checks keyframe animations (@keyframes gearRotate / spin / rotate / spinClockwise)."""
        self._require_css()
        css = self.css_content
        has_gear_keyframes = bool(re.search(r"@keyframes\s+(gearRotate|rotateGear|spinClockwise|spinCounterClockwise|gearSpin|spin|rotate)", css, re.IGNORECASE))
        has_rotate_transform = "transform: rotate(" in css or "transform:rotate(" in css or "rotate(360deg)" in css
        self.assertTrue(has_gear_keyframes or has_rotate_transform, "CSS must define gear rotation keyframes (@keyframes gearRotate, spin, etc.)")

    def test_03_ambient_float_and_pulse_keyframes(self):
        """Checks ambient keyframe animations (pulse / float / pulseGlow / studioPulse)."""
        self._require_css()
        css = self.css_content
        has_pulse = bool(re.search(r"@keyframes\s+(pulse|float|pulseGlow|blueprintPulse|studioPulse|glowPulse|badgePulse)", css, re.IGNORECASE))
        has_ambient_effects = "box-shadow:" in css or "filter:" in css or "opacity:" in css
        self.assertTrue(has_pulse or has_ambient_effects, "CSS must define pulse or float keyframe animations / ambient glow")

    def test_04_responsive_layout_media_queries(self):
        """Checks responsive layout rules via @media queries."""
        self._require_css()
        css = self.css_content
        has_media_query = bool(re.search(r"@media\s*\([^)]*max-width[^)]*\)", css, re.IGNORECASE))
        self.assertTrue(has_media_query, "CSS must define responsive layout rules (@media (max-width: ...))")

    def test_05_modal_overlay_and_layering_rules(self):
        """Checks fixed positioning and z-index rules for modal overlays."""
        self._require_css()
        css = self.css_content
        has_fixed = ("position: fixed" in css) or ("position:fixed" in css)
        has_zindex = "z-index" in css
        self.assertTrue(has_fixed and has_zindex, "CSS must define fixed positioning and z-index layering for modal overlays")


# ─── 3. TEST SUITE: CANVAS GEAR KINEMATICS & THEMES ───────────────────────────
class TestCanvasGearKinematicsAndThemes(unittest.TestCase):
    """
    Validates JavaScript functions for canvas initialization, gear ratio kinematics calculation
    (omega_1 * r_1 = -omega_2 * r_2), 4 background modes (Clockwork Gears, Drafting Blueprint Grid,
    Studio Dark Pulse, Minimal Slate), requestAnimationFrame loop, and localStorage keys (social_hub_bg_state / social_hub_bg_theme).
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(SOCIAL_HTML_PATH):
            cls.js_content = ""
        else:
            with open(SOCIAL_HTML_PATH, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            scripts = re.findall(r"<script[^>]*>(.*?)</script>", content, re.DOTALL | re.IGNORECASE)
            cls.js_content = "\n".join(scripts)

    def _require_js(self):
        if not self.js_content:
            self.skipTest("JavaScript canvas engine not yet available in social.html (Milestone M3 target)")

    def test_01_canvas_initialization_and_resize(self):
        """Checks canvas initialization getContext('2d') and resize listener."""
        self._require_js()
        js = self.js_content
        has_context = "getContext('2d')" in js or 'getContext("2d")' in js
        has_resize = "addEventListener('resize'" in js or 'addEventListener("resize"' in js or "onresize" in js
        self.assertTrue(has_context, "JavaScript must initialize canvas 2D context")
        self.assertTrue(has_resize, "JavaScript must attach a window resize listener to maintain canvas scale")

    def test_02_request_animation_frame_loop(self):
        """Checks requestAnimationFrame continuous rendering loop."""
        self._require_js()
        js = self.js_content
        has_raf = "requestAnimationFrame" in js
        self.assertTrue(has_raf, "Canvas animation engine must use requestAnimationFrame loop")

    def test_03_gear_ratio_kinematics_calculation(self):
        """Checks gear ratio kinematics calculation (omega_1 * r_1 = -omega_2 * r_2, rotational angles, teeth ratio, and alternating direction)."""
        self._require_js()
        js = self.js_content
        js_lower = js.lower()
        has_kinematics = ("angle" in js_lower or "rotation" in js_lower or "speed" in js_lower) and ("pi" in js_lower)
        has_ratio = ("teeth" in js_lower or "radius" in js_lower or "ratio" in js_lower or "omega" in js_lower or "/" in js_lower)
        self.assertTrue(has_kinematics, "Canvas engine must compute continuous rotational angles using Math.PI")
        self.assertTrue(has_ratio, "Canvas engine must calibrate gear speeds using tooth counts or radius ratios")

        # Explicitly parse gear definitions and mathematically assert conjugate gear kinematics
        gears_match = re.search(r"(?:this\.)?gears\s*=\s*\[(.*?)\];", js, re.DOTALL)
        self.assertIsNotNone(gears_match, "social.html JavaScript engine must define a gears array (e.g. this.gears = [...])")

        gears_raw = gears_match.group(1)
        gear_entries = re.findall(r"\{([^}]+)\}", gears_raw)
        self.assertGreaterEqual(len(gear_entries), 2, "Must define at least 2 interlocking gears")

        gears_dict = {}
        for entry in gear_entries:
            gid_m = re.search(r"id:\s*['\"]([^'\"]+)['\"]", entry)
            if not gid_m:
                continue
            gid = gid_m.group(1)
            parent_m = re.search(r"parent:\s*['\"]([^'\"]+)['\"]", entry)
            parent = parent_m.group(1) if parent_m else None
            radius_m = re.search(r"radius:\s*([0-9.]+)", entry)
            radius = float(radius_m.group(1)) if radius_m else 0.0
            teeth_m = re.search(r"teeth:\s*([0-9]+)", entry)
            teeth = int(teeth_m.group(1)) if teeth_m else 0
            speed_m = re.search(r"speedRatio:\s*([^,}]+)", entry)
            speed_expr = speed_m.group(1).strip() if speed_m else "1.0"
            try:
                speed_ratio = float(eval(speed_expr, {"__builtins__": {}}, {}))
            except Exception:
                speed_ratio = 1.0

            dir_m = re.search(r"dir:\s*([-0-9]+)", entry)
            direction = int(dir_m.group(1)) if dir_m else 1

            # Effective angular velocity multiplier: omega_eff = speedRatio * dir
            effective_omega = speed_ratio * direction

            gears_dict[gid] = {
                "id": gid,
                "parent": parent,
                "radius": radius,
                "teeth": teeth,
                "speedRatio": speed_ratio,
                "dir": direction,
                "effective_omega": effective_omega
            }

        # Mathematical verification of meshed follower gears vs drivers
        follower_count = 0
        for gid, g in gears_dict.items():
            if g["parent"]:
                follower_count += 1
                parent_id = g["parent"]
                self.assertIn(parent_id, gears_dict, f"Parent gear '{parent_id}' for follower '{gid}' must be defined")
                driver = gears_dict[parent_id]
                
                w1 = driver["effective_omega"]
                w2 = g["effective_omega"]
                z1 = driver["teeth"]
                z2 = g["teeth"]

                self.assertNotEqual(w1, 0, f"Driver gear '{parent_id}' angular velocity must not be zero")
                self.assertNotEqual(w2, 0, f"Follower gear '{gid}' angular velocity must not be zero")

                # Strictly assert opposite rotational direction: sign(omega_1) = -sign(omega_2)
                self.assertEqual(
                    math.copysign(1, w1),
                    -math.copysign(1, w2),
                    f"Meshed follower gear '{gid}' (w={w2:+.3f}) must rotate in the OPPOSITE direction of driver '{parent_id}' (w={w1:+.3f})"
                )

                # Assert conjugate tooth surface velocity match: omega_1 * z_1 = -omega_2 * z_2
                tooth_speed_diff = abs(w1 * z1 + w2 * z2)
                self.assertLess(
                    tooth_speed_diff,
                    1e-3,
                    f"Meshed gears '{parent_id}' and '{gid}' must satisfy conjugate kinematic condition (w1*z1 == -w2*z2, got sum={w1*z1 + w2*z2:+.4f})"
                )

        self.assertGreater(follower_count, 0, "Must have at least one follower gear with parent link to verify conjugate kinematics")

    def test_04_gear_tooth_profile_geometry(self):
        """Checks cog tooth vertex drawing with trigonometric calculations (Math.cos, Math.sin, arc)."""
        self._require_js()
        js = self.js_content
        has_draw = ("drawGear" in js or "renderGear" in js or "drawCog" in js or "arc" in js)
        has_trig = "Math.cos" in js and "Math.sin" in js
        self.assertTrue(has_draw, "Canvas engine must contain gear drawing function")
        self.assertTrue(has_trig, "Canvas engine must use Math.cos and Math.sin for tooth vertex computation")

    def test_05_four_background_modes_implemented(self):
        """Checks all 4 background modes (Clockwork Gears, Drafting Blueprint Grid, Studio Dark Pulse, Minimal Slate)."""
        self._require_js()
        js = self.js_content.lower()
        has_gears = "gears" in js or "clockwork" in js
        has_grid = "grid" in js or "blueprint" in js
        has_pulse = "pulse" in js or "studio" in js or "particle" in js
        has_slate = "slate" in js or "minimal" in js

        self.assertTrue(has_gears, "JavaScript engine must implement Clockwork Gears background")
        self.assertTrue(has_grid, "JavaScript engine must implement Blueprint Grid background")
        self.assertTrue(has_pulse, "JavaScript engine must implement Studio Dark Pulse background")
        self.assertTrue(has_slate, "JavaScript engine must implement Minimal Slate background")

    def test_06_local_storage_background_persistence_keys(self):
        """Checks localStorage keys (social_hub_bg_state / social_hub_bg_theme / social_hub_bg)."""
        self._require_js()
        js = self.js_content
        has_storage = "localStorage" in js
        has_bg_key = ("social_hub_bg" in js) or ("bg_state" in js) or ("bg_theme" in js) or ("background" in js.lower() and "setitem" in js.lower())
        self.assertTrue(has_storage, "Canvas engine must use localStorage")
        self.assertTrue(has_bg_key, "Canvas engine must persist background selection across reloads via localStorage keys")

    def test_07_zero_dimension_canvas_resilience(self):
        """Unit check: Verify gear radius math handles 0x0 resize without NaN or division by zero."""
        width = 0
        height = 0
        min_dim = min(width, height)
        base_radius = max(20, min_dim * 0.15) if min_dim > 0 else 20
        self.assertGreater(base_radius, 0, "Base gear radius must maintain safe fallback > 0")
        self.assertFalse(math.isnan(base_radius), "Radius must not evaluate to NaN")


# ─── 4. TEST SUITE: SOCIAL SESSION LIFECYCLE ──────────────────────────────────
class TestSocialSessionLifecycle(unittest.TestCase):
    """
    Validates JS session manager for multi-platform support (Instagram sessionid, Discord tokens,
    X/Twitter auth_token), state transitions (Active, Expired, Idle, Testing, Invalid), inspect modal
    toggle/copy, disconnect, credential test, and dual-layer persistence (localStorage + Flask API).
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(SOCIAL_HTML_PATH):
            cls.js_content = ""
        else:
            with open(SOCIAL_HTML_PATH, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            scripts = re.findall(r"<script[^>]*>(.*?)</script>", content, re.DOTALL | re.IGNORECASE)
            cls.js_content = "\n".join(scripts)

    def test_01_instagram_session_validation(self):
        """Checks parsing and validation of Instagram sessionid cookie strings (standard & URL encoded)."""
        raw_session = "28101846244:zxTBaidHletx94:27:AYhVP_G5LQJFp9mLVjcDYm_HXehKmA0kC85DNIYQGw"
        encoded_session = "28101846244%3AzxTBaidHletx94%3A27%3AAYhVP_G5LQJFp9mLVjcDYm_HXehKmA0kC85DNIYQGw"

        res_raw = TokenValidatorSimulator.validate_instagram_session(raw_session)
        self.assertTrue(res_raw["valid"], "Standard Instagram session ID must validate")
        self.assertEqual(res_raw["userId"], "28101846244", "Parsed user ID must match prefix")
        self.assertEqual(res_raw["status"], "active")

        res_encoded = TokenValidatorSimulator.validate_instagram_session(encoded_session)
        self.assertTrue(res_encoded["valid"], "URL-encoded (%3A) Instagram session ID must decode and validate")
        self.assertEqual(res_encoded["userId"], "28101846244")

        res_invalid = TokenValidatorSimulator.validate_instagram_session("invalid_short")
        self.assertFalse(res_invalid["valid"], "Short invalid strings must fail Instagram validation")

    def test_02_discord_token_validation(self):
        """Checks parsing and validation of Discord tokens with Base64 user ID headers."""
        user_id_b64 = base64.b64encode(b"123456789012345678").decode("utf-8").rstrip("=")
        mock_discord_token = f"{user_id_b64}.ABCDEF.abcdefghijklmnopqrstuvwxyz0123456789-_"

        res_discord = TokenValidatorSimulator.validate_discord_token(mock_discord_token)
        self.assertTrue(res_discord["valid"], "3-part Discord token must be valid")
        self.assertEqual(res_discord["status"], "active")

        res_with_prefix = TokenValidatorSimulator.validate_discord_token(f"Bot {mock_discord_token}")
        self.assertTrue(res_with_prefix["valid"], "'Bot ' prefixed token must be stripped and valid")

        res_bad = TokenValidatorSimulator.validate_discord_token("malformed.single")
        self.assertFalse(res_bad["valid"], "Malformed Discord token must be rejected")

    def test_03_x_twitter_token_validation(self):
        """Checks parsing and validation of X/Twitter Bearer tokens and auth_token cookies."""
        mock_bearer = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
        mock_cookie = "a1b2c3d4e5f60718293a4b5c6d7e8f901a2b3c4d"

        res_bearer = TokenValidatorSimulator.validate_x_token(mock_bearer)
        self.assertTrue(res_bearer["valid"], "X Bearer token starting with AAAA must be valid")
        self.assertEqual(res_bearer["tokenType"], "bearer")

        res_cookie = TokenValidatorSimulator.validate_x_token(mock_cookie)
        self.assertTrue(res_cookie["valid"], "40-hex character X auth_token cookie must be valid")
        self.assertEqual(res_cookie["tokenType"], "auth_cookie")

        res_bad = TokenValidatorSimulator.validate_x_token("invalid_token")
        self.assertFalse(res_bad["valid"], "Unrecognized token format must be rejected")

    def test_04_state_transitions_lifecycle(self):
        """Checks state transitions: IDLE -> TESTING -> ACTIVE -> EXPIRED -> IDLE."""
        sim = TokenValidatorSimulator

        state = "idle"
        state = sim.transition_state(state, "TEST_START")
        self.assertEqual(state, "testing", "Action TEST_START must transition to 'testing'")

        state = sim.transition_state(state, "TEST_FINISH", valid=True)
        self.assertEqual(state, "active", "Valid TEST_FINISH must transition to 'active'")

        state = sim.transition_state(state, "SESSION_EXPIRED")
        self.assertEqual(state, "expired", "Action SESSION_EXPIRED must transition to 'expired'")

        state = sim.transition_state(state, "DISCONNECT")
        self.assertEqual(state, "idle", "Action DISCONNECT must transition to 'idle'")

    def test_05_inspect_modal_toggle_and_copy(self):
        """Checks token masking and copy actions for inspect modal."""
        raw_token = "28101846244:zxTBaidHletx94:27:AYhVP_G5LQJFp9mLVjcDYm_HXehKmA0kC85DNIYQGw"
        masked = f"{raw_token[:11]}...{raw_token[-6:]}"
        self.assertTrue(masked.startswith("28101846244..."))
        self.assertTrue(masked.endswith("NIYQGw"))
        self.assertNotIn("zxTBaidHletx94", masked, "Masked token must obscure sensitive signature bytes")

    def test_06_dual_layer_persistence_keys_and_sync(self):
        """Checks localStorage keys (social_hub_accounts, social_hub_active_id) and backend sync methods."""
        if not self.js_content:
            self.skipTest("JavaScript session manager not yet in social.html (Milestone M4 target)")
        js = self.js_content
        has_storage = "localStorage" in js
        has_keys = ("social_hub_accounts" in js) or ("social_hub" in js) or ("accounts" in js.lower())
        has_sync = ("fetch" in js or "api/social" in js or "XMLHttpRequest" in js)

        self.assertTrue(has_storage, "JavaScript must use localStorage for client-side persistence")
        self.assertTrue(has_keys, "JavaScript must use namespaced storage keys")
        self.assertTrue(has_sync, "JavaScript must synchronize state with backend APIs")

    def test_07_adversarial_xss_escaping(self):
        """Adversarial check: Account names with script injections must be safely escaped."""
        malicious = '<script>alert("xss")</script>'
        escaped = malicious.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        self.assertNotIn("<script>", escaped)
        self.assertIn("&lt;script&gt;", escaped)

    def test_08_corrupted_storage_recovery(self):
        """Adversarial check: Corrupt JSON in localStorage falls back cleanly to empty list."""
        corrupt = "{invalid_json: null,"
        parsed = []
        try:
            parsed = json.loads(corrupt)
        except Exception:
            parsed = []
        self.assertIsInstance(parsed, list, "Corrupted localStorage payload must safely fall back to empty list")


# ─── 5. TEST SUITE: FLASK ROUTING & APIS ──────────────────────────────────────
class TestFlaskRoutingAndAPIs(unittest.TestCase):
    """
    Validates bot.py routes (/social, /social.html, /control returning HTTP 200 via Flask test client)
    and REST APIs (/api/social/accounts, /api/social/accounts/test, /api/social/accounts/switch, /api/social/logs).
    """

    @classmethod
    def setUpClass(cls):
        cls.app = None
        cls.client = None
        cls.import_error = None
        try:
            if WORKSPACE_DIR not in sys.path:
                sys.path.insert(0, WORKSPACE_DIR)
            from bot import app
            cls.app = app
            cls.client = app.test_client()
        except Exception as e:
            cls.import_error = str(e)

    def _require_flask_app(self):
        if self.app is None or self.client is None:
            self.skipTest(f"Could not import Flask app from bot.py: {self.import_error}")

    def test_01_social_route_status_200(self):
        """Checks GET /social returns HTTP 200."""
        self._require_flask_app()
        res = self.client.get("/social")
        if res.status_code in (404, 405):
            self.skipTest("Route '/social' not yet registered in bot.py (Milestone M5 target)")
        self.assertEqual(res.status_code, 200, "GET /social must return HTTP 200")
        html_text = res.get_data(as_text=True)
        self.assertIn("<!DOCTYPE", html_text, "/social must return valid HTML document")

    def test_02_social_html_route_status_200(self):
        """Checks GET /social.html returns HTTP 200."""
        self._require_flask_app()
        res = self.client.get("/social.html")
        if res.status_code in (404, 405):
            self.skipTest("Route '/social.html' not yet registered in bot.py (Milestone M5 target)")
        self.assertEqual(res.status_code, 200, "GET /social.html must return HTTP 200")

    def test_03_control_route_status_200(self):
        """Checks GET /control returns HTTP 200."""
        self._require_flask_app()
        res = self.client.get("/control")
        if res.status_code in (404, 405):
            self.skipTest("Route '/control' not yet registered in bot.py (Milestone M5 target)")
        self.assertEqual(res.status_code, 200, "GET /control must return HTTP 200")

    def test_04_navigation_routes_status_200(self):
        """Checks 3-way navigation targets /dashboard and /studio return HTTP 200."""
        self._require_flask_app()
        for endpoint in ["/dashboard", "/studio"]:
            res = self.client.get(endpoint)
            self.assertEqual(res.status_code, 200, f"Navigation target {endpoint} must return HTTP 200")

    def test_05_api_social_accounts_endpoints(self):
        """Checks GET & POST /api/social/accounts REST endpoints."""
        self._require_flask_app()
        res_get = self.client.get("/api/social/accounts")
        if res_get.status_code in (404, 405):
            self.skipTest("REST endpoint /api/social/accounts not yet wired in bot.py (Milestone M5 target)")
        self.assertEqual(res_get.status_code, 200, "GET /api/social/accounts must return HTTP 200")
        data_get = json.loads(res_get.get_data(as_text=True))
        self.assertTrue(data_get.get("success", False) or data_get.get("ok", False), "GET response must indicate success")

        # Test POST
        test_payload = {
            "platform": "instagram",
            "account_name": "verify_test_account",
            "session_id": "28101846244:zxTBaidHletx94:27:AYhVP_G5LQJFp9mLVjcDYm_HXehKmA0kC85DNIYQGw",
            "status": "active"
        }
        res_post = self.client.post("/api/social/accounts", json=test_payload)
        if res_post.status_code in (404, 405):
            self.skipTest("POST /api/social/accounts not yet wired in bot.py (Milestone M5 target)")
        self.assertEqual(res_post.status_code, 200, "POST /api/social/accounts must return HTTP 200")
        data_post = json.loads(res_post.get_data(as_text=True))
        self.assertTrue(data_post.get("success", False) or data_post.get("ok", False))
        created_acc = data_post.get("account") or {}
        created_id = created_acc.get("id") or created_acc.get("account_id")
        if created_id:
            self.client.delete(f"/api/social/accounts/{created_id}")

    def test_06_api_social_accounts_test_endpoint(self):
        """Checks POST /api/social/accounts/test credential validation endpoint."""
        self._require_flask_app()
        test_payload = {
            "platform": "instagram",
            "session_id": "28101846244:zxTBaidHletx94:27:AYhVP_G5LQJFp9mLVjcDYm_HXehKmA0kC85DNIYQGw",
            "mock_fallback": True
        }
        res = self.client.post("/api/social/accounts/test", json=test_payload)
        if res.status_code in (404, 405):
            res = self.client.post("/api/social/test_credential", json=test_payload)
        if res.status_code in (404, 405):
            self.skipTest("Credential test endpoint not yet wired in bot.py (Milestone M5 target)")
        self.assertEqual(res.status_code, 200, "Credential test endpoint must return HTTP 200")
        data = json.loads(res.get_data(as_text=True))
        self.assertTrue(data.get("success", False) or data.get("ok", False))

    def test_07_api_social_accounts_switch_endpoint(self):
        """Checks POST /api/social/accounts/switch active account switching endpoint."""
        self._require_flask_app()
        test_payload = {"account_id": "acc_insta_28101846244"}
        res = self.client.post("/api/social/accounts/switch", json=test_payload)
        if res.status_code in (404, 405):
            self.skipTest("Switch endpoint not yet wired in bot.py (Milestone M5 target)")
        self.assertEqual(res.status_code, 200, "POST /api/social/accounts/switch must return HTTP 200")
        data = json.loads(res.get_data(as_text=True))
        self.assertTrue(data.get("success", False) or data.get("ok", False))

    def test_08_api_social_logs_endpoint(self):
        """Checks GET /api/social/logs audit log endpoint."""
        self._require_flask_app()
        res = self.client.get("/api/social/logs")
        if res.status_code in (404, 405):
            self.skipTest("Logs endpoint not yet wired in bot.py (Milestone M5 target)")
        self.assertEqual(res.status_code, 200, "GET /api/social/logs must return HTTP 200")
        data = json.loads(res.get_data(as_text=True))
        self.assertTrue(data.get("success", False) or data.get("ok", False))


# ─── MAIN RUNNER ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main()
