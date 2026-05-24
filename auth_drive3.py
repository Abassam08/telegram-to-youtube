"""One-time OAuth for Drive account1 (abassam912@gmail.com).

Replaces the previous account1 token. Sign in as abassam912@gmail.com
when the browser URL is printed.
"""
from google_auth_oauthlib.flow import InstalledAppFlow
import config

SCOPES = ["https://www.googleapis.com/auth/drive"]
flow   = InstalledAppFlow.from_client_secrets_file(config.DRIVE_CLIENT_SECRETS, SCOPES)

print("Sign in as abassam912@gmail.com in the browser.")
creds  = flow.run_local_server(port=8083, open_browser=False)

with open(config.DRIVE_ACCOUNTS[0]["token_file"], "w") as f:
    f.write(creds.to_json())
print("Drive account1 authorised →", config.DRIVE_ACCOUNTS[0]["token_file"])
