"""One-time OAuth for YouTube uploads. Run from the project root."""
from google_auth_oauthlib.flow import InstalledAppFlow
import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
flow   = InstalledAppFlow.from_client_secrets_file(config.YOUTUBE_CLIENT_SECRETS, SCOPES)
creds  = flow.run_local_server(port=8082, open_browser=False)

with open(config.YOUTUBE_TOKEN, "w") as f:
    f.write(creds.to_json())
print("YouTube authorised →", config.YOUTUBE_TOKEN)
