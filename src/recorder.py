"""مسجّل محلي بصفحة مذيع (Teleprompter): python src/recorder.py  ثم افتح http://127.0.0.1:8765
- كل شيء على جهازك فقط (127.0.0.1)؛ لا يُرفع الصوت لأي خدمة.
- تسجّل مشهداً مشهداً، تستمع، تعيد إن أردت، ثم "إنتاج الفيديو" فيبدأ المونتاج آلياً."""
import json, subprocess, sys, tempfile, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, load_config, read_json, run
import db
from main import load_env

# تنظيف خفيف + قص الصمت من البداية والنهاية فقط + ضبط مستوى الصوت (لا يقصّ من وسط الكلام)
TRIM = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15"
FILTER = f"highpass=f=80,afftdn=nf=-28,{TRIM},areverse,{TRIM},areverse,loudnorm=I=-16:TP=-1.5:LRA=11"

def video_row(vid, con):
    r = con.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    if not r or not r["workdir"]: return None
    return r

def scenes_state(r):
    work = Path(r["workdir"]); meta = read_json(work / "script.json", {"scenes": []})
    return [{"n": i, "text": sc["narration"], "chapter": sc.get("chapter", ""),
             "done": (work / "scenes" / f"{i:02d}.mp3").exists()} for i, sc in enumerate(meta["scenes"], 1)]

def convert(raw_path, out_mp3):
    run(["ffmpeg", "-y", "-i", str(raw_path), "-ac", "1", "-ar", "44100", "-af", FILTER, "-b:a", "192k", str(out_mp3)])

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path); con = db.connect(); parts = u.path.strip("/").split("/")
        if u.path == "/":
            b = PAGE.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if u.path == "/api/videos":
            rows = con.execute("SELECT id,title,stage FROM videos WHERE stage IN ('scripted','recorded','rendering','review') ORDER BY id DESC").fetchall()
            return self._json([dict(r) for r in rows])
        if parts[:2] == ["api", "video"]:
            r = video_row(int(parts[2]), con)
            return self._json({"id": r["id"], "title": r["title"], "stage": r["stage"], "scenes": scenes_state(r)}) if r else self._json({}, 404)
        if parts[:2] == ["api", "audio"]:
            r = video_row(int(parts[2]), con); f = Path(r["workdir"]) / "scenes" / f"{int(parts[3]):02d}.mp3"
            if not f.exists(): return self._json({}, 404)
            b = f.read_bytes(); self.send_response(200); self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        self._json({}, 404)
    def do_POST(self):
        parts = urlparse(self.path).path.strip("/").split("/"); con = db.connect()
        if parts[:2] == ["api", "upload"]:
            r = video_row(int(parts[2]), con); n = int(parts[3]); work = Path(r["workdir"])
            data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if len(data) < 2000: return self._json({"error": "التسجيل فارغ"}, 400)
            rec = work / "rec"; rec.mkdir(exist_ok=True)
            raw = rec / f"{n:02d}.webm"; raw.write_bytes(data)
            try: convert(raw, work / "scenes" / f"{n:02d}.mp3")
            except Exception as e:
                db.log_error("recorder", e, r["id"], con); return self._json({"error": "تعذّرت معالجة الصوت"}, 500)
            return self._json({"ok": True, "scenes": scenes_state(r)})
        if parts[:2] == ["api", "finish"]:
            r = video_row(int(parts[2]), con)
            if not all(s["done"] for s in scenes_state(r)): return self._json({"error": "بقيت مشاهد بلا تسجيل"}, 400)
            con.execute("UPDATE videos SET stage='recorded', updated_at=? WHERE id=?", (time.time(), r["id"]))
            log = Path(r["workdir"]) / "render.log"
            subprocess.Popen([sys.executable, str(ROOT / "src" / "main.py"), "--render", str(r["id"])],
                             stdout=open(log, "w", encoding="utf-8"), stderr=subprocess.STDOUT, cwd=str(ROOT))
            return self._json({"ok": True})
        self._json({}, 404)

PAGE = r"""<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>تسجيل التعليق الصوتي</title>
<style>
body{font-family:Tahoma,Segoe UI,sans-serif;background:#0f1722;color:#eef2f7;margin:0}
header{padding:14px 22px;background:#16212f;position:sticky;top:0;z-index:5;display:flex;gap:16px;align-items:center;justify-content:space-between}
main{max-width:900px;margin:0 auto;padding:18px}
.card{background:#16212f;border-radius:14px;padding:18px;margin:14px 0;border:2px solid transparent}
.card.cur{border-color:#2fa4ff}.card.done{border-color:#2e9e5b66}
.txt{font-size:30px;line-height:1.9;margin:6px 0 14px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
button{font:inherit;font-size:18px;padding:10px 18px;border:0;border-radius:10px;cursor:pointer;background:#2b3a4f;color:#fff}
button.rec{background:#d63b3b}button.go{background:#2e9e5b}button:disabled{opacity:.4;cursor:default}
.tag{font-size:14px;padding:3px 10px;border-radius:20px;background:#2b3a4f}.tag.ok{background:#2e9e5b}
.tips{font-size:15px;opacity:.85;line-height:1.8}.lvl{height:8px;border-radius:4px;background:#2fa4ff;width:0;transition:width .08s}
select{font:inherit;font-size:17px;padding:8px;border-radius:8px}
</style>
<header><div id="title">...</div><div class="row"><select id="vsel"></select><button class="go" id="finish" disabled>إنتاج الفيديو ▶</button></div></header>
<main>
<div class="card tips">نصائح: ابتعد عن المايك نحو 15 سم · غرفة هادئة بلا مروحة أو تلفزيون · اقرأ بنبرتك الطبيعية وبلهجتك كما تحب · خذ نفساً بين الجمل · اضغط <b>سجّل</b> ثم <b>أوقف</b> ثم استمع، وأعد إن أردت.<br>
إن تغيّرت كلمة أثناء القراءة فلا بأس؛ الترجمة تُوزَّع على نص المشهد تقريباً.</div>
<div id="list"></div></main>
<script>
let V=null,rec=null,chunks=[],stream=null,curN=null;
const q=s=>document.querySelector(s);
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function loadVideos(){
  const vs=await j('/api/videos');const sel=q('#vsel');sel.innerHTML=vs.map(v=>`<option value="${v.id}">#${v.id} ${v.title} (${v.stage})</option>`).join('');
  const want=new URLSearchParams(location.search).get('v');if(want&&vs.find(v=>v.id==want))sel.value=want;
  sel.onchange=()=>load(sel.value);if(vs.length)load(sel.value);else q('#title').textContent='لا توجد فيديوهات جاهزة للتسجيل'}
async function load(id){V=await j('/api/video/'+id);q('#title').textContent=V.title+' — '+V.scenes.filter(s=>s.done).length+'/'+V.scenes.length+' مشهد';render()}
function render(){
  const firstTodo=V.scenes.find(s=>!s.done);
  q('#list').innerHTML=V.scenes.map(s=>`<div class="card ${s.done?'done':''} ${firstTodo&&firstTodo.n==s.n?'cur':''}" id="c${s.n}">
   <div class="row"><span class="tag ${s.done?'ok':''}">مشهد ${s.n} ${s.chapter?'· '+s.chapter:''} ${s.done?'· مسجَّل ✓':''}</span></div>
   <div class="txt">${s.text}</div>
   <div class="row"><button class="rec" onclick="start(${s.n})" id="r${s.n}">● سجّل</button><button onclick="stop()" id="s${s.n}" disabled>■ أوقف</button>
   <audio controls id="a${s.n}" ${s.done?`src="/api/audio/${V.id}/${s.n}?t=${Date.now()}"`:'hidden'}></audio><div style="flex:1;min-width:80px"><div class="lvl" id="l${s.n}"></div></div></div></div>`).join('');
  q('#finish').disabled=!V.scenes.every(s=>s.done)||V.stage!=='scripted'&&V.stage!=='recorded';
  if(firstTodo)document.getElementById('c'+firstTodo.n).scrollIntoView({block:'center'})}
async function start(n){
  if(rec&&rec.state==='recording')return;curN=n;chunks=[];
  try{stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}})}
  catch(e){alert('تعذّر الوصول للمايك: فعّل إذن الميكروفون للمتصفح (الإعدادات ← الخصوصية ← الميكروفون).');return}
  const ac=new AudioContext(),src=ac.createMediaStreamSource(stream),an=ac.createAnalyser();src.connect(an);const buf=new Uint8Array(an.fftSize);
  const tick=()=>{if(!rec||rec.state!=='recording'){ac.close();return}an.getByteTimeDomainData(buf);let m=0;for(const x of buf)m=Math.max(m,Math.abs(x-128));
    q('#l'+n).style.width=Math.min(100,m*1.6)+'%';requestAnimationFrame(tick)};
  rec=new MediaRecorder(stream);rec.ondataavailable=e=>chunks.push(e.data);
  rec.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());q('#l'+n).style.width='0';
    const blob=new Blob(chunks,{type:rec.mimeType});q('#r'+n).textContent='... جاري الحفظ';
    const r=await j(`/api/upload/${V.id}/${n}`,{method:'POST',body:blob});
    if(r.error){alert(r.error)}else{V.scenes=r.scenes;q('#title').textContent=V.title+' — '+V.scenes.filter(s=>s.done).length+'/'+V.scenes.length+' مشهد'}render()};
  rec.start();q('#r'+n).disabled=true;q('#s'+n).disabled=false;q('#r'+n).textContent='● يسجّل...';tick()}
function stop(){if(rec&&rec.state==='recording')rec.stop()}
q('#finish').onclick=async()=>{if(!confirm('بدء المونتاج وإنتاج الفيديو؟ سيصلك على Telegram للمراجعة.'))return;
  const r=await j('/api/finish/'+V.id,{method:'POST'});if(r.error)alert(r.error);else{alert('بدأ الإنتاج. يمكنك إغلاق الصفحة. سيصلك الفيديو للمراجعة.');q('#finish').disabled=true}}
loadVideos();
</script></html>"""

if __name__ == "__main__":
    load_env(); port = load_config().get("recorder", {}).get("port", 8765)
    print(f"المسجّل يعمل: http://127.0.0.1:{port}  (Ctrl+C للإيقاف)")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
