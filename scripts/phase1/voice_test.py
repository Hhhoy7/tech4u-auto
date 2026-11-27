"""المرحلة 1 — اختبار الصوت العربي وWhisper. مجاني 100% ولا يستهلك رصيد Claude.
الاستعمال:  python voice_test.py [--whisper small|medium] [--device cpu|cuda] [--with-edge]
الناتج: output/voice_test/report.html (افتحه واستمع لكل عينة وقيّمها) + report.json
"""
import argparse, json, re, subprocess, sys, time, urllib.request, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "voice_test"
MODELS = ROOT / "state" / "models"
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/{q}/ar_JO-kareem-{q}.onnx"

# نص العرض (كما يظهر في الترجمة) ونص النطق (أسماء إنجليزية مكتوبة بحروف عربية لتحسين النطق)
SAMPLES = {
  "hook": ("ماذا لو كان هناك مساعد لا ينام، يكتب ويبحث ويصمم نيابةً عنك؟",
           "ماذا لو كان هناك مساعد لا ينام، يكتب ويبحث ويصمم نيابةً عنك؟"),
  "names": ("الأداة الأولى هي ChatGPT، والثانية Claude، والثالثة Perplexity.",
            "الأداة الأولى هي تشات جي بي تي، والثانية كلود، والثالثة بيربلكسيتي."),
  "para": ("الذكاء الاصطناعي لا يعني أن تتوقف عن التفكير. هو أداة تسرّع العمل الروتيني، وتترك لك القرار والإبداع. "
           "جرّب أن تبدأ بمهمة صغيرة، ثم قارن الوقت الذي وفّرته.",
           "الذكاء الاصطناعي لا يعني أن تتوقف عن التفكير. هو أداة تسرّع العمل الروتيني، وتترك لك القرار والإبداع. "
           "جرّب أن تبدأ بمهمة صغيرة، ثم قارن الوقت الذي وفّرته."),
}

def norm(s):
    s = re.sub(r"[ً-ْـ]", "", s); s = re.sub(r"[إأآ]", "ا", s)
    s = s.replace("ى", "ي").replace("ة", "ه"); s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.lower().split())

def dur(p):
    with wave.open(str(p)) as w: return w.getnframes() / w.getframerate()

def fetch_piper(q):
    MODELS.mkdir(parents=True, exist_ok=True)
    f = MODELS / f"ar_JO-kareem-{q}.onnx"
    for suffix in ("", ".json"):
        t = Path(str(f) + suffix)
        if not t.exists():
            print(f"تنزيل {t.name} ..."); urllib.request.urlretrieve(HF.format(q=q) + suffix, t)
    return f

def synth_piper(q, text, out):
    t0 = time.time()
    subprocess.run([sys.executable, "-m", "piper", "-m", str(fetch_piper(q)), "-f", str(out)],
                   input=text.encode("utf-8"), check=True, capture_output=True)
    return time.time() - t0

def synth_edge(text, out):
    import asyncio, edge_tts
    mp3 = out.with_suffix(".mp3"); t0 = time.time()
    asyncio.run(edge_tts.Communicate(text, "ar-SA-HamedNeural").save(str(mp3)))
    subprocess.run(["ffmpeg", "-y", "-i", str(mp3), "-ar", "22050", "-ac", "1", str(out)], check=True, capture_output=True)
    return time.time() - t0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--whisper", default="small"); ap.add_argument("--device", default="cpu")
    ap.add_argument("--with-edge", action="store_true", help="للمقارنة فقط؛ خدمة غير رسمية وترخيصها غير واضح للمحتوى المُربح")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    from faster_whisper import WhisperModel
    import jiwer
    ctype = "int8_float16" if a.device == "cuda" else "int8"
    try:
        wm = WhisperModel(a.whisper, device=a.device, compute_type=ctype)
    except Exception as e:
        print("تعذر GPU:", e, "← استعمال CPU"); wm = WhisperModel(a.whisper, device="cpu", compute_type="int8"); a.device = "cpu"

    voices = {"piper-kareem-medium": lambda t, o: synth_piper("medium", t, o),
              "piper-kareem-low": lambda t, o: synth_piper("low", t, o)}
    if a.with_edge:
        try: import edge_tts  # noqa
        except ImportError: print("edge-tts غير مثبّت (pip install edge-tts) — تخطّي")
        else: voices["edge-ar-SA-Hamed (مقارنة فقط)"] = synth_edge

    rows = []
    for vname, fn in voices.items():
        for sname, (shown, spoken) in SAMPLES.items():
            wav = OUT / f"{vname.split(' ')[0]}_{sname}.wav"
            try: gen = fn(spoken, wav)
            except Exception as e:
                rows.append(dict(voice=vname, sample=sname, error=str(e)[:200])); continue
            t0 = time.time(); segs, _ = wm.transcribe(str(wav), language="ar", word_timestamps=True); segs = list(segs)
            asr = time.time() - t0
            hyp = " ".join(s.text for s in segs); nwords = sum(len(s.words or []) for s in segs)
            rows.append(dict(voice=vname, sample=sname, file=wav.name, audio_sec=round(dur(wav), 1),
                             synth_sec=round(gen, 1), whisper_sec=round(asr, 1), words_timed=nwords,
                             wer=round(jiwer.wer(norm(spoken), norm(hyp)), 3), heard=hyp.strip()))
            print(rows[-1])
    (OUT / "report.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    html = ["<meta charset=utf-8><body dir=rtl style='font-family:Tahoma;max-width:900px;margin:2em auto'>",
            f"<h2>اختبار الأصوات — Whisper {a.whisper} على {a.device}</h2>",
            "<p>WER أقل = أوضح للآلة (مؤشر مساعد فقط). <b>الحكم النهائي بأذنك</b>: لهجة، طبيعية، نطق الأسماء.</p>"]
    for r in rows:
        if "error" in r: html.append(f"<p>❌ {r['voice']} / {r['sample']}: {r['error']}</p>"); continue
        html.append(f"<hr><h4>{r['voice']} — {r['sample']}</h4><audio controls src='{r['file']}'></audio>"
                    f"<p>مدة {r['audio_sec']}ث · توليد {r['synth_sec']}ث · Whisper {r['whisper_sec']}ث · "
                    f"WER {r['wer']}<br>سمعها Whisper: {r['heard']}</p>")
    (OUT / "report.html").write_text("\n".join(html), encoding="utf-8")
    print("\nافتح:", OUT / "report.html")

if __name__ == "__main__":
    main()
