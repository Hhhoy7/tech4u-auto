"""رفع الفيديو والصورة المصغرة عبر YouTube Data API v3."""
import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from common import env

def _service():
    creds = Credentials(None, refresh_token=env("YT_REFRESH_TOKEN"),
                        client_id=env("YT_CLIENT_ID"), client_secret=env("YT_CLIENT_SECRET"),
                        token_uri="https://oauth2.googleapis.com/token",
                        scopes=["https://www.googleapis.com/auth/youtube.upload",
                                "https://www.googleapis.com/auth/youtube"])
    return build("youtube", "v3", credentials=creds)

def upload(video, thumb, meta, cfg):
    p = cfg["publish"]
    status = {"selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": bool(p["contains_synthetic_media"])}
    if p["privacy"] == "scheduled":
        t = datetime.datetime.now(datetime.timezone.utc).replace(hour=p["publish_hour_utc"], minute=0, second=0, microsecond=0)
        if t <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15):
            t += datetime.timedelta(days=1)
        status.update(privacyStatus="private", publishAt=t.strftime("%Y-%m-%dT%H:%M:%SZ"))
    else:
        status["privacyStatus"] = p["privacy"]
    body = {"snippet": {"title": meta["title"][:100], "description": meta["description"][:4900],
                        "tags": (meta["tags"] + p["default_tags"])[:30],
                        "categoryId": cfg["channel"]["category_id"],
                        "defaultLanguage": cfg["channel"]["language"],
                        "defaultAudioLanguage": cfg["channel"]["language"]},
            "status": status}
    yt = _service()
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 << 20, resumable=True))
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st: print(f"  رفع {int(st.progress() * 100)}%")
    vid = resp["id"]
    try:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
    except Exception as e:
        print(f"  ! تعذر ضبط الصورة المصغرة (يتطلب تفعيل الحساب): {e}")
    return vid
