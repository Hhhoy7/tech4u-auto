"""تعليق صوتي عبر ElevenLabs مع توقيت كل كلمة (للترجمة المتزامنة)."""
import base64, requests, subprocess
from common import env, run

def synth(text, out_mp3, cfg, dry_run=False):
    """يعيد قائمة (كلمة، بداية، نهاية) بالثواني."""
    words_txt = text.split()
    if dry_run:
        dur = max(2.0, len(words_txt) / 2.6)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", f"{dur:.2f}", "-q:a", "9", str(out_mp3)])
        step = dur / len(words_txt)
        return [(w, i * step, (i + 1) * step) for i, w in enumerate(words_txt)]

    v = cfg["voice"]
    if v.get("provider") == "local":
        import silma_backend
        return silma_backend.synth(text, out_mp3, cfg)
    if v.get("provider") != "elevenlabs":
        raise SystemExit("voice.provider يجب أن يكون local أو elevenlabs")
    voice_id = v["voice_id"] or env("ELEVENLABS_VOICE_ID")
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": env("ELEVENLABS_API_KEY")},
        json={"text": text, "model_id": v["model_id"],
              "voice_settings": {"stability": v["stability"],
                                 "similarity_boost": v["similarity_boost"],
                                 "style": v["style"], "use_speaker_boost": True}},
        timeout=300)
    r.raise_for_status()
    d = r.json()
    out_mp3.write_bytes(base64.b64decode(d["audio_base64"]))
    al = d["alignment"]
    chars, st, en = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words, cur, s, e = [], "", None, None
    for ch, a, b in zip(chars, st, en):
        if ch.isspace():
            if cur:
                words.append((cur, s, e)); cur, s = "", None
            continue
        if s is None: s = a
        cur += ch; e = b
    if cur: words.append((cur, s, e))
    return words
