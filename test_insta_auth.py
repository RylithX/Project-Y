import os
import sys
import logging
from pathlib import Path
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, LoginRequired, TwoFactorRequired

logging.basicConfig(level=logging.INFO)

cl = Client()
session_file = Path("data/insta_session.json")

def challenge_code_handler(username, choice):
    print(f"\n[INSTAGRAM CHALLENGE] Instagram requested verification code for choice: {choice}")
    # Default to email or SMS
    return None

cl.challenge_code_handler = challenge_code_handler

if session_file.exists():
    try:
        cl.load_settings(session_file)
        print("Loaded existing session.")
    except Exception as e:
        print("Could not load session:", e)

try:
    import urllib.parse
    sess_id_raw = "28101846244:zxTBaidHletx94:27:AYhVP_G5LQJFp9mLVjcDYm_HXehKmA0kC85DNIYQGw"
    sess_id = urllib.parse.unquote(sess_id_raw.strip())
    print("Attempting login via new session ID...")
    cl.login_by_sessionid(sess_id)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    cl.dump_settings(session_file)
    print("LOGIN SUCCESS! Session saved to data/insta_session.json")
    user_id = cl.user_id
    print(f"Logged in as {user_id}")
    threads = cl.direct_threads(amount=3)
    print(f"Fetched {len(threads)} DM threads successfully.")
except TwoFactorRequired:
    print("TwoFactorRequired: 2FA is enabled on this account.")
except ChallengeRequired as e:
    print("ChallengeRequired exception:", e)
except Exception as e:
    print("Login error:", type(e), e)
