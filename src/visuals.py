"""جلب لقطات ستوك من Pexels (مجاني) مع بدائل مولّدة."""
import os, requests, hashlib
from pathlib import Path
from common import ROOT

CACHE = ROOT / "state" / "stock_cache"

def _download(url, name):
    out = CACHE / name
    if not out.exists():
        with requests.get(url, stream=True, timeout=120) as dl:
            dl.raise_for_status()
            with open(out, "wb") as fh:
                for chunk in dl.iter_content(1 << 20):
                    fh.write(chunk)
    return out

def fetch_pixabay(query, used):
    key = os.environ.get("PIXABAY_API_KEY")
    if not key or not query:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get("https://pixabay.com/api/videos/",
                         params={"key": key, "q": query, "per_page": 10, "safesearch": "true"}, timeout=30)
        r.raise_for_status()
        for h in r.json().get("hits", []):
            pid = "pb%s" % h["id"]
            if pid in used:
                continue
            v = h["videos"]
            pick = next((v[k] for k in ("large", "medium") if v.get(k, {}).get("url") and v[k].get("width", 0) >= 1280), None)
            if not pick:
                continue
            used.add(pid)
            return _download(pick["url"], pid + ".mp4")
    except Exception as e:
        print(f"  ! تعذر جلب لقطة '{query}' من Pixabay: {e}")
    return None

def fetch_clip(query, dest_dir, used):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return fetch_pixabay(query, used)
    if not query:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get("https://api.pexels.com/videos/search",
                         headers={"Authorization": key},
                         params={"query": query, "orientation": "landscape", "per_page": 8, "size": "medium"},
                         timeout=30)
        r.raise_for_status()
        for v in r.json().get("videos", []):
            if v["id"] in used:
                continue
            files = [f for f in v["video_files"] if f["file_type"] == "video/mp4" and 1280 <= (f.get("width") or 0) <= 1920]
            if not files:
                continue
            f = max(files, key=lambda x: x["width"])
            out = CACHE / f"{v['id']}.mp4"
            if not out.exists():
                with requests.get(f["link"], stream=True, timeout=120) as dl:
                    dl.raise_for_status()
                    with open(out, "wb") as fh:
                        for chunk in dl.iter_content(1 << 20):
                            fh.write(chunk)
            used.add(v["id"])
            return out
    except Exception as e:
        print(f"  ! تعذر جلب لقطة '{query}': {e}")
    return None
