"""One-time OAuth for YouTube uploads. Run from the project root."""
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import config

SCOPES = ["https://www.googleapis.com/auth/youtube"]
flow   = InstalledAppFlow.from_client_secrets_file(config.YOUTUBE_CLIENT_SECRETS, SCOPES)
creds  = flow.run_local_server(port=8082, open_browser=False)

with open(config.YOUTUBE_TOKEN, "w") as f:
    f.write(creds.to_json())
print("YouTube authorised →", config.YOUTUBE_TOKEN)

youtube = build("youtube", "v3", credentials=creds)
channel = youtube.channels().list(part="snippet", mine=True).execute()
email = channel["items"][0]["snippet"].get("customUrl", "")
# The API doesn't expose the Gmail address directly; use the token's id_token hint if available
# Fall back to checking via oauth2 userinfo
import google.auth.transport.requests, requests as _req
authed = _req.get(
    "https://www.googleapis.com/oauth2/v3/userinfo",
    headers={"Authorization": f"Bearer {creds.token}"},
).json().get("email", "")

if authed:
    if authed.lower() == config.YOUTUBE_ACCOUNT.lower():
        print(f"Account verified: {authed}")
    else:
        print(f"WARNING: authenticated as {authed!r} but expected {config.YOUTUBE_ACCOUNT!r}")
else:
    print("WARNING: could not verify authenticated account email")
