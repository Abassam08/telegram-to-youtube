"""One-time OAuth for Drive account 2. Run from the project root."""
from google_auth_oauthlib.flow import InstalledAppFlow
import config

SCOPES = ["https://www.googleapis.com/auth/drive"]
flow   = InstalledAppFlow.from_client_secrets_file(config.DRIVE_CLIENT_SECRETS, SCOPES)
creds  = flow.run_local_server(port=8081, open_browser=False)

with open(config.DRIVE_ACCOUNTS[1]["token_file"], "w") as f:
    f.write(creds.to_json())
print("Drive account 2 authorised →", config.DRIVE_ACCOUNTS[1]["token_file"])
