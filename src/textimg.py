"""رسم نص عربي بـ Pillow (تشكيل الحروف + اتجاه RTL)."""
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont
from common import ROOT

def font(size, bold=True):
    return ImageFont.truetype(str(ROOT / "fonts" / ("Tajawal-Bold.ttf" if bold else "Tajawal-Medium.ttf")), size)

from PIL import features
RAQM = features.check("raqm")   # مع raqm يتولى Pillow التشكيل والاتجاه بنفسه

def shape(t):
    return t if RAQM else get_display(arabic_reshaper.reshape(t))

def wrap(draw, text, f, max_w):
    lines, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if draw.textlength(shape(trial), font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def gradient(w, h, c1=(8, 14, 38), c2=(10, 70, 110)):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(0, w):
            t = (x / w * 0.5 + y / h * 0.5)
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    return img

def lower_third(text, path, w=1920, h=1080):
    """شريط عنوان شفاف يظهر على المشهد."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(64)
    tw = d.textlength(shape(text), font=f)
    pad = 36
    x1, y1 = w - 120, 120
    x0 = x1 - tw - pad * 2
    d.rounded_rectangle((x0, y1, x1, y1 + 110), 18, fill=(0, 0, 0, 170))
    d.rectangle((x1 - 8, y1, x1, y1 + 110), fill=(0, 200, 255, 255))
    d.text((x1 - pad - 8 - tw, y1 + 18), shape(text), font=f, fill=(255, 255, 255, 255))
    img.save(path)

def card(text, path, w=1920, h=1080):
    """بطاقة احتياطية عند غياب لقطة ستوك."""
    img = gradient(w, h)
    d = ImageDraw.Draw(img)
    f = font(110)
    lines = wrap(d, text or "TECH4U", f, w - 400)
    y = h // 2 - len(lines) * 70
    for ln in lines:
        s = shape(ln); tw = d.textlength(s, font=f)
        d.text(((w - tw) / 2, y), s, font=f, fill=(255, 255, 255)); y += 140
    img.save(path)

def thumbnail(text, bg_path, path, w=1280, h=720):
    from PIL import ImageFilter, ImageEnhance
    if bg_path:
        bg = Image.open(bg_path).convert("RGB")
        r = max(w / bg.width, h / bg.height)
        bg = bg.resize((int(bg.width * r), int(bg.height * r)))
        bg = bg.crop(((bg.width - w) // 2, (bg.height - h) // 2, (bg.width + w) // 2, (bg.height + h) // 2))
        bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(3))).enhance(0.45)
    else:
        bg = gradient(w, h)
    d = ImageDraw.Draw(bg)
    size = 150
    while size > 70:
        f = font(size)
        lines = wrap(d, text, f, w - 160)
        if len(lines) <= 3 and len(lines) * size * 1.2 <= 520: break
        size -= 10
    total = len(lines) * int(size * 1.2)
    y = 140 + (h - 140 - total) // 2
    for i, ln in enumerate(lines):
        s = shape(ln); tw = d.textlength(s, font=f)
        col = (255, 221, 0) if i == len(lines) - 1 else (255, 255, 255)
        d.text(((w - tw) / 2, y), s, font=f, fill=col, stroke_width=10, stroke_fill=(0, 0, 0))
        y += int(size * 1.2)
    badge = font(48)
    d.rounded_rectangle((40, 40, 300, 120), 14, fill=(0, 200, 255))
    d.text((70, 48), "TECH4U", font=badge, fill=(0, 0, 0))
    bg.save(path, quality=92)
