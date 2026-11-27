"""ضغطة واحدة: يجهّز أول فيديو (إن لم يوجد) ثم يشغّل صفحة التسجيل ويفتحها في المتصفح."""
import os, subprocess, sys, threading, webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, load_config
import db, recorder
from main import load_env

load_env(); con = db.connect()
n = con.execute("SELECT COUNT(*) c FROM videos").fetchone()["c"]
if n == 0:
    print("تجهيز أول فيديو من السيناريو الجاهز ...")
    subprocess.run([sys.executable, str(ROOT / "src" / "main.py"), "--script", str(ROOT / "samples" / "first_video.json")], check=True)
row = con.execute("SELECT id FROM videos WHERE stage IN ('scripted','recorded') ORDER BY id DESC LIMIT 1").fetchone()
port = load_config().get("recorder", {}).get("port", 8765)
url = f"http://127.0.0.1:{port}/" + (f"?v={row['id']}" if row else "")
srv = ThreadingHTTPServer(("127.0.0.1", port), recorder.H)
print(f"\nصفحة التسجيل: {url}\n(أغلق هذه النافذة لإيقاف المسجّل)")
if not os.environ.get("TECH4U_NO_BROWSER"):
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
srv.serve_forever()
