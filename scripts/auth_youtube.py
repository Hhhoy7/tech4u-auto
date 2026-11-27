"""تشغيل مرة واحدة على جهازك للحصول على YT_REFRESH_TOKEN.
python scripts/auth_youtube.py client_secret.json
"""
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file(
    sys.argv[1], ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"])
c = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("\nYT_CLIENT_ID     =", c.client_id)
print("YT_CLIENT_SECRET =", c.client_secret)
print("YT_REFRESH_TOKEN =", c.refresh_token)
