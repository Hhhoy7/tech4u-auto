"""تشغيل مرة واحدة على جهازك: يفتح المتصفح لموافقتك ثم يكتب YT_* في ملف .env مباشرة (لا يطبع الأسرار).
python scripts/auth_youtube.py client_secret.json
قبل ذلك: فعّل YouTube Data API v3 وYouTube Analytics API، واجعل تطبيق OAuth In production (وإلا ينتهي التوكن بعد 7 أيام).
"""
import re, sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
SC = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube",
      "https://www.googleapis.com/auth/yt-analytics.readonly"]
c = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SC).run_local_server(port=0, access_type="offline", prompt="consent")
env = Path(__file__).resolve().parent.parent / ".env"
txt = env.read_text(encoding="utf-8") if env.exists() else ""
for k, v in (("YT_CLIENT_ID", c.client_id), ("YT_CLIENT_SECRET", c.client_secret), ("YT_REFRESH_TOKEN", c.refresh_token)):
    txt = re.sub(rf"(?m)^{k}=.*\n?", "", txt) + f"{k}={v}\n"
env.write_text(txt, encoding="utf-8"); print("تم حفظ توكن يوتيوب في .env (لم يُطبع).")
