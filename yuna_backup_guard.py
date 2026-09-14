#!/usr/bin/env python3
"""
Yuna Safe File Backup Guard
---------------------------
Ensures every file is backed up before modification, tracks a manifest with checksums,
and provides atomic rollback capability so Yuna / AGY can never break the codebase permanently.
"""

import os
import sys
import json
import time
import shutil
import hashlib
from typing import Optional, List, Dict
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
BACKUP_DIR = BASE_DIR / ".bak"
MANIFEST_FILE = BACKUP_DIR / "manifest.json"

def _ensure_dirs():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def _get_file_hash(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def _load_manifest() -> List[Dict]:
    _ensure_dirs()
    if not MANIFEST_FILE.exists():
        return []
    try:
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def _save_manifest(entries: List[Dict]):
    _ensure_dirs()
    try:
        temp_file = BACKUP_DIR / f"manifest.tmp.{int(time.time()*1000)}"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
        os.replace(temp_file, MANIFEST_FILE)
    except Exception as e:
        print(f"[BACKUP GUARD WARNING] Failed to save manifest: {e}", file=sys.stderr)

def backup_file(filepath: str, reason: str = "") -> Optional[str]:
    """
    Creates a timestamped snapshot of filepath before any modification.
    Returns the absolute path to the backup file, or None if file doesn't exist.
    """
    _ensure_dirs()
    p = Path(filepath)
    if not p.is_absolute():
        p = BASE_DIR / p
    p = p.resolve()

    if not p.exists() or not p.is_file():
        # Nothing to back up for non-existent file
        return None

    try:
        file_hash = _get_file_hash(str(p))
        timestamp = int(time.time())
        date_str = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"{p.name}.{date_str}.{file_hash[:8]}.bak"
        backup_path = BACKUP_DIR / backup_name

        shutil.copy2(str(p), str(backup_path))

        entry = {
            "source_path": str(p),
            "filename": p.name,
            "backup_path": str(backup_path),
            "backup_filename": backup_name,
            "timestamp": timestamp,
            "date": date_str,
            "sha256": file_hash,
            "size_bytes": p.stat().st_size,
            "reason": reason or "Pre-modification snapshot"
        }

        manifest = _load_manifest()
        manifest.append(entry)
        _save_manifest(manifest)

        print(f"[BACKUP GUARD] Snapshotted '{p.name}' -> '{backup_name}' ({reason or 'pre-edit'})")
        return str(backup_path)
    except Exception as e:
        print(f"[BACKUP GUARD ERROR] Failed to backup '{filepath}': {e}", file=sys.stderr)
        return None

def rollback(filepath: str, backup_path: Optional[str] = None) -> bool:
    """
    Restores filepath to its last backup, or to a specific backup_path.
    Returns True on successful rollback.
    """
    p = Path(filepath)
    if not p.is_absolute():
        p = BASE_DIR / p
    p = p.resolve()

    manifest = _load_manifest()

    if backup_path:
        target_backup = Path(backup_path)
    else:
        # Find latest backup for this file
        file_backups = [e for e in manifest if Path(e.get("source_path", "")).resolve() == p]
        if not file_backups:
            print(f"[BACKUP GUARD] No recorded backups found for '{p}'", file=sys.stderr)
            return False
        # Sort by timestamp desc
        file_backups.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        target_backup = Path(file_backups[0]["backup_path"])

    if not target_backup.exists():
        print(f"[BACKUP GUARD ERROR] Target backup '{target_backup}' does not exist", file=sys.stderr)
        return False

    try:
        # Atomic replace
        temp_restore = p.parent / f"{p.name}.restore.tmp"
        shutil.copy2(str(target_backup), str(temp_restore))
        os.replace(str(temp_restore), str(p))
        print(f"[BACKUP GUARD] Successfully rolled back '{p.name}' from '{target_backup.name}'")
        return True
    except Exception as e:
        print(f"[BACKUP GUARD ERROR] Failed to rollback '{filepath}': {e}", file=sys.stderr)
        return False

def list_backups(filepath: Optional[str] = None) -> List[Dict]:
    """Returns recorded backups, optionally filtered by filepath."""
    manifest = _load_manifest()
    if not filepath:
        return manifest
    target_p = Path(filepath).resolve()
    return [e for e in manifest if Path(e.get("source_path", "")).resolve() == target_p]

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_file = BASE_DIR / ".bak" / "test_dummy.txt"
        test_file.write_text("dummy version 1")
        b = backup_file(str(test_file), "Initial test version")
        assert b and os.path.exists(b), "Backup file was not created"
        test_file.write_text("corrupted version 2")
        assert rollback(str(test_file)), "Rollback failed"
        assert test_file.read_text() == "dummy version 1", "Content does not match original"
        test_file.unlink(missing_ok=True)
        print("✅ yuna_backup_guard self-test passed successfully!")
    elif len(sys.argv) > 2 and sys.argv[1] == "backup":
        backup_file(sys.argv[2], "Manual CLI backup")
    elif len(sys.argv) > 2 and sys.argv[1] == "rollback":
        rollback(sys.argv[2])
    else:
        print("Usage: python yuna_backup_guard.py [test|backup <file>|rollback <file>]")
