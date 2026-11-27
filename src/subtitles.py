"""بناء ملف ASS (ترجمة عربية متزامنة) و SRT."""
def _t(s):
    h, rem = divmod(s, 3600); m, sec = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{sec:05.2f}"

def _srt(s):
    h, rem = divmod(s, 3600); m, sec = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(sec):02d},{int((sec % 1) * 1000):03d}"

def chunks(words, offset, max_words=6, max_chars=38):
    out, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x[0] for x in cur)
        end_punct = w[0][-1] in "،.؟!:؛,?"
        if len(cur) >= max_words or len(text) >= max_chars or end_punct:
            out.append((text, offset + cur[0][1], offset + cur[-1][2])); cur = []
    if cur:
        out.append((" ".join(x[0] for x in cur), offset + cur[0][1], offset + cur[-1][2]))
    return out

def build(all_chunks, ass_path, srt_path, w=1920, h=1080):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Tajawal,62,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,120,120,70,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    ev = [f"Dialogue: 0,{_t(a)},{_t(b + 0.05)},Default,,0,0,0,,{t}" for t, a, b in all_chunks]
    ass_path.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    srt = [f"{i}\n{_srt(a)} --> {_srt(b)}\n{t}\n" for i, (t, a, b) in enumerate(all_chunks, 1)]
    srt_path.write_text("\n".join(srt), encoding="utf-8")
