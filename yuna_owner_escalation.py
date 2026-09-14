#!/usr/bin/env python3
"""
Yuna Owner DM Escalation & Missing Input Service
------------------------------------------------
When Yuna needs credentials, API keys, or manual actions to enable a feature
(e.g., creating an Instagram account, entering a 2FA code or password):
1. Informs the user in the channel: "w8 i need [this] ill ask my owner to help me real quick"
2. DMs the bot owner with the exact issue and instructions
3. Listens for the owner's response in DM to resume and finish setup automatically
"""

import os
import sys
import json
import time
import re
from typing import Optional, List, Dict
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
PENDING_FILE = BASE_DIR / "data" / "pending_escalations.json"

def get_owner_ids() -> List[int]:
    """Reads all owner IDs from .env and config.json, prioritizing the companion account."""
    from dotenv import load_dotenv
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)

    ids = []
    # Primary companion user account
    user_id_str = os.getenv("DISCORD_USER_ID", "824888375395876884").strip()
    if user_id_str and user_id_str.isdigit():
        ids.append(int(user_id_str))

    # Read all OWNER_ID occurrences in .env
    if env_file.exists():
        try:
            for line in env_file.read_text().splitlines():
                if line.startswith("OWNER_ID="):
                    val = line.split("=", 1)[1].strip()
                    if val.isdigit() and int(val) not in ids:
                        ids.append(int(val))
        except Exception:
            pass

    # Read from config.json
    cfg_file = BASE_DIR / "config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r") as f:
                c = json.load(f)
                c_owner = c.get("owner_id")
                if c_owner and str(c_owner).isdigit() and int(c_owner) not in ids:
                    ids.append(int(c_owner))
        except Exception:
            pass

    if not ids:
        ids = [824888375395876884]
    return ids

def load_pending_escalations() -> List[Dict]:
    if not PENDING_FILE.exists():
        return []
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def save_pending_escalations(entries: List[Dict]):
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        temp = PENDING_FILE.parent / f"escalations.tmp.{int(time.time()*1000)}"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
        os.replace(temp, PENDING_FILE)
    except Exception as e:
        print(f"[ESCALATION ERROR] Failed to save pending escalations: {e}", file=sys.stderr)

async def dispatch_owner_escalation(
    client,
    feature_name: str,
    needed_input: str,
    requester_name: str,
    channel_name: str,
    channel_id: int,
    requester_id: int,
    additional_notes: str = ""
) -> bool:
    """
    Sends a direct message to the owner asking for missing credentials or action.
    """
    owner_ids = get_owner_ids()
    sent_any = False

    escalation_entry = {
        "id": f"esc_{int(time.time()*1000)}",
        "timestamp": time.time(),
        "feature_name": feature_name,
        "needed_input": needed_input,
        "requester_name": requester_name,
        "channel_name": channel_name,
        "channel_id": channel_id,
        "requester_id": requester_id,
        "status": "pending",
        "notes": additional_notes
    }

    message_text = (
        f"🚨 **Yuna Action Required — Missing Input Alert** 🚨\n\n"
        f"Hey owner! @{requester_name} in **#{channel_name}** asked for **{feature_name}**, "
        f"but I'm missing something that requires your input:\n\n"
        f"👉 **Needed:** `{needed_input}`\n"
        f"{f'ℹ️ *Notes:* {additional_notes}' if additional_notes else ''}\n\n"
        f"💡 *You can reply directly to this DM with the needed info or update `.env` / `config.json`! "
        f"I told @{requester_name} to hold on while I asked you.*"
    )

    for oid in owner_ids:
        try:
            owner_user = client.get_user(oid)
            if not owner_user:
                try:
                    owner_user = await client.fetch_user(oid)
                except Exception:
                    owner_user = None

            if owner_user:
                dm_channel = owner_user.dm_channel or await owner_user.create_dm()
                await dm_channel.send(message_text)
                print(f"[ESCALATION] Dispatched DM to owner ID {oid} for '{feature_name}'")
                sent_any = True
        except Exception as e:
            print(f"[ESCALATION ERROR] Failed to send DM to owner {oid}: {e}", file=sys.stderr)

    if sent_any:
        escalations = load_pending_escalations()
        escalations.append(escalation_entry)
        save_pending_escalations(escalations)

    return sent_any

async def check_and_handle_owner_reply(message, client) -> Optional[Dict]:
    """
    If the incoming message is a DM from an owner, checks if there is a pending escalation
    to resolve. Returns the resolved escalation entry if found.
    """
    if message.guild is not None:
        return None

    owner_ids = get_owner_ids()
    if message.author.id not in owner_ids:
        return None

    escalations = load_pending_escalations()
    pending = [e for e in escalations if e.get("status") == "pending"]
    if not pending:
        return None

    # Resolve the most recent pending escalation
    target_esc = pending[-1]
    target_esc["status"] = "resolved"
    target_esc["resolved_at"] = time.time()
    target_esc["owner_response"] = message.content

    save_pending_escalations(escalations)

    # Acknowledge to owner
    await message.reply(
        f"✨ **Got it!** Received your input for **{target_esc.get('feature_name')}**. "
        f"Applying changes and updating @{target_esc.get('requester_name')} right now~!"
    )

    return target_esc

if __name__ == "__main__":
    print("Detected owner IDs:", get_owner_ids())
    print("Active pending escalations:", len([e for e in load_pending_escalations() if e.get("status") == "pending"]))
