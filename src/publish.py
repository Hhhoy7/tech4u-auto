"""الرفع بعد موافقتك فقط. يُرفع خاصاً ما لم تفعّل publish_enabled (النشر العام/المجدول مغلق افتراضياً)."""
import time
from pathlib import Path
from common import ROOT, load_config, read_json, write_json
import db

def upload_approved(video_id, con=None):
    con = con or db.connect()
    row = con.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    if not row: raise RuntimeError(f"الفيديو {video_id} غير موجود")
    if row["stage"] not in ("review", "approved"):
        raise RuntimeError(f"حالة الفيديو {row['stage']} لا تسمح بالرفع")
    work = Path(row["workdir"]); meta = read_json(work / "upload_meta.json", None)
    cfg = load_config()
    if not db.flag("publish_enabled", con):
        cfg["publish"]["privacy"] = "private"        # بلا موافقة نشر عام: خاص دائماً
    db.log("publish", f"رفع #{video_id} بخصوصية {cfg['publish']['privacy']}", video_id, con)
    import upload
    yt = upload.upload(work / "video.mp4", work / "thumbnail.jpg", meta, cfg)
    con.execute("UPDATE videos SET stage='uploaded', youtube_id=?, updated_at=? WHERE id=?", (yt, time.time(), video_id))
    con.execute("INSERT INTO publish_log(ts,video_id,youtube_id,privacy,note) VALUES(?,?,?,?,?)",
                (time.time(), video_id, yt, cfg["publish"]["privacy"], "approved via telegram"))
    state = read_json(ROOT / "state" / "published.json", {"videos": []})
    state["videos"].append({"date": time.strftime("%Y-%m-%d"), "topic": row["topic"], "title": row["title"], "id": yt})
    write_json(ROOT / "state" / "published.json", state)
    return yt
