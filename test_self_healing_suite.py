#!/usr/bin/env python3
"""
Comprehensive Test Suite for Yuna Self-Healing, AGY Bridge & Backup Engine
"""

import os
import sys
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

def test_all():
    print("==================================================")
    print("  RUNNING YUNA SELF-HEALING & AGY SUITE TESTS")
    print("==================================================")

    # 1. Test Backup Guard
    print("\n[TEST 1] Testing Backup Guard...")
    import yuna_backup_guard as guard
    test_f = BASE_DIR / ".bak" / "verification_test.txt"
    test_f.write_text("initial state v1")
    
    bk = guard.backup_file(str(test_f), "Self-healing verification test")
    assert bk and os.path.exists(bk), "Failed to generate backup"
    
    test_f.write_text("corrupted state v2")
    assert test_f.read_text() == "corrupted state v2"
    
    assert guard.rollback(str(test_f)), "Rollback execution returned False"
    assert test_f.read_text() == "initial state v1", "Rollback did not restore original content"
    test_f.unlink(missing_ok=True)
    print("  -> Backup Guard & Rollback: PASSED ✅")

    # 2. Test Feature Intent Classifier & Comprehension
    print("\n[TEST 2] Testing Feature Gap Intent Classifier & Comprehension...")
    import yuna_feature_evaluator as evaluator
    
    # Test Instagram
    res_insta = evaluator.check_feature_intent("hey yuna do you have insta?")
    assert res_insta and res_insta["type"] == "instagram", f"Failed to detect insta intent: {res_insta}"
    
    # Test Instagram for account (ensure pip_package is None, not 'instagram for account')
    res_insta_acc = evaluator.check_feature_intent("install instagram for account")
    assert res_insta_acc and res_insta_acc["intent_type"] == "instagram", f"Failed to comprehend insta account: {res_insta_acc}"
    assert res_insta_acc.get("pip_package") is None, f"Incorrectly assigned pip_package: {res_insta_acc.get('pip_package')}"
    assert res_insta_acc.get("needs_pip") is False, "Incorrectly set needs_pip to True"

    # Test Command creation (ensure not treated as pip package)
    res_cmd = evaluator.check_feature_intent("install a /command called test which triggers response hihihi")
    assert res_cmd and res_cmd["intent_type"] == "bot_command", f"Failed to comprehend command creation: {res_cmd}"
    assert res_cmd.get("command_name") == "test", f"Failed to extract command name: {res_cmd}"
    assert res_cmd.get("pip_package") is None, f"Command creation must have pip_package=None: {res_cmd}"
    assert res_cmd.get("needs_pip") is False, "Command creation must have needs_pip=False"
    assert res_cmd.get("needs_code_edit") is True, "Command creation requires code edit"

    # Test Pip package sanitizer anti-bruteforce
    assert evaluator.sanitize_pip_package("a /command called test") is None, "Failed to reject phrase"
    assert evaluator.sanitize_pip_package("instagram for account") is None, "Failed to reject phrase"
    assert evaluator.sanitize_pip_package("sympy") == "sympy", "Failed to accept valid package"
    assert evaluator.sanitize_pip_package("numpy") == "numpy", "Failed to accept valid package"

    # Test Twitter
    res_tw = evaluator.check_feature_intent("can you post on twitter?")
    assert res_tw and res_tw["type"] == "twitter", f"Failed to detect twitter intent: {res_tw}"
    
    # Test Package install
    res_pkg = evaluator.check_feature_intent("download sympy")
    assert res_pkg and res_pkg["type"] == "package_or_tool", f"Failed to detect package intent: {res_pkg}"
    assert res_pkg.get("pip_package") == "sympy", f"Failed to extract clean package: {res_pkg}"
    
    # Test Normal conversation
    res_none = evaluator.check_feature_intent("good morning yuna, tell me a joke")
    assert res_none is None, f"Incorrectly triggered intent for general conversation: {res_none}"
    
    # Test external installation question (PC/laptop)
    res_ext = evaluator.check_feature_intent("how do I install GTA 5 on my PC?")
    assert res_ext is None, f"Incorrectly intercepted PC software question: {res_ext}"
    print("  -> Feature Intent Classifier & Comprehension: PASSED ✅")

    # 3. Test Owner Escalation Engine
    print("\n[TEST 3] Testing Owner Escalation...")
    import yuna_owner_escalation as escalation
    owner_ids = escalation.get_owner_ids()
    assert 824888375395876884 in owner_ids, f"Companion account ID not found in owner IDs: {owner_ids}"
    print(f"  -> Owner IDs identified: {owner_ids}: PASSED ✅")

    # 4. Test AGY Bridge Binary Detection & Syntax Verification
    print("\n[TEST 4] Testing AGY Bridge...")
    import yuna_agy_bridge as bridge
    agy_path = bridge.find_agy_binary()
    assert agy_path, "AGY binary could not be found"
    print(f"  -> Detected AGY binary: {agy_path}")

    # Syntax verification of critical bot files
    crit_files = [
        str(BASE_DIR / "bot.py"),
        str(BASE_DIR / "user_worker.py"),
        str(BASE_DIR / "yuna_backup_guard.py"),
        str(BASE_DIR / "yuna_agy_bridge.py"),
        str(BASE_DIR / "yuna_owner_escalation.py"),
        str(BASE_DIR / "yuna_feature_evaluator.py")
    ]
    ok, err = bridge.verify_python_syntax(crit_files)
    assert ok, f"Syntax verification failed: {err}"
    print("  -> Critical files syntax verification: PASSED ✅")

    print("\n==================================================")
    print("  ALL 4 CORE SUITE TESTS COMPLETED SUCCESSFULLY ✅")
    print("==================================================")

if __name__ == "__main__":
    test_all()
