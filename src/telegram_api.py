"""Telegram بسيط عبر requests (مجاني). الاستطلاع (long-polling) لا Webhook، فلا حاجة لإنترنت عام."""
import os, requests
import db

def token(): return os.environ.get("TELEGRAM_BOT_TOKEN", "")
def configured(): return bool(token())

def api(method, files=None, timeout=60, **data):
    r = requests.post(f"https://api.telegram.org/bot{token()}/{method}", data=data, files=files, timeout=timeout)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"Telegram {method}: {j.get('description')}")
    return j["result"]

def chat_id(con=None):
    return db.get_setting("telegram_chat_id", con) or os.environ.get("TELEGRAM_CHAT_ID", "") or None

def notify(text, con=None):
    cid = chat_id(con)
    if not (configured() and cid): return False
    api("sendMessage", chat_id=cid, text=text[:4000]); return True

def send_review(video_id, title, desc, thumb, preview, con=None):
    """يرسل صورة + عنوان + معاينة 480p مع أزرار. حد رفع البوت 50MB."""
    import json
    cid = chat_id(con)
    if not (configured() and cid): return False
    kb = json.dumps({"inline_keyboard": [[{"text": "✅ موافقة ورفع (خاص)", "callback_data": f"ok:{video_id}"},
                                         {"text": "❌ رفض", "callback_data": f"no:{video_id}"}]]})
    with open(thumb, "rb") as f:
        api("sendPhoto", files={"photo": f}, chat_id=cid, caption=f"🎬 #{video_id}\n{title}\n\n{desc[:600]}")
    if os.path.getsize(preview) <= 49 * 2**20:
        with open(preview, "rb") as f:
            api("sendVideo", files={"video": f}, timeout=600, chat_id=cid, supports_streaming="true",
                caption=f"معاينة 480p للفيديو #{video_id}", reply_markup=kb)
    else:
        api("sendMessage", chat_id=cid, text=f"المعاينة أكبر من 50MB؛ افتحها من مجلد الإخراج.", reply_markup=kb)
    return True
