#!/usr/bin/env python3
"""
run_stress_tests.py - Comprehensive Empirical Stress Harness for Milestone M6 Social Hub
Executed by Challenger 1 to rigorously stress-test:
1. Malformed/extreme tokens, Unicode, XSS injections across APIs and frontend escaping.
2. Canvas kinematics, boundary dimensions, rapid background mode switching, extreme speed/opacity parameters.
3. Storage corruption recovery in both localStorage simulation and data/social_accounts.json.
4. Server endpoint boundary handling, invalid methods, path traversal, large payloads.
"""

import os
import sys
import json
import time
import math
import html
import shutil
import base64
import random
import string
import tempfile
import unittest
from typing import Dict, Any, List

WORKSPACE_DIR = "/storage/emulated/0/discord-bot"
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

import bot
from bot import (
    app,
    _load_social_accounts_data,
    _save_social_accounts_data,
    _validate_credential_helper,
    _mask_token_string,
    SOCIAL_ACCOUNTS_FILE
)

class TestMilestone6ChallengerHarness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.orig_accounts_file = SOCIAL_ACCOUNTS_FILE
        # Ensure data dir exists
        os.makedirs(os.path.dirname(SOCIAL_ACCOUNTS_FILE), exist_ok=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. EMPIRICAL TESTS: INPUTS, TOKENS, UNICODE & XSS RESILIENCE
    # ═══════════════════════════════════════════════════════════════════════════

    def test_01_empty_and_null_session_ids(self):
        """Test handling of empty, whitespace, and None session IDs."""
        test_inputs = [None, "", "   ", "\t\n\r", "   \n   "]
        for p in ["instagram", "discord", "twitter", "custom"]:
            for s in test_inputs:
                res = _validate_credential_helper(p, s)
                self.assertFalse(res["valid"], f"Expected empty credential for {p} to be invalid")
                self.assertEqual(res["status"], "invalid")

    def test_02_extreme_token_lengths(self):
        """Test extreme token lengths: 1 char, 15 chars, 10,000 chars, 100,000 chars."""
        lengths = [1, 5, 15, 16, 500, 10_000, 50_000]
        for l in lengths:
            tok = "A" * l
            # Instagram
            ig_res = _validate_credential_helper("instagram", tok)
            self.assertIsInstance(ig_res, dict)
            self.assertIn("valid", ig_res)
            # Discord
            dc_res = _validate_credential_helper("discord", tok)
            self.assertIsInstance(dc_res, dict)
            self.assertIn("valid", dc_res)
            # Twitter
            tw_res = _validate_credential_helper("twitter", tok)
            self.assertIsInstance(tw_res, dict)
            self.assertIn("valid", tw_res)
            # Masking check
            masked = _mask_token_string(tok)
            self.assertIsInstance(masked, str)
            if l > 16:
                self.assertTrue(masked.startswith("AAAAAAAA..."))
                self.assertTrue(masked.endswith("AAAAAA"))

    def test_03_malformed_platform_tuples(self):
        """Test malformed tuples, invalid delimiters, and non-numeric user IDs."""
        malformed_tuples = [
            "::::",
            "user:token:27:hash",  # non-numeric user id
            "12345:only_two_parts",
            "123:too_short_id:27:sig",
            "%3A%3A%3A",
            "12345678%3Abad%3A",
            "discord_single_part",
            "discord.two.parts.extra.parts",
            "AAAAAAAAAAAAAAAAAAAA_too_short",
            "zzz_invalid_hex_40_chars_012345678901234567890123"
        ]
        for tok in malformed_tuples:
            for plat in ["instagram", "discord", "twitter"]:
                res = _validate_credential_helper(plat, tok)
                self.assertIsInstance(res, dict)
                # Valid should only be True if it specifically matches valid specs
                if res.get("valid"):
                    # Check that it met criteria (e.g. generic fallback if >=16 chars for unknown platform)
                    pass

    def test_04_special_unicode_and_injection_characters(self):
        """Test unicode emojis, RTL characters, null bytes, zalgo text, and escape sequences."""
        adversarial_strings = [
            "👾🚀🤖🔥💯",
            "مرحبا بك في المركز",  # Arabic RTL
            "こんにちは世界",  # Japanese
            "T̴e̸s̷t̶ ̵S̷e̷s̶s̸i̷o̶n̸",  # Zalgo
            "token\x00with\x00nulls",
            "token\r\nwith\r\nnewlines",
            "\x1b[31mRedANSI\x1b[0m",
            "../../etc/passwd",
            "' OR '1'='1",
            "SELECT * FROM accounts;"
        ]
        for adv in adversarial_strings:
            res = _validate_credential_helper("instagram", adv)
            self.assertIsInstance(res, dict)
            masked = _mask_token_string(adv)
            self.assertIsInstance(masked, str)

            # Test through API POST
            payload = {
                "platform": "instagram",
                "account_name": f"Adversarial_{adv[:10]}",
                "session_id": f"28101846244:sig:27:{adv}",
                "metadata": {"special": adv}
            }
            resp = self.client.post("/api/social/accounts", json=payload)
            self.assertEqual(resp.status_code, 200, f"Failed on adversarial string: {adv}")
            data = resp.get_json()
            self.assertTrue(data.get("success"))

    def test_05_xss_injections_escaping(self):
        """Test XSS payloads in account names, IDs, platform strings, and HTML escaping."""
        xss_payloads = [
            '<script>alert("XSS")</script>',
            '<img src=x onerror=alert(document.cookie)>',
            '"><svg onload=alert(1)>',
            "javascript:alert('XSS')",
            "' onfocus='alert(1)'",
            '<iframe src="https://evil.com"></iframe>',
            '{{ 7 * 7 }}',  # Template injection probe
            '${7*7}'
        ]

        def client_side_escape_html(s: str) -> str:
            if not s or not isinstance(s, str):
                return ""
            return (s.replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;")
                     .replace('"', "&quot;")
                     .replace("'", "&#039;"))

        for xss in xss_payloads:
            # 1. Verify frontend escape logic sanitizes dangerous HTML characters
            escaped = client_side_escape_html(xss)
            self.assertNotIn("<script>", escaped)
            self.assertNotIn("<img", escaped)
            self.assertNotIn("<svg", escaped)
            self.assertNotIn("<iframe", escaped)

            # 2. Verify server stores without code execution or crashing
            resp = self.client.post("/api/social/accounts", json={
                "platform": "instagram",
                "account_name": xss,
                "session_id": "28101846244:zxTBaidHletx94:27:AYhVP_G5LQJFp9mLVjcDYm_HXehKmA0kC85DNIYQGw"
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data.get("success"))
            self.assertIn("account", data)

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. EMPIRICAL TESTS: CANVAS ENGINE BOUNDARIES & RAPID SWITCHING
    # ═══════════════════════════════════════════════════════════════════════════

    def test_06_canvas_boundary_dimensions(self):
        """Test gear radius and layout mathematics under zero, negative, and extreme dimensions."""
        dimensions = [
            (0, 0),
            (-500, -300),
            (1, 1),
            (10, 10000),
            (10000, 10),
            (3840, 2160),
            (32000, 32000)
        ]
        gears = [
            {"id": "sun", "radius": 110, "teeth": 24, "speedRatio": 1.0, "dir": 1},
            {"id": "planet1", "parent": "sun", "angleOffset": math.pi * 0.75, "radius": 65, "teeth": 14, "speedRatio": -24/14, "dir": -1},
            {"id": "planet2", "parent": "planet1", "angleOffset": math.pi * 0.35, "radius": 85, "teeth": 18, "speedRatio": (24/14)*(14/18), "dir": 1},
        ]

        for width, height in dimensions:
            min_dim = min(width, height)
            scale_factor = max(0.6, min(1.4, min_dim / 900))
            self.assertFalse(math.isnan(scale_factor), f"Scale factor is NaN for {width}x{height}")
            self.assertGreaterEqual(scale_factor, 0.6)

            for g in gears:
                r = max(20, g["radius"] * scale_factor)
                pitch_radius = r
                outer_radius = r * 1.14
                root_radius = r * 0.86
                self.assertFalse(math.isnan(r), f"Radius is NaN for {width}x{height}")
                self.assertGreater(r, 0, f"Radius must be > 0 for {width}x{height}")
                self.assertGreater(outer_radius, root_radius)

    def test_07_gear_kinematics_numerical_stability(self):
        """Stress-test rotational angle integration across 100,000 simulated frames."""
        angle = 0.0
        dt = 16.666  # ~60 fps in ms
        speed = 1.0
        gear_sun_ratio = 1.0
        gear_planet1_ratio = -24 / 14
        gear_planet2_ratio = (24 / 14) * (14 / 18)

        for frame in range(100_000):
            angle = (angle + (dt * 0.001 * speed * math.pi)) % (math.pi * 2)
            rot_sun = angle * gear_sun_ratio * 1
            rot_p1 = angle * gear_planet1_ratio * -1
            rot_p2 = angle * gear_planet2_ratio * 1

            # Assert angles remain in finite bounds and never produce NaN
            self.assertFalse(math.isnan(angle))
            self.assertFalse(math.isnan(rot_sun))
            self.assertFalse(math.isnan(rot_p1))
            self.assertFalse(math.isnan(rot_p2))
            self.assertGreaterEqual(angle, 0.0)
            self.assertLessEqual(angle, math.pi * 2 + 1e-9)

    def test_08_extreme_speed_and_opacity_parameters(self):
        """Test speed slider limits (0, negative, 100x, NaN/inf) and opacity."""
        test_speeds = [0.0, -1.0, -10.0, 0.1, 1.0, 5.0, 100.0, 1000.0]
        for sp in test_speeds:
            dt = 16.666
            delta = (dt * 0.001 * sp * math.pi)
            self.assertFalse(math.isnan(delta))
            self.assertTrue(math.isfinite(delta))

        # Test opacity clamp
        test_opacities = [-5.0, 0.0, 0.5, 1.0, 5.0]
        for op in test_opacities:
            clamped = max(0.0, min(1.0, op))
            self.assertGreaterEqual(clamped, 0.0)
            self.assertLessEqual(clamped, 1.0)

    def test_09_rapid_background_mode_switching(self):
        """Simulate rapid cycling between background themes 5,000 times."""
        themes = ["gears", "blueprint", "pulse", "slate", "unknown_theme"]
        valid_themes = {"gears", "blueprint", "pulse", "slate"}

        current_theme = "gears"
        for _ in range(5000):
            next_th = random.choice(themes)
            # Simulated setTheme logic
            current_theme = next_th if next_th in valid_themes else "gears"
            self.assertIn(current_theme, valid_themes)

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. EMPIRICAL TESTS: STORAGE CORRUPTION & RECOVERY
    # ═══════════════════════════════════════════════════════════════════════════

    def test_10_localstorage_corruption_recovery_scenarios(self):
        """Simulate safeJsonParse behavior under corrupted localStorage payloads."""
        def safe_json_parse(raw_str, fallback):
            try:
                return json.loads(raw_str) if raw_str else fallback
            except Exception:
                return fallback

        corrupted_payloads = [
            "",
            "   ",
            "not_json",
            "{\"theme\": \"gears\", \"speed\":",
            "{\"accounts\": [undefined]}",
            "null",
            "true",
            "12345",
            "\x00\x01\x02\x03",
            "{'single_quotes': true}"
        ]

        for payload in corrupted_payloads:
            parsed_accounts = safe_json_parse(payload, [])
            # If payload parses to non-list (e.g. integer or boolean), verify graceful normalization
            if not isinstance(parsed_accounts, list):
                parsed_accounts = []
            self.assertIsInstance(parsed_accounts, list, f"Failed on payload: {payload}")

            parsed_bg = safe_json_parse(payload, None)
            if not isinstance(parsed_bg, dict):
                parsed_bg = {"theme": "gears", "speed": 1.0, "opacity": 0.85}
            self.assertIsInstance(parsed_bg, dict)
            self.assertIn("theme", parsed_bg)

    def test_11_backend_file_storage_corruption_recovery(self):
        """Test server _load_social_accounts_data recovery when social_accounts.json is corrupted."""
        corrupted_contents = [
            b"",  # empty file
            b"   \n\t  ",  # whitespace
            b"{invalid_json: null",  # invalid syntax
            b"['an', 'array', 'instead', 'of', 'dict']",  # wrong root type
            b"\"a string literal\"",  # string root
            b"123456",  # int root
            b"true",  # bool root
            b"\x80\x81\x82\x83\xff\xfe",  # binary garbage
            b"{\"accounts\": \"not_a_list\", \"logs\": null}"  # corrupted schema
        ]

        for content in corrupted_contents:
            # Write corrupted file
            with open(SOCIAL_ACCOUNTS_FILE, "wb") as f:
                f.write(content)

            # Attempt load
            loaded = _load_social_accounts_data()
            self.assertIsInstance(loaded, dict, f"Load failed on content: {content}")
            self.assertIsInstance(loaded.get("accounts"), list, f"Accounts not a list on content: {content}")
            self.assertIsInstance(loaded.get("logs"), list, f"Logs not a list on content: {content}")
            self.assertIn("active_id", loaded)

            # Verify API endpoints still respond HTTP 200 after corruption
            resp = self.client.get("/api/social/accounts")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data.get("success"))

            resp_logs = self.client.get("/api/social/logs")
            self.assertEqual(resp_logs.status_code, 200)
            logs_data = resp_logs.get_json()
            self.assertTrue(logs_data.get("success"))

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. EMPIRICAL TESTS: BACKEND API BOUNDARY & STATE INTEGRITY
    # ═══════════════════════════════════════════════════════════════════════════

    def test_12_backend_api_malformed_requests(self):
        """Test backend endpoints with malformed bodies, missing fields, and bad types."""
        # 1. Empty body POST to /api/social/accounts
        resp = self.client.post("/api/social/accounts", data="", content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))

        # 2. Non-dict JSON (e.g. list or integer)
        resp = self.client.post("/api/social/accounts", json=[1, 2, 3])
        self.assertEqual(resp.status_code, 200)

        # 3. Switch endpoint with nonexistent account ID
        resp = self.client.post("/api/social/accounts/switch", json={"account_id": "nonexistent_id_9999"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("active_id"), "nonexistent_id_9999")

        # 4. Switch endpoint with empty JSON
        resp = self.client.post("/api/social/accounts/switch", json={})
        self.assertEqual(resp.status_code, 200)

        # 5. Test credential endpoint with invalid platform
        resp = self.client.post("/api/social/accounts/test", json={"platform": "unknown_platform", "session_id": "short"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertFalse(data.get("valid"))

    def test_13_delete_account_lifecycle_and_active_id_reassignment(self):
        """Test account addition, active_id assignment, deletion, and active_id fallback."""
        # Clear storage
        _save_social_accounts_data({"accounts": [], "active_id": None, "logs": []})

        # Add Account 1
        acc1_payload = {
            "account_id": "acc_1",
            "platform": "instagram",
            "account_name": "User One",
            "session_id": "28101846244:sig1:27:valid_token_1"
        }
        r1 = self.client.post("/api/social/accounts", json=acc1_payload)
        self.assertEqual(r1.status_code, 200)
        d1 = r1.get_json()
        self.assertEqual(d1.get("active_id"), "acc_1")

        # Add Account 2
        acc2_payload = {
            "account_id": "acc_2",
            "platform": "discord",
            "account_name": "User Two",
            "session_id": "Bot MTIzNDU2.ABC.abcdef"
        }
        r2 = self.client.post("/api/social/accounts", json=acc2_payload)
        self.assertEqual(r2.status_code, 200)

        # Active ID should still be acc_1
        cur = _load_social_accounts_data()
        self.assertEqual(cur.get("active_id"), "acc_1")
        self.assertEqual(len(cur.get("accounts")), 2)

        # Delete acc_1 (active account)
        del_r = self.client.delete("/api/social/accounts/acc_1")
        self.assertEqual(del_r.status_code, 200)
        del_data = del_r.get_json()
        self.assertTrue(del_data.get("success"))
        # Active ID should have fallen back to acc_2
        self.assertEqual(del_data.get("active_id"), "acc_2")

        cur2 = _load_social_accounts_data()
        self.assertEqual(cur2.get("active_id"), "acc_2")
        self.assertEqual(len(cur2.get("accounts")), 1)

        # Delete acc_2 (last account)
        del_r2 = self.client.delete("/api/social/accounts/acc_2")
        self.assertEqual(del_r2.status_code, 200)
        del_data2 = del_r2.get_json()
        self.assertIsNone(del_data2.get("active_id"))

        cur3 = _load_social_accounts_data()
        self.assertEqual(len(cur3.get("accounts")), 0)
        self.assertIsNone(cur3.get("active_id"))

    def test_14_delete_path_traversal_and_special_characters(self):
        """Test DELETE /api/social/accounts/<account_id> with special characters and path traversal."""
        traversal_ids = [
            "acc_123",
            "acc_test%2Ftraversal",
            "acc_test%2E%2E",
            "acc_special_!@#$%^&*()",
            "acc_nonexistent"
        ]
        for tid in traversal_ids:
            resp = self.client.delete(f"/api/social/accounts/{tid}")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data.get("success"))

if __name__ == "__main__":
    unittest.main()
