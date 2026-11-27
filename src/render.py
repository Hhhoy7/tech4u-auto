"""تركيب الفيديو بـ ffmpeg: مشهد لكل مقطع صوتي ثم دمج + ترجمة + موسيقى."""
from pathlib import Path
from common import ROOT, run, duration

def scene_clip(visual, audio, lower_png, out, cfg, pad=0.5):
    W, H, FPS = cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"]
    dur = duration(audio) + pad
    frames = int(dur * FPS)
    fade = f"fade=t=in:st=0:d=0.35,fade=t=out:st={dur - 0.35:.2f}:d=0.35"
    if str(visual).lower().endswith((".mp4", ".mov")):
        inp = ["-stream_loop", "-1", "-i", str(visual)]
        base = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},eq=brightness=-0.06:saturation=1.1"
    else:
        inp = ["-loop", "1", "-i", str(visual)]
        base = (f"scale=2880:-1,zoompan=z='min(zoom+0.0007,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={frames}:s={W}x{H}:fps={FPS}")
    cmd = ["ffmpeg", "-y", *inp, "-i", str(audio)]
    if lower_png:
        cmd += ["-loop", "1", "-i", str(lower_png)]
        fc = (f"[0:v]{base},format=yuv420p[b];[2:v]format=rgba,fade=t=in:st=0.4:d=0.4:alpha=1,"
              f"fade=t=out:st=4.2:d=0.4:alpha=1[o];[b][o]overlay=0:0:shortest=0,{fade}[v];"
              f"[1:a]apad=pad_dur=0.5,aresample=48000[a]")
    else:
        fc = f"[0:v]{base},{fade},format=yuv420p[v];[1:a]apad=pad_dur=0.5,aresample=48000[a]"
    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out)]
    run(cmd)
    return dur

def final(scene_files, ass, out, cfg, workdir):
    lst = workdir / "list.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in scene_files))
    joined = workdir / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    fonts = ROOT / "fonts"
    vf = f"ass={ass.resolve()}:fontsdir={fonts.resolve()}"
    music = cfg["visuals"].get("music_file")
    cmd = ["ffmpeg", "-y", "-i", str(joined)]
    if music and (ROOT / music).exists():
        cmd += ["-stream_loop", "-1", "-i", str(ROOT / music),
                "-filter_complex",
                f"[0:v]{vf}[v];[1:a]volume={cfg['visuals']['music_volume']}[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", vf]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(cfg["video"]["fps"]),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)]
    run(cmd)
