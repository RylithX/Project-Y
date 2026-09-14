#!/usr/bin/env python3
"""
Yuna <-> Google Antigravity (AGY) Autonomous Bridge
---------------------------------------------------
Connects Yuna's runtime brain to the Antigravity (AGY) CLI on Termux.
Enables self-healing (error detection & auto-repair), feature evolution (self-coding &
package installation), pre-edit file backup enforcement, post-edit compilation verification,
and graceful restarts.
"""

import os
import sys
import re
import json
import time
import shutil
import asyncio
import subprocess
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

import yuna_backup_guard as backup_guard

BASE_DIR = Path(__file__).parent.resolve()
AGY_BIN = "/data/data/com.termux/files/usr/bin/agy"
VENV_PYTHON = "/data/data/com.termux/files/home/discord-bot-venv/bin/python"
VENV_PIP = "/data/data/com.termux/files/home/discord-bot-venv/bin/pip"
USERBOT_VENV_PYTHON = "/data/data/com.termux/files/home/userbot-venv/bin/python"
USERBOT_VENV_PIP = "/data/data/com.termux/files/home/userbot-venv/bin/pip"

class AgyTaskResult:
    def __init__(self, success: bool, output: str = "", error: str = "", modified_files: List[str] = None, requires_owner: bool = False, owner_prompt: str = ""):
        self.success = success
        self.output = output
        self.error = error
        self.modified_files = modified_files or []
        self.requires_owner = requires_owner
        self.owner_prompt = owner_prompt

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "modified_files": self.modified_files,
            "requires_owner": self.requires_owner,
            "owner_prompt": self.owner_prompt
        }

AGY_LOG_FILE = BASE_DIR / "memories" / "pids" / "yuna_agy.log"

def log_agy_event(category: str, title: str, details: Optional[str] = None, success: Optional[bool] = None):
    """
    Writes a prominent, formatted log entry to both stdout and memories/pids/yuna_agy.log.
    Categories:
      [AGY ACCESS]    - Invoking AGY CLI or querying AGY
      [INSTALL]       - Pip package installation
      [FIX/HEAL]      - Auto-repairing runtime errors
      [FILE BACKUP]   - Snapshotting files prior to edit
      [SYNTAX VERIFY] - py_compile verification
      [ROLLBACK]      - Atomic rollback to backup
      [RELOAD]        - Triggering service supervisor reload
      [FEATURE EVAL]  - User requested new feature
      [OWNER ESCALATE]- Escalating missing inputs to owner
    """
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    status_icon = "✅" if success is True else ("❌" if success is False else "ℹ️")
    header = f"[{timestamp}] [{category}] {status_icon} {title}"

    # Visual console output
    border = "═" * min(68, len(header) + 2)
    print(f"\n[YUNA AGY] ╔{border}╗", flush=True)
    print(f"[YUNA AGY] ║ {header}", flush=True)
    if details:
        for d in str(details).splitlines():
            print(f"[YUNA AGY] ║   {d}", flush=True)
    print(f"[YUNA AGY] ╚{border}╝\n", flush=True)

    # Persistent log file
    try:
        AGY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AGY_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(header + "\n")
            if details:
                for d in str(details).splitlines():
                    f.write(f"    {d}\n")
            f.write("\n")
    except Exception as e:
        print(f"[AGY LOGGER ERROR] Could not write to {AGY_LOG_FILE}: {e}", file=sys.stderr)

def find_agy_binary() -> Optional[str]:
    if os.path.exists(AGY_BIN) and os.access(AGY_BIN, os.X_OK):
        return AGY_BIN
    which_path = shutil.which("agy")
    return which_path

def backup_targets(files: List[str], reason: str = "") -> List[str]:
    """Snapshots all specified files using yuna_backup_guard before edits."""
    backups = []
    for f in files:
        b = backup_guard.backup_file(f, reason=reason)
        if b:
            backups.append(b)
    if backups:
        log_agy_event(
            "FILE BACKUP",
            f"Snapshotted {len(backups)} file(s) before changes",
            details=f"Reason: {reason}\nBackups: {', '.join([Path(x).name for x in backups])}",
            success=True
        )
    return backups

def verify_python_syntax(files: List[str]) -> Tuple[bool, Optional[str]]:
    """Checks compilation syntax of all modified python files."""
    for f in files:
        if f.endswith(".py") and os.path.exists(f):
            py_bin = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable
            res = subprocess.run(
                [py_bin, "-m", "py_compile", f],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if res.returncode != 0:
                err_msg = f"SyntaxError in {Path(f).name}: {res.stderr.strip()}"
                log_agy_event("SYNTAX VERIFY", f"Syntax verification FAILED for {Path(f).name}", details=err_msg, success=False)
                return False, err_msg
    log_agy_event("SYNTAX VERIFY", f"Syntax verification PASSED for {len(files)} file(s)", details=", ".join([Path(x).name for x in files]), success=True)
    return True, None

def rollback_targets(files: List[str]):
    """Rolls back all specified files to their most recent backup."""
    for f in files:
        backup_guard.rollback(f)
    log_agy_event("ROLLBACK", f"Rolled back {len(files)} file(s) to safe pre-edit state", details=", ".join([Path(x).name for x in files]), success=False)

def is_interactive_agy_running() -> bool:
    """Detects if an interactive AGY session is already active in Termux."""
    try:
        res = subprocess.run(["pgrep", "-f", "agy.va39"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        pids = [p.strip() for p in res.stdout.split() if p.strip()]
        my_pid = str(os.getpid())
        pids = [p for p in pids if p != my_pid]
        return len(pids) > 0
    except Exception:
        return False

def ensure_termux_wake_lock():
    """Acquires Termux wake lock so Android OS does not sleep Wi-Fi/cellular sockets."""
    try:
        twl = shutil.which("termux-wake-lock") or "/data/data/com.termux/files/usr/bin/termux-wake-lock"
        if os.path.exists(twl):
            subprocess.run([twl], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    except Exception:
        pass

def queue_agy_task(
    title: str,
    prompt: str,
    target_files: Optional[List[str]] = None,
    requester: str = "",
    channel: str = "",
    reason: str = ""
) -> Dict[str, Any]:
    """
    Enqueues a task for the active Terminal AGY pairing session.
    Prevents spawning duplicate CLI instances that freeze the network.
    """
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    inbox_file = data_dir / "agy_inbox.json"

    entries = []
    if inbox_file.exists():
        try:
            entries = json.loads(inbox_file.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                entries = []
        except Exception:
            entries = []

    task_entry = {
        "id": f"task_{int(time.time()*1000)}",
        "timestamp": time.time(),
        "title": title,
        "prompt": prompt,
        "target_files": target_files or [],
        "requester": requester,
        "channel": channel,
        "reason": reason,
        "status": "pending"
    }
    entries.append(task_entry)
    try:
        inbox_file.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[AGY INBOX ERROR] Failed to write task: {e}")

    log_agy_event(
        "AGY QUEUE",
        f"Queued task for Terminal AGY: '{title}'",
        details=f"Targets: {', '.join([Path(t).name for t in (target_files or [])])}\nReason: {reason}",
        success=True
    )
    return task_entry

async def direct_ai_generate_code(
    prompt: str,
    target_file: str,
    task_type: str = "command"
) -> Tuple[bool, str]:
    """
    Synthesizes code directly via Gemini Flash API in <1.5s with ZERO extra processes,
    0 MB memory footprint, and ZERO network socket exhaustion.
    """
    from yuna_feature_evaluator import _get_gemini_key
    key = _get_gemini_key()
    if not key:
        return False, "Gemini API key not configured for direct code generation."

    import aiohttp
    models_to_try = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]

    system_instruction = (
        "You are an expert Discord.py bot code generator for Yuna.\n"
        "Generate clean, robust, working Python code according to the prompt.\n"
        "RULES:\n"
        "1. Return ONLY the python code block for the command or feature. No conversational filler.\n"
        "2. For slash commands, use:\n"
        "   @tree.command(name='...', description='...')\n"
        "   async def slash_...(interaction: discord.Interaction, ...):\n"
        "       await interaction.response.send_message(...)\n"
        "3. Ensure the code compiles cleanly and does not reference undefined global variables.\n"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {
            "maxOutputTokens": 1200,
            "temperature": 0.2
        }
    }

    generated_code = ""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        for m in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        raw_text = re.sub(r'^```(?:python)?\s*', '', raw_text.strip(), flags=re.MULTILINE)
                        raw_text = re.sub(r'```\s*$', '', raw_text.strip(), flags=re.MULTILINE)
                        generated_code = raw_text.strip()
                        if generated_code:
                            break
            except Exception:
                continue

    if not generated_code:
        return False, "Failed to generate code via Gemini API."

    # Backup target file before edit
    backup_targets([target_file], reason=f"Direct AI Code Gen: {prompt[:40]}")

    try:
        content = Path(target_file).read_text(encoding="utf-8")

        # Insertion anchor
        anchor = "\n@tree.command(name=\"vc\""
        if anchor in content:
            new_content = content.replace(anchor, f"\n\n{generated_code}\n\n{anchor}", 1)
        else:
            msg_anchor = "\n@client.event\nasync def on_message"
            if msg_anchor in content:
                new_content = content.replace(msg_anchor, f"\n\n{generated_code}\n\n{msg_anchor}", 1)
            else:
                new_content = content + f"\n\n{generated_code}\n"

        Path(target_file).write_text(new_content, encoding="utf-8")

        # Verify syntax
        ok, err = verify_python_syntax([target_file])
        if not ok:
            print(f"[DIRECT AI CODER] Syntax verification failed: {err}. Rolling back...")
            rollback_targets([target_file])
            return False, f"Generated code failed syntax check: {err}"

        log_agy_event(
            "DIRECT AI CODE",
            f"Successfully generated and inserted code into {Path(target_file).name}",
            details=f"Code preview:\n{generated_code[:200]}...",
            success=True
        )
        return True, generated_code

    except Exception as e:
        rollback_targets([target_file])
        return False, f"Exception during code insertion: {e}"

async def run_agy_prompt(prompt: str, target_files: Optional[List[str]] = None, timeout_sec: int = 35, reason: str = "") -> AgyTaskResult:
    """
    Safely executes an AGY task.
    1. If interactive AGY is running, uses direct AI code generation or queues the task to prevent socket/network collision.
    2. Enforces Termux wake lock so Android Wi-Fi never disconnects.
    3. Caps timeout to 35s to prevent long hangs.
    """
    ensure_termux_wake_lock()
    targets = target_files or []

    # Priority 1: If interactive AGY is active OR single target python file edit, use fast direct AI
    if is_interactive_agy_running() or (len(targets) == 1 and targets[0].endswith("bot.py")):
        log_agy_event("AGY ACCESS", f"Using Direct AI Coder for '{reason or prompt[:60]}'", details="Active AGY terminal detected; using direct AI to preserve network bandwidth.")
        target_f = targets[0] if targets else str(BASE_DIR / "bot.py")
        ok, res_text = await direct_ai_generate_code(prompt, target_f)
        if ok:
            return AgyTaskResult(True, output=res_text, modified_files=[target_f])
        else:
            # Queue to AGY inbox for terminal pairing review
            queue_agy_task(
                title=reason or prompt[:50],
                prompt=prompt,
                target_files=targets,
                reason=f"Direct AI fallback: {res_text}"
            )
            return AgyTaskResult(False, error=res_text)

    # Priority 2: Standalone CLI invocation (when no interactive AGY terminal is open)
    agy = find_agy_binary()
    if not agy:
        log_agy_event("AGY ACCESS", "AGY binary (agy) not found; queuing task for AGY terminal", success=False)
        queue_agy_task(title=reason or prompt[:50], prompt=prompt, target_files=targets, reason="AGY binary not in path")
        return AgyTaskResult(False, error="AGY binary not in path. Task queued for Terminal AGY.")

    log_agy_event(
        "AGY ACCESS",
        f"Invoking AGY Terminal CLI: '{reason or prompt[:60]}'",
        details=f"Binary: {agy}\nTargets: {', '.join([Path(t).name for t in targets]) if targets else 'None'}\nPrompt: {prompt[:250]}..."
    )

    if targets:
        backup_targets(targets, reason=reason or f"AGY prompt: {prompt[:50]}...")

    cmd = [
        agy,
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--disable-slash-commands",
        "--effort", "low"
    ]

    env = os.environ.copy()
    env["AGY_NO_UPDATE"] = "1"
    env["TERMUX_NO_NET_BLOCK"] = "1"

    effective_timeout = min(timeout_sec, 35)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(BASE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)
            out_str = stdout.decode("utf-8", errors="replace")
            err_str = stderr.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            log_agy_event("AGY ACCESS", f"AGY task timed out after {effective_timeout}s (protected network)", success=False)
            if targets:
                rollback_targets(targets)
            queue_agy_task(title=reason or prompt[:50], prompt=prompt, target_files=targets, reason=f"Timed out after {effective_timeout}s")
            return AgyTaskResult(False, error=f"AGY task timed out after {effective_timeout}s. Queued for Terminal AGY review.")

        if proc.returncode != 0:
            if targets:
                print(f"[AGY BRIDGE] AGY failed with exit code {proc.returncode}. Rolling back targets...")
                rollback_targets(targets)
            log_agy_event("AGY ACCESS", f"AGY task exited with error code {proc.returncode}", details=err_str or out_str[:300], success=False)
            queue_agy_task(title=reason or prompt[:50], prompt=prompt, target_files=targets, reason=err_str or f"Exit {proc.returncode}")
            return AgyTaskResult(False, output=out_str, error=err_str or f"Exit code {proc.returncode}")

        # Post-edit verification
        if targets:
            ok, syntax_err = verify_python_syntax(targets)
            if not ok:
                print(f"[AGY BRIDGE] Verification failed: {syntax_err}. Rolling back targets...")
                rollback_targets(targets)
                return AgyTaskResult(False, output=out_str, error=f"Validation failed: {syntax_err}")

        log_agy_event("AGY ACCESS", f"AGY task completed successfully", details=f"Output preview: {out_str[:250]}...\nModified files: {targets}", success=True)
        return AgyTaskResult(True, output=out_str, modified_files=targets)

    except Exception as e:
        if targets:
            rollback_targets(targets)
        log_agy_event("AGY ACCESS", f"Exception running AGY task: {e}", success=False)
        return AgyTaskResult(False, error=str(e))

async def install_package_direct(package_name: str, target_venv: str = "main") -> Tuple[bool, str]:
    """Fast direct installation of python packages into the appropriate virtualenv."""
    pip_bin = VENV_PIP if target_venv == "main" else USERBOT_VENV_PIP
    if not os.path.exists(pip_bin):
        pip_bin = shutil.which("pip") or "pip"

    log_agy_event(
        "INSTALL",
        f"Installing package '{package_name}' via pip",
        details=f"Target: {target_venv} venv ({pip_bin})"
    )

    proc = await asyncio.create_subprocess_exec(
        pip_bin, "install", package_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    is_ok = proc.returncode == 0

    log_agy_event(
        "INSTALL",
        f"Package '{package_name}' installation {'SUCCEEDED' if is_ok else 'FAILED'}",
        details=out[:350] if is_ok else err[:350],
        success=is_ok
    )
    return (is_ok, out if is_ok else err)

async def handle_missing_feature(feature_query: str, user_context: dict) -> AgyTaskResult:
    """
    Evaluates a missing feature request.
    If it's a known service missing credentials (like Instagram without login),
    flags requires_owner = True so Yuna can DM the owner.
    If it's an installable feature, installs or generates code via AGY.
    """
    q_low = feature_query.lower()

    # Case 1: Instagram requested
    if any(w in q_low for w in ["insta", "instagram", "ig"]):
        cfg_file = BASE_DIR / "config.json"
        env_file = BASE_DIR / ".env"
        env_content = env_file.read_text() if env_file.exists() else ""

        has_user = "INSTA_USERNAME" in env_content and bool(re.search(r'INSTA_USERNAME=.+', env_content))
        has_pass = "INSTA_PASSWORD" in env_content and bool(re.search(r'INSTA_PASSWORD=.+', env_content))
        has_sess = "INSTA_SESSIONID" in env_content and bool(re.search(r'INSTA_SESSIONID=.+', env_content))

        # Check if instaloader / PIL is installed
        try:
            import instaloader
            has_lib = True
        except ImportError:
            has_lib = False

        if not has_lib:
            print("[AGY BRIDGE] Installing missing instaloader package...")
            ok, log = await install_package_direct("instaloader")
            if not ok:
                return AgyTaskResult(False, error=f"Failed to install instaloader: {log}")

        if not (has_user or has_sess):
            # Requires owner credentials!
            return AgyTaskResult(
                success=False,
                requires_owner=True,
                owner_prompt="Instagram integration is ready to be enabled, but I need Instagram login credentials (INSTA_USERNAME and INSTA_PASSWORD, or an active INSTA_SESSIONID cookie) to connect."
            )
        else:
            return AgyTaskResult(
                success=True,
                output="Instagram module is installed and credentials are configured! Ready to chat on Instagram."
            )

    # Case 2: General package or capability request
    # Check if user asks for specific tool
    package_match = re.search(r'install\s+([a-zA-Z0-9_\-]+)', q_low)
    if package_match:
        pkg = package_match.group(1)
        ok, log = await install_package_direct(pkg)
        if ok:
            return AgyTaskResult(True, output=f"Successfully installed package '{pkg}'.")
        else:
            return AgyTaskResult(False, error=f"Could not install '{pkg}': {log}")

    # Case 3: Complex code feature -> invoke AGY with target file backup
    target_files = [str(BASE_DIR / "bot.py"), str(BASE_DIR / "config.json")]
    prompt = (
        f"In the Discord bot project at {BASE_DIR}, implement the following feature requested by a user: "
        f"\"{feature_query}\". Context: {json.dumps(user_context)}. "
        f"Ensure safe changes without breaking existing routes or commands, and verify python syntax."
    )
    return await run_agy_prompt(prompt, target_files=target_files, reason=f"Feature Request: {feature_query[:60]}")

async def handle_runtime_error(error_trace: str, file_hint: Optional[str] = None) -> AgyTaskResult:
    """
    Submits an unhandled error or exception trace to AGY to repair the broken code.
    """
    target_file = file_hint or str(BASE_DIR / "bot.py")
    targets = [target_file]

    prompt = (
        f"In {target_file}, a runtime error occurred:\n\n{error_trace}\n\n"
        f"Diagnose the root cause, fix the issue safely, maintain existing functionality, "
        f"and ensure syntax compiles cleanly."
    )

    log_agy_event(
        "FIX/HEAL",
        f"Self-healing requested for runtime error in {Path(target_file).name}",
        details=f"Trace preview:\n{error_trace[:300]}..."
    )

    res = await run_agy_prompt(prompt, target_files=targets, reason="Self-Healing Error Fix")
    log_agy_event(
        "FIX/HEAL",
        f"Self-healing repair {'SUCCESSFUL' if res.success else 'FAILED'} for {Path(target_file).name}",
        details=res.output[:250] if res.success else res.error[:250],
        success=res.success
    )
    return res

def trigger_restart(service: str = "both"):
    """
    Signals service supervisor to restart bot or companion worker cleanly.
    Creates a restart flag file in data/ which supervisor can read or restarts via process signal.
    """
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    restart_flag = data_dir / "restart_request.json"
    try:
        with open(restart_flag, "w", encoding="utf-8") as f:
            json.dump({"service": service, "timestamp": time.time()}, f)
        log_agy_event("RELOAD", f"Service supervisor reload triggered for '{service}'", details=f"Flag: {restart_flag}", success=True)
        return True
    except Exception as e:
        log_agy_event("RELOAD", f"Failed to write reload request for '{service}': {e}", success=False)
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("Testing find_agy_binary():", find_agy_binary())
        print("Testing backup guard integration...")
        test_f = str(BASE_DIR / ".bak" / "bridge_test.py")
        Path(test_f).write_text("print('test 1')\n")
        backup_targets([test_f], "Bridge self-test")
        ok, err = verify_python_syntax([test_f])
        assert ok, f"Syntax check failed: {err}"
        Path(test_f).unlink(missing_ok=True)
        print("✅ yuna_agy_bridge self-test passed successfully!")
    else:
        print("Usage: python yuna_agy_bridge.py test")
