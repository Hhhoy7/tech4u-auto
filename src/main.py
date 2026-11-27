"""خط الإنتاج على مرحلتين:
 1) python src/main.py            ← سيناريو + إنشاء فيديو (#id) جاهز للتسجيل بصوتك
 2) python src/recorder.py        ← تسجّل المشاهد من صفحة محلية، ثم "إنتاج" يشغّل: python src/main.py --render ID
 3) بعد المونتاج: معاينة على Telegram ← موافقتك ← رفع (خاص).
أوضاع الاختبار: --dry-run (صوت صامت، بلا DB) و--sample (سيناريو العينة بلا Claude)."""
import argparse, os, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, load_config, read_json, write_json, run
import script_gen, tts, visuals, subtitles, render, textimg, db, telegram_api

def load_env():
    env = ROOT / ".env"
    if env.exists():                                             # أسرار .env المحلية، لا تُطبع
        for l in env.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.split("=", 1); os.environ.setdefault(k.strip(), v.split("#")[0].strip())

def recorder_url(cfg, vid):
    return f"http://127.0.0.1:{cfg.get('recorder', {}).get('port', 8765)}/?v={vid}"

def prepare(a, cfg, con):
    """المرحلة 1: السيناريو وصف الفيديو في قاعدة البيانات (workdir خاص بكل فيديو، لا يُحذف أبداً)."""
    topics = read_json(ROOT / "topics.json", {"queue": [], "niche": ""})
    state = read_json(ROOT / "state" / "published.json", {"videos": []})
    history = [v["topic"] for v in state["videos"]] + [r["topic"] for r in con.execute("SELECT topic FROM videos WHERE topic IS NOT NULL")]
    from_queue = False
    if a.dry_run or a.sample:
        meta = read_json(ROOT / "samples" / "sample_script.json", None); topic = "dry-run" if a.dry_run else "sample"
    else:
        topic, from_queue = (a.topic, False) if a.topic else script_gen.next_topic(topics, history)
        print(f"الموضوع: {topic}")
        meta = script_gen.generate(topic, cfg, history)
    if a.dry_run:
        vid, work = None, ROOT / "output" / "dryrun"
        if work.exists(): shutil.rmtree(work)
    else:
        now = time.time()
        vid = con.execute("INSERT INTO videos(topic,title,stage,created_at,updated_at) VALUES(?,?,?,?,?)",
                          (topic, meta["title"], "scripted", now, now)).lastrowid
        work = ROOT / "output" / f"v{vid}"
        con.execute("UPDATE videos SET workdir=? WHERE id=?", (str(work), vid))
        if from_queue:
            topics["queue"].pop(0); write_json(ROOT / "topics.json", topics)
    (work / "scenes").mkdir(parents=True, exist_ok=True)
    write_json(work / "script.json", meta)
    print(f"السيناريو: {meta['title']} ({len(meta['scenes'])} مشهد) → {work}")
    return vid, work, meta

def render_video(vid, work, meta, a, cfg, con):
    """المرحلة 2: صوت (مسجَّل بصوتك أو غيره) + مشاهد + ترجمة + مونتاج + صورة مصغرة + مراجعة."""
    scenes = meta["scenes"]
    if cfg["voice"].get("provider") == "recorded" and not a.dry_run:
        missing = [i for i in range(1, len(scenes) + 1) if not (work / "scenes" / f"{i:02d}.mp3").exists()]
        if missing: raise SystemExit(f"مشاهد غير مسجّلة: {missing}. افتح {recorder_url(cfg, vid)}")
    if vid: con.execute("UPDATE videos SET stage='rendering', updated_at=? WHERE id=?", (time.time(), vid))
    scene_files, chunks, offset, used, chapters = [], [], 0.0, set(), []
    first_visual = None
    for i, sc in enumerate(scenes, 1):
        print(f"مشهد {i}/{len(scenes)}")
        mp3 = work / "scenes" / f"{i:02d}.mp3"
        words = tts.synth(sc["narration"], mp3, cfg, a.dry_run)
        chunks += subtitles.chunks(words, offset)
        if sc.get("chapter"): chapters.append((offset, sc["chapter"]))
        vis = None if a.dry_run else visuals.fetch_clip(sc.get("stock_query"), work, used)
        if vis is None:
            vis = work / "scenes" / f"{i:02d}_card.png"
            textimg.card(sc.get("on_screen_text") or sc["narration"].split("،")[0], vis)
        first_visual = first_visual or vis
        lower = None
        if sc.get("on_screen_text") and str(vis).endswith((".mp4", ".mov")):
            lower = work / "scenes" / f"{i:02d}_lt.png"; textimg.lower_third(sc["on_screen_text"], lower)
        out = work / "scenes" / f"{i:02d}.mp4"
        offset += render.scene_clip(vis, mp3, lower, out, cfg)
        scene_files.append(out)

    ass, srt = work / "subs.ass", work / "subs.srt"
    subtitles.build(chunks, ass, srt, cfg["video"]["width"], cfg["video"]["height"])
    final = work / "video.mp4"
    render.final(scene_files, ass, final, cfg, work)
    print(f"تم التصدير: {final} ({offset / 60:.1f} دقيقة)")

    bg = first_visual
    if bg and str(bg).endswith(".mp4"):
        bg_png = work / "bg.jpg"
        run(["ffmpeg", "-y", "-ss", "2", "-i", str(bg), "-frames:v", "1", str(bg_png)]); bg = bg_png
    thumb = work / "thumbnail.jpg"
    textimg.thumbnail(meta["thumbnail_text"], bg, thumb)

    desc = meta["description"]
    if len(chapters) >= 3:
        def ts(s): return f"{int(s // 60):02d}:{int(s % 60):02d}"
        chapters[0] = (0, chapters[0][1])
        desc += "\n\nالفصول:\n" + "\n".join(f"{ts(t)} {n}" for t, n in chapters)
    desc += "\n\nلقطات الفيديو: Pixabay (pixabay.com)"
    meta["description"] = desc

    if a.dry_run or a.no_upload:
        print("لا رفع (dry-run/no-upload). راجع مجلد", work); return
    # بوابة المراجعة: لا رفع قبل موافقتك (Telegram) إلا بـ --upload-now مع publish_enabled
    write_json(work / "upload_meta.json", meta)
    preview = work / "preview480.mp4"
    run(["ffmpeg", "-y", "-i", str(final), "-vf", "scale=-2:480", "-c:v", "libx264", "-crf", "30", "-preset", "fast",
         "-c:a", "aac", "-b:a", "96k", str(preview)])
    con.execute("UPDATE videos SET stage='review', title=?, updated_at=? WHERE id=?", (meta["title"], time.time(), vid))
    db.log("render", f"جاهز للمراجعة #{vid}: {meta['title']}", vid, con)
    if a.upload_now and db.flag("publish_enabled", con):
        import publish; print("✅ https://youtu.be/" + publish.upload_approved(vid, con)); return
    sent = telegram_api.send_review(vid, meta["title"], meta["description"], thumb, preview, con)
    print(f"جاهز للمراجعة #{vid}: {work}\n" + ("أُرسل إلى Telegram." if sent else
          "لم يُرسل (Telegram غير مضبوط بعد). راجع الملفات ثم شغّل البوت."))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="بدون مفاتيح: سيناريو تجريبي وصوت صامت ولا رفع")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--sample", action="store_true", help="سيناريو العينة بلا Claude")
    ap.add_argument("--upload-now", action="store_true", help="رفع فوري بلا مراجعة؛ يتطلب publish_enabled=true")
    ap.add_argument("--render", type=int, metavar="ID", help="مونتاج فيديو سُجّلت مشاهده")
    ap.add_argument("--topic")
    ap.add_argument("--privacy", choices=["private", "public", "scheduled"])
    a = ap.parse_args()
    load_env(); cfg = load_config()
    con = db.connect(); db.import_published(con=con)
    if db.flag("paused", con): print("الإنتاج موقوف (paused). /resume في Telegram."); return
    if a.privacy: cfg["publish"]["privacy"] = a.privacy
    try:
        if a.render:
            row = con.execute("SELECT * FROM videos WHERE id=?", (a.render,)).fetchone()
            if not row: raise SystemExit(f"الفيديو {a.render} غير موجود")
            work = Path(row["workdir"]); render_video(a.render, work, read_json(work / "script.json", None), a, cfg, con); return
        vid, work, meta = prepare(a, cfg, con)
        if cfg["voice"].get("provider") == "recorded" and not a.dry_run:
            url = recorder_url(cfg, vid)
            db.log("script", f"جاهز للتسجيل #{vid}", vid, con)
            telegram_api.notify(f"🎙️ جاهز للتسجيل #{vid}: {meta['title']}\nافتح على الكمبيوتر: {url}", con)
            print(f"جاهز للتسجيل بصوتك. شغّل: python src/recorder.py ثم افتح {url}")
            return
        render_video(vid, work, meta, a, cfg, con)
    except SystemExit: raise
    except Exception as e:
        db.log_error("pipeline", e, None, con); telegram_api.notify(f"⚠️ خطأ في الإنتاج: {str(e)[:300]}", con); raise

if __name__ == "__main__":
    main()
