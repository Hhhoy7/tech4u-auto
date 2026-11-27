"""بوت المراجعة: python src/telegram_bot.py   (يعمل في الخلفية؛ إيقاف: Ctrl+C أو /pause)
الأوامر: /start (ربط محادثتك) /status /pause /resume /publish_on /publish_off
الأزرار تحت المعاينة: موافقة (رفع خاص) أو رفض."""
import time, traceback
import db, telegram_api as tg, budget

def handle(upd, con):
    if "callback_query" in upd:
        cq = upd["callback_query"]; cid = str(cq["message"]["chat"]["id"])
        if cid != tg.chat_id(con): return
        act, vid = cq["data"].split(":"); vid = int(vid)
        tg.api("answerCallbackQuery", callback_query_id=cq["id"])
        if act == "no":
            con.execute("UPDATE videos SET stage='rejected' WHERE id=?", (vid,)); tg.notify(f"❌ رُفض #{vid}", con); return
        tg.notify(f"⏳ جاري رفع #{vid} ...", con)
        try:
            import publish; yt = publish.upload_approved(vid, con)
            tg.notify(f"✅ رُفع خاصاً: https://youtu.be/{yt}\nانشره من YouTube Studio عندما ترضى.", con)
        except Exception as e:
            db.log_error("publish", e, vid, con); tg.notify(f"⚠️ فشل الرفع #{vid}: {str(e)[:300]}", con)
        return
    m = upd.get("message") or {}; text = (m.get("text") or "").strip(); cid = str(m.get("chat", {}).get("id", ""))
    if text == "/start":
        if not tg.chat_id(con): db.set_setting("telegram_chat_id", cid, con)       # الربط عند أول /start
        if cid == tg.chat_id(con): tg.api("sendMessage", chat_id=cid, text="تم الربط ✅ سأرسل لك الفيديوهات للمراجعة هنا.")
        return
    if cid != tg.chat_id(con): return                                               # لا يُنفَّذ شيء من غير محادثتك
    if text == "/status":
        s = budget.status(con); n = con.execute("SELECT stage, COUNT(*) c FROM videos GROUP BY stage").fetchall()
        tg.notify(f"الإنتاج متوقف: {db.flag('paused', con)} | النشر العام: {db.flag('publish_enabled', con)}\n"
                  f"Claude: مفعّل={s['enabled']} صُرف {s['spent_usd']}$ من {s['hard_cap_usd']}$\n"
                  + ", ".join(f"{r['stage']}={r['c']}" for r in n), con)
    elif text in ("/pause", "/resume"):
        db.set_setting("paused", "true" if text == "/pause" else "false", con); tg.notify("تم: " + text, con)
    elif text in ("/publish_on", "/publish_off"):
        db.set_setting("publish_enabled", "true" if text == "/publish_on" else "false", con); tg.notify("تم: " + text, con)

def main():
    if not tg.configured(): raise SystemExit("ضع TELEGRAM_BOT_TOKEN في ملف .env")
    con = db.connect(); off = None; print("البوت يعمل (Ctrl+C للإيقاف)")
    while True:
        try:
            for u in tg.api("getUpdates", timeout=70, offset=off, **{"timeout": 50}):
                off = u["update_id"] + 1; handle(u, con)
        except KeyboardInterrupt: break
        except Exception as e:
            print("خطأ:", e); traceback.print_exc(limit=1); time.sleep(5)

if __name__ == "__main__":
    import os; from pathlib import Path
    envf = Path(__file__).resolve().parent.parent / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.split("#")[0].strip())
    main()
