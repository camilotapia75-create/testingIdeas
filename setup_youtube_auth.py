#!/usr/bin/env python3
"""
One-time setup — run LOCALLY on your laptop (not in GitHub Actions), OR use the
browser-only OAuth Playground method your assistant gave you.

It authorizes the YouTube permissions the agent needs (upload + comment + playlist)
and prints the three values to paste as GitHub secrets:
  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
  YOUTUBE_REFRESH_TOKEN

Prereqs:  pip install google-auth-oauthlib google-api-python-client
Then put your downloaded client_secret.json next to this file and run it.
"""

import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

# force-ssl covers uploading, commenting, and managing playlists with one token.
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
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
