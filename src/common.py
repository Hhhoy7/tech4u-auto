import json, os, subprocess, yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load_config():
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"فشل الأمر: {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r.stdout

def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", str(path)]).strip())

def env(name, required=True):
    v = os.environ.get(name, "")
    if required and not v:
        raise SystemExit(f"المتغير {name} غير مضبوط")
    return v

def read_json(path, default):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
