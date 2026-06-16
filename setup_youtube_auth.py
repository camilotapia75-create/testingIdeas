#!/usr/bin/env python3
"""
One-time setup script — run this LOCALLY on your laptop (not in GitHub Actions).

It opens a browser for you to log in to Google and authorize the YouTube upload
permission. After you approve, it prints three values to paste as GitHub secrets:
  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
  YOUTUBE_REFRESH_TOKEN

Prerequisites:
  pip install google-auth-oauthlib google-api-python-client

Usage:
  1. Go to https://console.cloud.google.com/
  2. Create a project (or use an existing one)
  3. Enable "YouTube Data API v3" in APIs & Services > Library
  4. Go to APIs & Services > Credentials > Create Credentials > OAuth client ID
  5. Application type: Desktop app  (NOT Web application)
  6. Download the JSON file and save it as client_secret.json in this folder
  7. Run: python setup_youtube_auth.py
  8. Copy the three printed values into GitHub Secrets
"""

import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = "client_secret.json"

if not Path(CLIENT_SECRET_FILE).exists():
    print(f"ERROR: {CLIENT_SECRET_FILE} not found.")
    print("Download it from Google Cloud Console > APIs & Services > Credentials")
    raise SystemExit(1)

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
creds = flow.run_local_server(port=0)

client_info = json.loads(Path(CLIENT_SECRET_FILE).read_text())
outer = client_info.get("installed") or client_info.get("web", {})

print("\n" + "=" * 60)
print("SUCCESS! Add these 3 values as GitHub repository secrets:")
print("=" * 60)
print(f"\nYOUTUBE_CLIENT_ID\n  {outer['client_id']}")
print(f"\nYOUTUBE_CLIENT_SECRET\n  {outer['client_secret']}")
print(f"\nYOUTUBE_REFRESH_TOKEN\n  {creds.refresh_token}")
print("\n" + "=" * 60)
print("Add them at: https://github.com/camilotapia75-create/testingideas/settings/secrets/actions")
