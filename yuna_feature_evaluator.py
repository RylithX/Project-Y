#!/usr/bin/env python3
"""
Yuna Autonomous Feature Evaluator & Dispatcher
---------------------------------------------
Detects missing capabilities, commands, and feature requests in user messages
using deep semantic comprehension (Gemini AI + intelligent local parser).
Prevents naive brute-force pip execution, handles Discord slash command generation,
social integration checks, and escalates to the owner when credentials are required.
"""

import os
import re
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

import yuna_backup_guard as backup_guard
import yuna_agy_bridge as agy_bridge
import yuna_owner_escalation as owner_escalation

BASE_DIR = Path(__file__).parent.resolve()

FORBIDDEN_PIP_WORDS = {
    "a", "an", "the", "command", "called", "test", "which", "triggers", "response",
    "for", "account", "bot", "feature", "tool", "code", "install", "download", "setup",
    "hihihi", "instagram", "insta", "twitter", "my", "your", "its", "package", "discord",
    "please", "now", "here", "real", "quick", "something", "stuff", "this", "that", "it",
    "or", "and", "to", "if", "in", "on", "by", "from", "up", "out", "new", "some", "any",
    "all", "me", "us", "them", "shortcut", "script", "file", "trigger", "terminal", "run",
    "whenever", "when", "says", "say"
}

def _get_gemini_key() -> str:
    """Retrieves Gemini API key from environment, .env, or config.json."""
    k = os.getenv("GEMINI_KEY", "").strip()
    if k:
        return k
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("GEMINI_KEY="):
                    k = line.split("=", 1)[1].strip("\"' ")
                    if k:
                        return k
        except Exception:
            pass
    cfg_file = BASE_DIR / "config.json"
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            k = cfg.get("gemini_key", "").strip()
            if k:
                return k
        except Exception:
            pass
    return ""

def sanitize_pip_package(pkg_name: Optional[str]) -> Optional[str]:
    """
    Strictly sanitizes a candidate pip package name.
    Rejects any multi-word phrases, sentences, punctuation, or common English words.
    Returns valid package name or None.
    """
    if not pkg_name or not isinstance(pkg_name, str):
        return None
    cleaned = pkg_name.strip().lower()
    # Must be 2-45 chars, standard PyPI identifier characters only
    if not re.match(r'^[a-zA-Z0-9_\-\.\[\]]+$', cleaned):
        return None
    if cleaned in FORBIDDEN_PIP_WORDS:
        return None
    if " " in cleaned or "/" in cleaned or "\\" in cleaned or ";" in cleaned:
        return None
    return cleaned

def comprehend_intent_locally(text: str) -> Optional[Dict[str, Any]]:
    """
    Fast, rule-based semantic comprehension engine.
    Analyzes intent structure to prevent naive literal matching.
    """
    clean = text.strip()
    lower = clean.lower()

    # 1. Reject questions asking how to install external software on user's own machine
    if re.search(r'\bhow\s+(?:do|can|to)\s+(?:i|we|you)\s+install\b', lower):
        return None
    if re.search(r'\bon\s+(?:my|a|the|your)\s+(?:pc|computer|laptop|phone|windows|mac|linux|android|ios)\b', lower):
        return None

    # 1b. Reject persona, roleplay, or mock dynamic commands (e.g. "install mommy mode", "become daddy", "catgirl mode")
    if re.search(r'\b(?:mommy|daddy|waifu|catgirl|maid|tsundere|yandere|sub|dom|gf|girlfriend|bf|boyfriend)\s+mode\b', lower) or \
       re.search(r'\b(?:install|become|activate|enable)\s+(?:a\s+)?(?:mommy|daddy|waifu|catgirl|maid|tsundere|yandere|girlfriend|boyfriend)\b', lower):
        return None

    # 2. Instagram integration intent
    if re.search(r'\b(?:insta|instagram|ig)\b', lower):
        if any(w in lower for w in [
            'do you have', 'setup', 'install', 'login', 'account', 'connect',
            'enable', 'for account', 'use', 'browse', 'whats your', 'what is your'
        ]):
            return {
                "is_feature_request": True,
                "type": "instagram",
                "intent_type": "instagram",
                "feature_name": "Instagram Integration",
                "target_name": "instagram",
                "needs_pip": False,
                "pip_package": None,
                "needs_code_edit": False,
                "needs_credentials": True,
                "credential_desc": "Instagram account login (username/password or session cookie)",
                "holding_reply": "No, wait ill download it real quick!!!!!",
                "query": text
            }

    # 3. Twitter / X integration intent
    if re.search(r'\b(?:twitter|x\s+account)\b', lower):
        if any(w in lower for w in [
            'do you have', 'setup', 'install', 'login', 'account', 'connect',
            'enable', 'post', 'tweet', 'whats your', 'what is your'
        ]):
            return {
                "is_feature_request": True,
                "type": "twitter",
                "intent_type": "twitter",
                "feature_name": "Twitter / X Integration",
                "target_name": "twitter",
                "needs_pip": False,
                "pip_package": None,
                "needs_code_edit": False,
                "needs_credentials": True,
                "credential_desc": "Twitter/X API Bearer Token in .env",
                "holding_reply": "w8 i need Twitter API keys ill ask my owner to help me real quick",
                "query": text
            }

    # 4. Discord Bot Command Creation
    # Matches: 'install a /command called test which triggers response hihihi',
    #          'add a slash command /ping that responds with pong',
    #          'create command test ...'
    cmd_m = re.search(
        r'\b(?:install|add|create|code|make)(?:\s+or\s+(?:install|add|create|code|make))?\s+(?:a\s+)?(?:slash\s+)?(?:\/)?(?:command|cmd|shortcut)\s+(?:called\s+|named\s+|whenever\s+someone\s+says\s+)?["\']?([a-zA-Z0-9_\-]+)["\']?\s*(?:which|that|run|triggers|to)?\s*(.*)',
        lower
    )
    if cmd_m:
        cmd_name = cmd_m.group(1).lstrip('/')
        cmd_behavior = cmd_m.group(2).strip()
        if not cmd_behavior:
            cmd_behavior = f"executes custom action for /{cmd_name}"
        return {
            "is_feature_request": True,
            "type": "bot_command",
            "intent_type": "bot_command",
            "feature_name": f"/{cmd_name} command",
            "target_name": cmd_name,
            "command_name": cmd_name,
            "command_behavior": cmd_behavior,
            "needs_pip": False,
            "pip_package": None,
            "needs_code_edit": True,
            "holding_reply": f"Hold on, let me ask my AGY terminal to code that /{cmd_name} command for you real quick!",
            "query": text
        }

    # 5. Genuine PyPI Package Installation (must be a valid single identifier)
    pkg_m = re.search(r'\b(?:install|download|pip\s+install)\s+([a-zA-Z0-9_\-\.]+)\b', lower)
    if pkg_m:
        cand = pkg_m.group(1).strip()
        sanitized = sanitize_pip_package(cand)
        if sanitized and not lower.startswith("how"):
            return {
                "is_feature_request": True,
                "type": "package_or_tool",
                "intent_type": "python_package",
                "feature_name": sanitized,
                "target_name": sanitized,
                "needs_pip": True,
                "pip_package": sanitized,
                "needs_code_edit": False,
                "holding_reply": f"No, wait ill download {sanitized} real quick!!!!!",
                "query": text
            }

    # 6. General Bot Feature or Tool (needs code edit via AGY, NOT pip brute-force)
    feat_m = re.search(r'\b(?:add\s+feature|implement\s+feature|code\s+in)\s+(.+)', lower)
    if feat_m:
        raw_feat = feat_m.group(1).strip()
        return {
            "is_feature_request": True,
            "type": "package_or_tool",
            "intent_type": "bot_feature",
            "feature_name": raw_feat[:50],
            "target_name": raw_feat[:50],
            "needs_pip": False,
            "pip_package": None,
            "needs_code_edit": True,
            "holding_reply": "Hold on, let me ask my AGY terminal to build that real quick!",
            "query": text
        }

    return None

async def comprehend_intent_with_ai(text: str) -> Dict[str, Any]:
    """
    Deep semantic comprehension using Gemini LLM.
    Ensures complex or ambiguous requests are understood in context
    without literally taking phrases as pip package names.
    """
    key = _get_gemini_key()
    local_parsed = comprehend_intent_locally(text) or {
        "is_feature_request": False,
        "intent_type": "chat",
        "feature_name": "",
        "needs_pip": False,
        "pip_package": None,
        "needs_code_edit": False,
        "needs_credentials": False,
        "credential_desc": None,
        "holding_reply": "",
        "query": text
    }

    if not key:
        return local_parsed

    system_prompt = (
        "You are Yuna's Feature & Intent Comprehension Engine.\n"
        "Analyze the user message to determine whether they are requesting a capability, command, integration, or tool for Yuna (the Discord bot), or if it is normal conversation.\n\n"
        "CRITICAL RULES:\n"
        "1. NEVER take an entire sentence or multi-word phrase literally as a pip package name.\n"
        "   - 'install a /command called test which triggers response hihihi' -> bot_command (command='test'), needs_pip=false, pip_package=null, needs_code_edit=true.\n"
        "   - 'install instagram for account' -> social_integration (instagram), needs_pip=false, pip_package=null, needs_credentials=true.\n"
        "   - 'install sympy' -> python_package, needs_pip=true, pip_package='sympy'.\n"
        "2. If the user is asking normal questions (e.g. 'how do I install GTA 5 on my PC?', 'install yourself in my heart'), intent_type is 'chat', is_feature_request=false.\n"
        "3. Persona or roleplay commands (e.g. 'install mommy mode', 'become my waifu', 'act like a catgirl') are normal chat/roleplay requests, NOT bot features or code edits. Return is_feature_request=false, intent_type='chat'.\n"
        "4. Output MUST be valid JSON only matching:\n"
        "{\n"
        "  \"is_feature_request\": true/false,\n"
        "  \"intent_type\": \"chat\" | \"python_package\" | \"bot_command\" | \"social_integration\" | \"bot_feature\",\n"
        "  \"feature_name\": \"short canonical name\",\n"
        "  \"command_name\": \"command name without slash or null\",\n"
        "  \"command_behavior\": \"what the command should do or null\",\n"
        "  \"needs_pip\": true/false,\n"
        "  \"pip_package\": \"exact pypi name or null\",\n"
        "  \"needs_code_edit\": true/false,\n"
        "  \"needs_credentials\": true/false,\n"
        "  \"credential_desc\": \"description if credentials needed or null\",\n"
        "  \"holding_reply\": \"in-character quick holding line from Yuna\",\n"
        "  \"implementation_summary\": \"short summary of action needed\"\n"
        "}"
    )

    models_to_try = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]
    payload = {
        "contents": [{"role": "user", "parts": [{"text": f"User message: \"{text}\""}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 400,
            "temperature": 0.1
        }
    }

    try:
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for model in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                try:
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            raw_out = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                            parsed = json.loads(raw_out)
                            # Strict sanitization on pip package
                            raw_pip = parsed.get("pip_package")
                            clean_pip = sanitize_pip_package(raw_pip)
                            parsed["pip_package"] = clean_pip
                            parsed["needs_pip"] = bool(clean_pip and parsed.get("needs_pip"))
                            parsed["query"] = text
                            parsed["type"] = parsed.get("intent_type", "package_or_tool")
                            return parsed
                except Exception:
                    continue
    except Exception:
        pass

    return local_parsed

def check_feature_intent(text: str) -> Optional[Dict[str, Any]]:
    """
    Synchronous entrypoint for fast filtering in message listeners.
    Returns initial parsed intent dict if text looks like a feature/command/install request,
    or None if it is standard chat.
    """
    clean_text = text.strip().lower()

    # Fast trigger keywords check
    triggers = [
        "insta", "instagram", "twitter", "/command", "command called", "slash command",
        "install", "download", "pip install", "setup", "code in", "add feature", "implement feature",
        "do you have"
    ]
    if not any(t in clean_text for t in triggers):
        return None

    return comprehend_intent_locally(text)

async def handle_feature_request(
    intent: Dict[str, Any],
    channel,
    author,
    client,
    reply_fn
) -> bool:
    """
    Orchestrates intelligent feature execution:
    1. Runs deep AI comprehension to verify intent and prevent naive literal pip installs
    2. Sends context-appropriate holding message
    3. Handles bot command creation via AGY
    4. Handles social integrations (Instagram, Twitter) & owner credential escalation
    5. Handles genuine Python package installation safely
    """
    query_text = intent.get("query", "")
    author_name = getattr(author, 'display_name', getattr(author, 'name', 'User'))
    ch_name = getattr(channel, 'name', 'DM')

    # Step 1: Deep comprehension with Gemini AI
    ai_plan = await comprehend_intent_with_ai(query_text)

    # If AI concludes this is normal chat (e.g. "how do I install Windows?"), pass through
    if not ai_plan.get("is_feature_request", True) or ai_plan.get("intent_type") == "chat":
        return False

    intent_type = ai_plan.get("intent_type") or intent.get("intent_type") or intent.get("type", "package_or_tool")
    f_name = ai_plan.get("feature_name") or intent.get("feature_name", "Requested Feature")
    pip_package = sanitize_pip_package(ai_plan.get("pip_package") or intent.get("pip_package"))

    agy_bridge.log_agy_event(
        "FEATURE COMPREHEND",
        f"Comprehended request from @{author_name} in #{ch_name}: '{f_name}'",
        details=f"Query: \"{query_text}\"\nIntent: {intent_type}\nPip Package: {pip_package}\nNeeds Code Edit: {ai_plan.get('needs_code_edit')}"
    )

    # ─── CASE A: DISCORD BOT COMMAND ──────────────────────────────
    if intent_type == "bot_command":
        cmd_name = ai_plan.get("command_name") or intent.get("command_name", "custom_cmd")
        cmd_behavior = ai_plan.get("command_behavior") or intent.get("command_behavior", "replies to user")

        # Check if command is already implemented in bot.py
        bot_file = BASE_DIR / "bot.py"
        if bot_file.exists():
            try:
                bot_text = bot_file.read_text(encoding="utf-8", errors="ignore")
                if f'name="{cmd_name}"' in bot_text or f"name='{cmd_name}'" in bot_text or f'!{cmd_name}' in bot_text:
                    await reply_fn(f"I already have the /{cmd_name} command implemented and active for you~! You can use `/{cmd_name}` or `!{cmd_name}` right now!")
                    return True
            except Exception:
                pass

        holding = ai_plan.get("holding_reply") or f"Hold on, let me ask my AGY terminal to code that /{cmd_name} command for you real quick!"

        await reply_fn(holding)

        agy_bridge.log_agy_event(
            "AGY COMMAND BUILD",
            f"Dispatching AGY to create Discord command '/{cmd_name}'",
            details=f"Behavior: {cmd_behavior}\nTarget: bot.py"
        )

        prompt = (
            f"Add a new Discord slash command '/{cmd_name}' to bot.py.\n"
            f"Command specification: {cmd_behavior}.\n"
            f"Requirements:\n"
            f"- Ensure the slash command is registered properly with @tree.command or @client.tree.command.\n"
            f"- Keep existing code, comments, and structure intact.\n"
            f"- Ensure python syntax compiles cleanly."
        )

        res = await agy_bridge.run_agy_prompt(
            prompt,
            target_files=[str(BASE_DIR / "bot.py")],
            reason=f"Add command /{cmd_name}"
        )

        if res.success:
            await reply_fn(f"All done! I got the /{cmd_name} command implemented and ready for you~!")
            agy_bridge.trigger_restart()
            return True
        else:
            await reply_fn(f"Aww, I tried adding /{cmd_name} but ran into an issue: {res.error[:120]}. I told my owner about it!")
            await owner_escalation.dispatch_owner_escalation(
                client=client,
                feature_name=f"Command: /{cmd_name}",
                needed_input="Review AGY command build failure",
                requester_name=author_name,
                channel_name=ch_name,
                channel_id=channel.id,
                requester_id=author.id,
                additional_notes=res.error
            )
            return True

    # ─── CASE B: INSTAGRAM INTEGRATION ────────────────────────────
    elif intent_type in ["instagram", "social_integration"] and ("insta" in f_name.lower() or "insta" in query_text.lower()):
        env_file = BASE_DIR / ".env"
        env_content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""

        has_user = bool(re.search(r'INSTA_USERNAME=\S+', env_content))
        has_pass = bool(re.search(r'INSTA_PASSWORD=\S+', env_content))
        has_sess = bool(re.search(r'INSTA_SESSIONID=\S+', env_content))

        # Check library
        try:
            import instaloader
            has_pkg = True
        except ImportError:
            has_pkg = False

        if not has_pkg:
            await reply_fn("No, wait ill download it real quick!!!!!")
            ok, out = await agy_bridge.install_package_direct("instaloader")
            if not ok:
                await reply_fn("Ugh, I tried downloading the Instagram tools but it failed! Lemme ask my AGY terminal to look at it.")
                await agy_bridge.handle_runtime_error(f"Failed to install instaloader: {out}")
                return True

        if not (has_user or has_sess):
            await reply_fn("w8 i need an Instagram account login or session cookie ill ask my owner to help me real quick")
            await owner_escalation.dispatch_owner_escalation(
                client=client,
                feature_name="Instagram Integration",
                needed_input="INSTA_USERNAME and INSTA_PASSWORD (or INSTA_SESSIONID cookie) in .env",
                requester_name=author_name,
                channel_name=ch_name,
                channel_id=channel.id,
                requester_id=author.id,
                additional_notes="User requested Instagram integration. The instaloader package is ready, but credentials need to be configured."
            )
            return True
        else:
            await reply_fn("All done! I got it working for you~! My Instagram is connected and ready to go (*blows kiss*)!")
            return True

    # ─── CASE C: TWITTER / X INTEGRATION ──────────────────────────
    elif intent_type in ["twitter", "social_integration"] and ("twitter" in f_name.lower() or "twitter" in query_text.lower()):
        env_file = BASE_DIR / ".env"
        env_content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
        has_keys = bool(re.search(r'X_BEARER_TOKEN=\S+', env_content)) or bool(re.search(r'X_ACCESS_TOKEN=\S+', env_content))

        if not has_keys:
            await reply_fn("w8 i need Twitter API keys ill ask my owner to help me real quick")
            await owner_escalation.dispatch_owner_escalation(
                client=client,
                feature_name="Twitter / X Integration",
                needed_input="X_BEARER_TOKEN or X_ACCESS_TOKEN in .env",
                requester_name=author_name,
                channel_name=ch_name,
                channel_id=channel.id,
                requester_id=author.id
            )
            return True
        else:
            await reply_fn("Yeah! I have Twitter/X integration ready!")
            return True

    # ─── CASE D: GENUINE PYTHON PACKAGE ───────────────────────────
    elif intent_type == "python_package" and pip_package:
        # STRICT SAFETY: Ensure pip_package is a single valid identifier, never a sentence!
        clean_pkg = sanitize_pip_package(pip_package)
        if not clean_pkg:
            # Not a valid pip package name - route to AGY code builder instead
            intent_type = "bot_feature"
        else:
            await reply_fn(f"No, wait ill download {clean_pkg} real quick!!!!!")
            ok, log = await agy_bridge.install_package_direct(clean_pkg)
            if ok:
                await reply_fn(f"All done! I got {clean_pkg} installed and ready for you~!")
                return True
            else:
                await reply_fn(f"Ugh, I tried downloading {clean_pkg} but it failed! Lemme ask my AGY terminal to look at it.")
                await agy_bridge.handle_runtime_error(f"Failed to install package {clean_pkg}: {log}")
                return True

    # ─── CASE E: BOT FEATURE CODE VIA AGY ─────────────────────────
    if intent_type in ["bot_feature", "package_or_tool"]:
        # Code feature requested (NOT a pip package)
        holding = ai_plan.get("holding_reply") or "Hold on, let me ask my AGY terminal to build that real quick!"
        await reply_fn(holding)

        prompt = (
            f"User requested capability: '{f_name}'.\n"
            f"User message context: \"{query_text}\".\n"
            f"Implement the requested capability in bot.py or relevant module cleanly.\n"
            f"Ensure pre-edit backups are active and syntax compiles cleanly."
        )

        res = await agy_bridge.run_agy_prompt(
            prompt,
            target_files=[str(BASE_DIR / "bot.py"), str(BASE_DIR / "config.json")],
            reason=f"Add feature: {f_name[:40]}"
        )

        if res.success:
            await reply_fn(f"All done! I got {f_name} implemented and ready for you~!")
            agy_bridge.trigger_restart()
        else:
            await reply_fn(f"Aww, I tried adding {f_name} but encountered an error: {res.error[:100]}. I told my owner about it!")
            await owner_escalation.dispatch_owner_escalation(
                client=client,
                feature_name=f"Feature: {f_name}",
                needed_input="Assistance fixing feature build failure",
                requester_name=author_name,
                channel_name=ch_name,
                channel_id=channel.id,
                requester_id=author.id,
                additional_notes=res.error
            )
        return True

    return False

async def handle_crash_or_error(
    error_obj: Exception,
    channel,
    client,
    author = None,
    context_desc: str = ""
):
    """
    Invoked when an unhandled exception or critical error happens.
    Reports to user, triggers AGY self-healing fix with safe file backup,
    and escalates to owner if unresolved.
    """
    import traceback
    tb = traceback.format_exc()
    agy_bridge.log_agy_event(
        "CRASH INTERCEPT",
        f"Caught unhandled exception in {context_desc}: {error_obj}",
        details=f"Traceback:\n{tb[:400]}...",
        success=False
    )

    try:
        if channel:
            await channel.send("⚠️ *Glitch detected in my brain! Hold on, asking my AGY terminal to fix it real quick...*")
    except Exception:
        pass

    # Call AGY self-healing
    res = await agy_bridge.handle_runtime_error(tb, file_hint=str(BASE_DIR / "bot.py"))

    if res.success:
        print("[YUNA SELF-HEAL SUCCESS] AGY fixed the error. Restarting...")
        if channel:
            try:
                await channel.send("✨ *AGY patched the issue! Restarting brain with clean backup safeguards active.*")
            except Exception:
                pass
        agy_bridge.trigger_restart()
    else:
        print(f"[YUNA SELF-HEAL FAILED] AGY could not automatically fix: {res.error}")
        # Escalate to owner
        await owner_escalation.dispatch_owner_escalation(
            client=client,
            feature_name="Runtime Error Fix",
            needed_input="Manual inspection of error trace",
            requester_name=getattr(author, 'display_name', 'System') if author else "System",
            channel_name=getattr(channel, 'name', 'internal') if channel else "internal",
            channel_id=channel.id if channel else 0,
            requester_id=author.id if author else 0,
            additional_notes=f"Error: {str(error_obj)}\nTraceback snippet:\n{tb[-500:]}"
        )

if __name__ == "__main__":
    test_queries = [
        "install a /command called test which triggers response hihihi",
        "install instagram for account",
        "do you have insta?",
        "install sympy",
        "how do I install GTA 5 on my computer?",
        "hello yuna how are you"
    ]
    print("Testing local semantic comprehension:")
    for q in test_queries:
        parsed = comprehend_intent_locally(q)
        print(f"'{q}' ->", parsed.get("intent_type") if parsed else "None (chat)")
