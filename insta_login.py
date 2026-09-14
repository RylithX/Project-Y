import os
import sys
from pathlib import Path
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, TwoFactorRequired
from dotenv import load_dotenv

load_dotenv()

username = os.environ.get("INSTA_USERNAME")
password = os.environ.get("INSTA_PASSWORD")

if not username or not password:
    print("❌ Error: INSTA_USERNAME or INSTA_PASSWORD not found in .env")
    sys.exit(1)

print(f"Logging in to Instagram as {username}...")
cl = Client()
session_file = Path("data/insta_session.json")

def challenge_code_handler(username, choice):
    print(f"\n[!] Instagram has sent a verification code to your email/phone.")
    return input("Enter the 6-digit verification code: ")

cl.challenge_code_handler = challenge_code_handler

def save_all_sessions(client):
    session_file.parent.mkdir(parents=True, exist_ok=True)
    client.dump_settings(session_file)
    yuna_session = Path("data/insta_session_yuna.json")
    client.dump_settings(yuna_session)
    sid = client.sessionid or (client.settings.get("authorization_data") or {}).get("sessionid") or (client.settings.get("cookies") or {}).get("sessionid")
    if sid:
        # Update .env
        env_path = Path(".env")
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("INSTA_SESSIONID="):
                    new_lines.append(f"INSTA_SESSIONID={sid}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"INSTA_SESSIONID={sid}")
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print(f"✅ Session ID updated in .env: {sid[:20]}...")
    print("\n✅ SUCCESS! Session saved to data/insta_session.json and data/insta_session_yuna.json")
    print("Yuna's Instagram integration is ready to go!")

try:
    cl.login(username, password)
    save_all_sessions(cl)
except TwoFactorRequired:
    print("\n[!] 2FA is enabled on your account.")
    code = input("Enter your 2FA code from your authenticator app/SMS: ")
    try:
        cl.login(username, password, verification_code=code)
        save_all_sessions(cl)
    except Exception as e:
        print(f"\n❌ 2FA Login Failed: {e}")
except ChallengeRequired as e:
    print("\n❌ Challenge Failed: Instagram blocked automated password login.")
    print("Please open the Instagram app on your phone, look for 'Suspicious Login Attempt', and tap 'This Was Me'.")
    print("\nAlternatively, you can provide your browser sessionid cookie:")
    sid_input = input("Paste your sessionid cookie (or press Enter to skip): ").strip()
    if sid_input:
        try:
            import urllib.parse
            clean_sid = urllib.parse.unquote(sid_input)
            cl.login_by_sessionid(clean_sid)
            save_all_sessions(cl)
        except Exception as se:
            print(f"❌ Session ID login failed: {se}")
except Exception as e:
    print(f"\n❌ Login Failed: {e}")
    print("\nAlternatively, you can provide your browser sessionid cookie:")
    sid_input = input("Paste your sessionid cookie (or press Enter to skip): ").strip()
    if sid_input:
        try:
            import urllib.parse
            clean_sid = urllib.parse.unquote(sid_input)
            cl.login_by_sessionid(clean_sid)
            save_all_sessions(cl)
        except Exception as se:
            print(f"❌ Session ID login failed: {se}")
