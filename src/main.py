"""خط الإنتاج: موضوع ← سيناريو ← صوت ← مشاهد ← مونتاج ← صورة مصغرة ← رفع."""
import argparse, datetime, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, load_config, read_json, write_json, run
import script_gen, tts, visuals, subtitles, render, textimg, db, telegram_api

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="بدون مفاتيح: سيناريو تجريبي وصوت صامت ولا رفع")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--sample", action="store_true", help="سيناريو العينة بلا Claude، مع صوت حقيقي وبوابة المراجعة")
    ap.add_argument("--upload-now", action="store_true", help="رفع فوري بلا مراجعة؛ يتطلب publish_enabled=true")
    ap.add_argument("--topic")
    ap.add_argument("--privacy", choices=["private", "public", "scheduled"])
    a = ap.parse_args()
    cfg = load_config()
    _env = ROOT / ".env"
    if _env.exists():                                            # يحمّل أسرار .env المحلية دون طباعتها
        import os
        for _l in _env.read_text(encoding="utf-8").splitlines():
            if "=" in _l and not _l.lstrip().startswith("#"):
                _k, _v = _l.split("=", 1); os.environ.setdefault(_k.strip(), _v.split("#")[0].strip())
    con = db.connect(); db.import_published(con=con)
    if db.flag("paused", con): print("الإنتاج موقوف (paused). /resume في Telegram أو db.set_setting."); return
    if a.privacy: cfg["publish"]["privacy"] = a.privacy

    topics = read_json(ROOT / "topics.json", {"queue": [], "niche": ""})
    state = read_json(ROOT / "state" / "published.json", {"videos": []})
    history = [v["topic"] for v in state["videos"]] + [r["topic"] for r in con.execute("SELECT topic FROM videos WHERE topic IS NOT NULL")]

    stamp = datetime.date.today().isoformat()
    work = ROOT / "output" / stamp
    if work.exists(): shutil.rmtree(work)
    (work / "scenes").mkdir(parents=True)

    # 1) السيناريو
    from_queue = False
    if a.dry_run or a.sample:
        meta = read_json(ROOT / "samples" / "sample_script.json", None); topic = "dry-run" if a.dry_run else "sample"
    else:
        topic, from_queue = (a.topic, False) if a.topic else script_gen.next_topic(topics, history)
        print(f"الموضوع: {topic}")
        meta = script_gen.generate(topic, cfg, history)
    write_json(work / "script.json", meta)
    print(f"السيناريو: {meta['title']} ({len(meta['scenes'])} مشهد)")

    # 2) صوت + مشاهد
    scene_files, chunks, offset, used, chapters = [], [], 0.0, set(), []
    first_visual = None
    for i, sc in enumerate(meta["scenes"], 1):
        print(f"مشهد {i}/{len(meta['scenes'])}")
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

    # 3) ترجمة + دمج
    ass, srt = work / "subs.ass", work / "subs.srt"
    subtitles.build(chunks, ass, srt, cfg["video"]["width"], cfg["video"]["height"])
    final = work / "video.mp4"
    render.final(scene_files, ass, final, cfg, work)
    print(f"تم التصدير: {final} ({offset / 60:.1f} دقيقة)")

    # 4) صورة مصغرة
    bg = first_visual
    if bg and str(bg).endswith(".mp4"):
        bg_png = work / "bg.jpg"
        run(["ffmpeg", "-y", "-ss", "2", "-i", str(bg), "-frames:v", "1", str(bg_png)]); bg = bg_png
    thumb = work / "thumbnail.jpg"
    textimg.thumbnail(meta["thumbnail_text"], bg, thumb)

    # 5) وصف مع الفصول
    desc = meta["description"]
    if len(chapters) >= 3:
        def ts(s): return f"{int(s // 60):02d}:{int(s % 60):02d}"
        chapters[0] = (0, chapters[0][1])
        desc += "\n\nالفصول:\n" + "\n".join(f"{ts(t)} {n}" for t, n in chapters)
    desc += "\n\nلقطات الفيديو: Pixabay (pixabay.com)"
    meta["description"] = desc

    if a.dry_run or a.no_upload:
        print("لا رفع (dry-run/no-upload). راجع مجلد", work); return

    # 6) بوابة المراجعة: لا رفع قبل موافقتك (Telegram) إلا بـ --upload-now مع publish_enabled
    import time as _t, subprocess as _sp, json as _j
    write_json(work / "upload_meta.json", meta)
    preview = work / "preview480.mp4"
    run(["ffmpeg", "-y", "-i", str(final), "-vf", "scale=-2:480", "-c:v", "libx264", "-crf", "30", "-preset", "fast",
         "-c:a", "aac", "-b:a", "96k", str(preview)])
    cur = con.execute("INSERT INTO videos(topic,title,stage,workdir,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                      (topic, meta["title"], "review", str(work), _t.time(), _t.time()))
    vid = cur.lastrowid
    if from_queue:
        topics["queue"].pop(0); write_json(ROOT / "topics.json", topics)
    db.log("render", f"جاهز للمراجعة #{vid}: {meta['title']}", vid, con)
    if a.upload_now and db.flag("publish_enabled", con):
        import publish; print("✅ https://youtu.be/" + publish.upload_approved(vid, con)); return
    sent = telegram_api.send_review(vid, meta["title"], meta["description"], thumb, preview, con)
    print(f"جاهز للمراجعة #{vid}: {work}\n" + ("أُرسل إلى Telegram." if sent else
          "لم يُرسل (Telegram غير مضبوط بعد). راجع الملفات ثم شغّل البوت."))

if __name__ == "__main__":
    main()
