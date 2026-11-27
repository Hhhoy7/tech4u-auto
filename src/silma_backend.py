"""صوت محلي مجاني: SILMA TTS (Apache-2.0) باستنساخ صوتك من assets/voice_ref/ref.wav،
وتوقيت الكلمات من faster-whisper (للترجمة المتزامنة). لا يتصل بأي خدمة بعد تنزيل النماذج."""
import os, re, subprocess, sys
from pathlib import Path
from common import ROOT, run

_model = None
_whisper = None

def _prepare_runtime():
    shim = str(ROOT / "scripts" / "phase1" / "shims")      # بديل nemo_text_processing (pynini لا تُبنى على ويندوز)
    if shim not in sys.path: sys.path.insert(0, shim)
    import torch, torchaudio, soundfile as sf
    def _load(path, *a, **k):                                # بدل torchcodec (يتطلب DLLs لـ ffmpeg على ويندوز)
        d, sr = sf.read(str(path), dtype="float32", always_2d=True)
        return torch.from_numpy(d.T.copy()), sr
    torchaudio.load = _load
    return torch

def _tts(cfg):
    global _model
    if _model is None:
        torch = _prepare_runtime()
        from silma_tts.api import SilmaTTS
        dev = cfg["voice"]["local"].get("device") or ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"  تحميل SILMA على {dev} ...")
        _model = SilmaTTS(device=dev, enable_normalizer=False)
    return _model

def _aligner(cfg):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        a = cfg["voice"]["local"].get("align", {})
        _whisper = WhisperModel(a.get("model", "small"), device=a.get("device", "cpu"),
                                compute_type=a.get("compute_type", "int8"))
    return _whisper

def spread_words(words, t0, t1):
    """يوزّع الزمن [t0,t1] على كلمات النص الأصلي بنسبة طول كل كلمة (يتحمل أخطاء ASR)."""
    total = sum(len(w) + 1 for w in words) or 1
    out, t = [], t0
    for w in words:
        d = (t1 - t0) * (len(w) + 1) / total
        out.append((w, t, t + d)); t += d
    return out

def align_words(wav, text, cfg):
    segs, _ = _aligner(cfg).transcribe(str(wav), language="ar", word_timestamps=True)
    heard = [w for s in segs for w in (s.words or [])]
    orig = text.split()
    if not heard:
        return None
    if len(heard) == len(orig):                               # تطابق العدد: نستعمل توقيت Whisper مباشرة
        return [(o, h.start, h.end) for o, h in zip(orig, heard)]
    return spread_words(orig, heard[0].start, heard[-1].end)   # غير ذلك: توزيع نسبي بين أول وآخر كلمة

def synth(text, out_mp3, cfg):
    """يعيد [(كلمة، بداية، نهاية)] ويكتب out_mp3."""
    L = cfg["voice"]["local"]
    ref, ref_txt = ROOT / L["ref_audio"], ROOT / L["ref_text_file"]
    if not ref.exists() or not ref_txt.exists():
        raise SystemExit(f"التسجيل المرجعي غير موجود: {ref} و{ref_txt} (شاهد docs/DESIGN.md)")
    wav = Path(out_mp3).with_suffix(".wav")
    _tts(cfg).infer(ref_file=str(ref), ref_text=ref_txt.read_text(encoding="utf-8").strip(), gen_text=text,
                    file_wave=str(wav), seed=L.get("seed", 1), nfe_step=int(os.environ.get("TECH4U_NFE") or L.get("nfe_step", 32)),
                    normalize_numbers=False, force_tashkeel=L.get("force_tashkeel", False))
    words = align_words(wav, text, cfg)
    if words is None:                                          # صمت أو فشل Whisper: توزيع على كامل المدة
        from common import duration
        words = spread_words(text.split(), 0.0, duration(wav))
    run(["ffmpeg", "-y", "-i", str(wav), "-ar", "44100", "-b:a", "192k", str(out_mp3)])
    return words
