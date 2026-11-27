"""اختبار SILMA TTS (Apache 2.0) بصوتك المرجعي. مجاني، محلي بالكامل، لا يرفع شيئاً لأي خدمة.
التسجيل المرجعي يبقى في assets/voice_ref/ (مستثنى من git) ولا يُستعمل إلا لهذا المشروع.

الاستعمال (من جذر المشروع):
  python scripts/phase1/silma_test.py --ref assets/voice_ref/ref.wav --ref-text "النص الذي قلته حرفياً" [--only hook] [--device cuda]
المرجع: 5–10 ثوانٍ، صوتك وحدك، بلا موسيقى أو ضجيج، وبلهجتك العراقية الطبيعية.
"""
import argparse, json, sys, time, wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from voice_test import SAMPLES, OUT

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True); ap.add_argument("--ref-text", required=True)
    ap.add_argument("--device", default=None, help="cuda أو cpu (الافتراضي: تلقائي)")
    ap.add_argument("--only", choices=list(SAMPLES), default=None)
    ap.add_argument("--nfe", type=int, default=32, help="خطوات التوليد: أعلى = أجود وأبطأ (32 = إعداد D المعتمد مؤقتاً)")
    a = ap.parse_args()
    import torch
    # 1) بديل nemo_text_processing (pynini لا تُبنى على ويندوز)
    shim = str(Path(__file__).parent / "shims")
    if shim not in sys.path: sys.path.insert(0, shim)
    # 2) قراءة الصوت عبر soundfile بدل torchcodec (يتطلب DLLs لـ ffmpeg على ويندوز)
    import soundfile as sf, torchaudio
    def _load(path, *args, **kw):
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        return torch.from_numpy(data.T.copy()), sr
    torchaudio.load = _load
    dev = a.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print("الجهاز:", dev, torch.cuda.get_device_name(0) if dev == "cuda" else "")
    from silma_tts.api import SilmaTTS
    t0 = time.time(); m = SilmaTTS(device=dev, enable_normalizer=False); load = time.time() - t0
    OUT.mkdir(parents=True, exist_ok=True); rows = []
    for name, (_, spoken) in SAMPLES.items():
        if a.only and name != a.only: continue
        # لا نحوّل الأسماء الإنجليزية إلى عربية هنا: النموذج ثنائي اللغة. نستعمل النص كما يظهر في الترجمة
        text = SAMPLES[name][0]
        out = OUT / f"silma_{name}.wav"; t0 = time.time()
        m.infer(ref_file=a.ref, ref_text=a.ref_text, gen_text=text, file_wave=str(out), seed=1, nfe_step=a.nfe, normalize_numbers=False, force_tashkeel=False)
        dt = time.time() - t0
        with wave.open(str(out)) as w: d = w.getnframes() / w.getframerate()
        rows.append(dict(sample=name, file=out.name, audio_sec=round(d, 1), gen_sec=round(dt, 1), rtf=round(dt / d, 2)))
        print(rows[-1])
    peak = torch.cuda.max_memory_allocated() / 2**30 if dev == "cuda" else None
    summary = dict(device=dev, load_sec=round(load, 1), peak_vram_gb=peak and round(peak, 2), nfe=a.nfe, samples=rows)
    (OUT / "silma_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nاستمع إلى الملفات في", OUT, "\n", json.dumps(summary, ensure_ascii=False))

if __name__ == "__main__":
    main()
