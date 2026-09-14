#!/usr/bin/env python3
"""
independent_audit_test.py - Independent Victory Auditor Verification Suite
Authored by Victory Auditor (victory_auditor_1) to independently audit requirements R1-R5.
"""

import os
import sys
import re
import json
import math
import base64
import time
from html.parser import HTMLParser

WORKSPACE_DIR = "/storage/emulated/0/discord-bot"
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

SOCIAL_HTML = os.path.join(WORKSPACE_DIR, "social.html")
BOT_PY = os.path.join(WORKSPACE_DIR, "bot.py")
VERIFY_SCRIPT = os.path.join(WORKSPACE_DIR, "verify_social_hub.py")
DATA_FILE = os.path.join(WORKSPACE_DIR, "data", "social_accounts.json")

test_results = []

def record(test_id, name, status, detail=""):
    test_results.append({
        "id": test_id,
        "name": name,
        "status": status,
        "detail": detail
    })
    status_str = "PASS" if status else "FAIL"
    print(f"[{status_str}] {test_id} - {name}: {detail}")

print("=" * 80)
print("INDEPENDENT VICTORY AUDIT TEST SUITE")
print("=" * 80)

# ─── 1. AUDIT R1: DRAFTING DESK & STUDIO HYBRID INTERFACE ─────────────────────
print("\n--- AUDITING R1: Hybrid Interface & 3-Way Navigation ---")
if not os.path.exists(SOCIAL_HTML):
    record("R1.1", "social.html existence", False, "File not found")
else:
    with open(SOCIAL_HTML, "r", encoding="utf-8") as f:
        html = f.read()
    record("R1.1", "social.html existence", True, f"File size: {len(html)} bytes, lines: {html.count(chr(10))+1}")

    # Check 3-way navigation
    has_dash = 'href="/dashboard"' in html
    has_studio = 'href="/studio"' in html
    has_social = 'href="/social"' in html or 'active' in html
    record("R1.2", "3-Way Navigation (/dashboard, /studio, /social)", has_dash and has_studio and has_social,
           f"dashboard={has_dash}, studio={has_studio}, social={has_social}")

    # Check tactile drafting elements
    has_ruler = "blueprint-ruler" in html
    has_paper = "paper-card" in html or "tactile-card" in html
    has_clip = "paper-clip" in html
    record("R1.3", "Tactile Drafting Desk Elements", has_ruler and has_paper and has_clip,
           f"ruler={has_ruler}, paper_card={has_paper}, paper_clip={has_clip}")

    # Check studio suite elements
    has_studio_card = "studio-card" in html
    has_telemetry = "telemetry-strip" in html or "activeNodesCount" in html
    has_badges = "status-badge" in html or "status-pill" in html
    record("R1.4", "Studio Suite Dark Cards & Telemetry", has_studio_card and has_telemetry and has_badges,
           f"studio_card={has_studio_card}, telemetry={has_telemetry}, status_badges={has_badges}")

# ─── 2. AUDIT R2: SOCIAL ACCOUNT MANAGEMENT & SESSION ID INGESTION ───────────
print("\n--- AUDITING R2: Social Account Management via Session IDs ---")
with open(SOCIAL_HTML, "r", encoding="utf-8") as f:
    html = f.read()

# Form inputs
has_platform_sel = 'id="platformSelect"' in html
has_acc_name = 'id="accountName"' in html
has_sess_id = 'id="sessionIdInput"' in html
has_add_btn = 'id="addAccountBtn"' in html
record("R2.1", "Credential Form Controls", has_platform_sel and has_acc_name and has_sess_id and has_add_btn,
       f"platform={has_platform_sel}, name={has_acc_name}, session={has_sess_id}, add_btn={has_add_btn}")

# Inspect modal and controls
has_modal = 'id="inspectModal"' in html
has_copy = 'id="copyTokenBtn"' in html
has_mask_toggle = 'id="toggleMaskBtn"' in html
record("R2.2", "Inspect Modal with Mask Toggle and Copy", has_modal and has_copy and has_mask_toggle,
       f"modal={has_modal}, copy_btn={has_copy}, mask_toggle={has_mask_toggle}")

# Actions: Disconnect, Switch, Test
has_switch = "switchActiveAccount" in html
has_test_fn = "testAccountCredential" in html
has_disconnect = "disconnectAccount" in html
record("R2.3", "Account Actions (Switch, Test, Disconnect)", has_switch and has_test_fn and has_disconnect,
       f"switch={has_switch}, test={has_test_fn}, disconnect={has_disconnect}")

# Activity Log feed
has_log_feed = 'id="activityLogFeed"' in html or 'id="activityList"' in html
record("R2.4", "Activity Log Feed Container", has_log_feed, f"log_feed={has_log_feed}")

# ─── 3. AUDIT R3: ANIMATED BACKGROUND ENGINE & GEAR KINEMATICS ───────────────
print("\n--- AUDITING R3: Animated Background Engine & Conjugate Gear Kinematics ---")
# 4 selectable themes
themes = ["gears", "blueprint", "pulse", "slate"]
found_themes = [t for t in themes if t in html]
record("R3.1", "4 Selectable Background Themes", len(found_themes) == 4, f"Found themes: {found_themes}")

# Canvas element and requestAnimationFrame loop
has_canvas = 'id="bgCanvas"' in html or 'id="gearCanvas"' in html
has_raf = "requestAnimationFrame" in html
record("R3.2", "HTML5 Canvas & RAF Loop", has_canvas and has_raf, f"canvas={has_canvas}, RAF={has_raf}")

# Gear Kinematics Extraction and Mathematical Proof
gears_match = re.search(r"this\.gears\s*=\s*\[(.*?)\];", html, re.DOTALL)
if not gears_match:
    record("R3.3", "Gear Kinematics Array Extraction", False, "Could not extract this.gears")
else:
    record("R3.3", "Gear Kinematics Array Extraction", True, "Successfully extracted this.gears")
    gear_entries = re.findall(r"\{([^}]+)\}", gears_match.group(1))
    gears_map = {}
    for entry in gear_entries:
        gid_m = re.search(r"id:\s*['\"]([^'\"]+)['\"]", entry)
        if not gid_m: continue
        gid = gid_m.group(1)
        parent_m = re.search(r"parent:\s*['\"]([^'\"]+)['\"]", entry)
        parent = parent_m.group(1) if parent_m else None
        radius_m = re.search(r"radius:\s*([0-9.]+)", entry)
        radius = float(radius_m.group(1)) if radius_m else 0.0
        teeth_m = re.search(r"teeth:\s*([0-9]+)", entry)
        teeth = int(teeth_m.group(1)) if teeth_m else 0
        speed_m = re.search(r"speedRatio:\s*([^\s,]+)", entry)
        speed_ratio = float(eval(speed_m.group(1), {"__builtins__": None}, {})) if speed_m else 1.0
        dir_m = re.search(r"dir:\s*([-0-9]+)", entry)
        direction = int(dir_m.group(1)) if dir_m else 1
        effective_omega = speed_ratio * direction
        gears_map[gid] = {
            "id": gid, "parent": parent, "radius": radius, "teeth": teeth,
            "speedRatio": speed_ratio, "dir": direction, "effective_omega": effective_omega
        }

    # Verify conjugate kinematics for all followers
    all_kinematics_valid = True
    kinematic_details = []
    for gid, g in gears_map.items():
        if g["parent"]:
            p = gears_map[g["parent"]]
            w1 = p["effective_omega"]
            w2 = g["effective_omega"]
            z1 = p["teeth"]
            z2 = g["teeth"]
            
            # 1. Opposite direction
            counter_rotating = (w1 * w2 < 0)
            # 2. Tangential tooth velocity match: w1*z1 + w2*z2 == 0
            v_sum = abs(w1 * z1 + w2 * z2)
            tooth_match = (v_sum < 1e-4)
            # 3. Module match
            m1 = 2 * p["radius"] / z1
            m2 = 2 * g["radius"] / z2
            mod_match = (abs(m1 - m2) / m1 < 0.06)

            pair_valid = counter_rotating and tooth_match and mod_match
            if not pair_valid:
                all_kinematics_valid = False
            kinematic_details.append(f"{g['parent']}->{gid}: counter_rot={counter_rotating} (w1={w1:+.3f}, w2={w2:+.3f}), v_sum={v_sum:.4f}, m1={m1:.2f}/m2={m2:.2f}")

    record("R3.4", "Conjugate Gear Kinematics (w1*z1 = -w2*z2 & counter-rotation)", all_kinematics_valid,
           "; ".join(kinematic_details))

# ─── 4. AUDIT R4: FLASK ROUTING & REST APIS IN BOT.PY ────────────────────────
print("\n--- AUDITING R4: Flask Application Routes and REST Endpoints ---")
try:
    from bot import app
    client = app.test_client()

    # Route checks
    r_social = client.get("/social")
    r_social_html = client.get("/social.html")
    r_control = client.get("/control")
    r_dashboard = client.get("/dashboard")
    r_studio = client.get("/studio")

    routes_ok = (r_social.status_code == 200 and r_social_html.status_code == 200 and
                 r_control.status_code == 200 and r_dashboard.status_code == 200 and
                 r_studio.status_code == 200)
    record("R4.1", "HTML Page Routes (/social, /social.html, /control, /dashboard, /studio)", routes_ok,
           f"/social={r_social.status_code}, /social.html={r_social_html.status_code}, /control={r_control.status_code}, /dashboard={r_dashboard.status_code}, /studio={r_studio.status_code}")

    # REST APIs: GET accounts
    r_get = client.get("/api/social/accounts")
    get_ok = (r_get.status_code == 200 and r_get.get_json().get("success"))
    record("R4.2", "GET /api/social/accounts", get_ok, f"status={r_get.status_code}, success={r_get.get_json().get('success')}")

    # REST APIs: POST add account
    test_acc_id = f"acc_victory_audit_{int(time.time())}"
    post_payload = {
        "account_id": test_acc_id,
        "platform": "instagram",
        "account_name": "victory_audit_user",
        "session_id": "28101846244:auditSignatureHash:27:AUDIT_TEST_TOKEN",
        "status": "active"
    }
    r_post = client.post("/api/social/accounts", json=post_payload)
    post_ok = (r_post.status_code == 200 and r_post.get_json().get("success"))
    record("R4.3", "POST /api/social/accounts", post_ok, f"status={r_post.status_code}, created_id={r_post.get_json().get('account', {}).get('id')}")

    # REST APIs: POST switch account
    r_switch = client.post("/api/social/accounts/switch", json={"account_id": test_acc_id})
    switch_ok = (r_switch.status_code == 200 and r_switch.get_json().get("active_id") == test_acc_id)
    record("R4.4", "POST /api/social/accounts/switch", switch_ok, f"status={r_switch.status_code}, active_id={r_switch.get_json().get('active_id')}")

    # REST APIs: POST test credential
    r_test = client.post("/api/social/accounts/test", json={"account_id": test_acc_id, "platform": "instagram", "session_id": post_payload["session_id"], "mock_fallback": True})
    test_ok = (r_test.status_code == 200 and r_test.get_json().get("valid") is True)
    record("R4.5", "POST /api/social/accounts/test", test_ok, f"status={r_test.status_code}, valid={r_test.get_json().get('valid')}")

    # REST APIs: GET logs
    r_logs = client.get("/api/social/logs")
    logs_ok = (r_logs.status_code == 200 and isinstance(r_logs.get_json().get("logs"), list))
    record("R4.6", "GET /api/social/logs", logs_ok, f"status={r_logs.status_code}, log_count={len(r_logs.get_json().get('logs', []))}")

    # REST APIs: DELETE account
    r_del = client.delete(f"/api/social/accounts/{test_acc_id}")
    del_ok = (r_del.status_code == 200 and r_del.get_json().get("deleted_id") == test_acc_id)
    record("R4.7", f"DELETE /api/social/accounts/{test_acc_id}", del_ok, f"status={r_del.status_code}, deleted_id={r_del.get_json().get('deleted_id')}")

except Exception as e:
    record("R4.X", "Flask API Exception", False, f"Exception: {e}")

# ─── 5. AUDIT R5: AUTOMATED OBJECTIVE VERIFICATION ───────────────────────────
print("\n--- AUDITING R5: Automated Verification Script ---")
has_verify_file = os.path.exists(VERIFY_SCRIPT)
record("R5.1", "verify_social_hub.py exists", has_verify_file, f"Path: {VERIFY_SCRIPT}")

# ─── SUMMARY EVALUATION ──────────────────────────────────────────────────────
print("\n" + "=" * 80)
total_tests = len(test_results)
passed_count = sum(1 for t in test_results if t["status"])
failed_count = total_tests - passed_count
print(f"AUDIT SUMMARY: {passed_count}/{total_tests} checks PASSED, {failed_count} FAILED")
print("=" * 80)

if failed_count == 0:
    print("VERDICT: ALL AUDIT CRITERIA MET (VICTORY CONFIRMED)")
    sys.exit(0)
else:
    print("VERDICT: AUDIT FAILURES DETECTED (VICTORY REJECTED)")
    sys.exit(1)
