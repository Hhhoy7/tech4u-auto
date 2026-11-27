"""قاعدة SQLite المحلية: كل حالة النظام في ملف واحد (state/tech4u.db). مجانية وبلا خادم."""
import json, os, sqlite3, time
from pathlib import Path
from common import ROOT

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT NOT NULL, updated_at REAL);
CREATE TABLE IF NOT EXISTS ideas(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, lang TEXT DEFAULT 'ar', source TEXT,
  score REAL, score_detail TEXT, status TEXT DEFAULT 'new', created_at REAL);
CREATE TABLE IF NOT EXISTS videos(
  id INTEGER PRIMARY KEY, idea_id INTEGER REFERENCES ideas(id), kind TEXT DEFAULT 'long',
  lang TEXT DEFAULT 'ar', topic TEXT, title TEXT,
  -- idea,researched,scripted,voiced,rendered,review,approved,uploaded,measured,rejected,failed
  stage TEXT DEFAULT 'idea', workdir TEXT, youtube_id TEXT,
  created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS claude_ledger(
  id INTEGER PRIMARY KEY, ts REAL, model TEXT, purpose TEXT, video_id INTEGER,
  status TEXT,            -- reserved | settled | failed_unknown
  est_in_tokens INTEGER, max_out_tokens INTEGER,
  in_tokens INTEGER, out_tokens INTEGER, cost_usd REAL);
CREATE TABLE IF NOT EXISTS publish_log(
  id INTEGER PRIMARY KEY, ts REAL, video_id INTEGER, youtube_id TEXT, privacy TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS metrics_daily(
  day TEXT, youtube_id TEXT, views INTEGER, watch_min REAL, avg_view_sec REAL,
  ctr REAL, subs_gained INTEGER, PRIMARY KEY(day, youtube_id));
CREATE TABLE IF NOT EXISTS automation_log(id INTEGER PRIMARY KEY, ts REAL, stage TEXT, video_id INTEGER, msg TEXT);
CREATE TABLE IF NOT EXISTS errors(id INTEGER PRIMARY KEY, ts REAL, stage TEXT, video_id INTEGER, error TEXT);
"""
DEFAULT_SETTINGS = {
    "paused": "false",            # إيقاف الإنتاج كله
    "publish_enabled": "false",   # النشر مغلق افتراضياً حتى تفعّله أنت
    "claude_enabled": "false",    # استدعاءات Claude مغلقة حتى توافق أنت (python src/budget.py enable)
}

def db_path():
    return Path(os.environ.get("TECH4U_DB") or (ROOT / "state" / "tech4u.db"))

def connect():
    p = db_path(); p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=30, isolation_level=None)  # autocommit؛ المعاملات صريحة
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL"); con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    con.execute("INSERT OR IGNORE INTO meta VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
    for k, v in DEFAULT_SETTINGS.items():
        con.execute("INSERT OR IGNORE INTO settings VALUES(?,?,?)", (k, v, time.time()))
    return con

def get_setting(k, con=None):
    c = con or connect(); r = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    return r["v"] if r else None

def set_setting(k, v, con=None):
    c = con or connect()
    c.execute("INSERT INTO settings VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_at=excluded.updated_at",
              (k, str(v), time.time()))

def flag(k, con=None):
    return get_setting(k, con) == "true"

def log(stage, msg, video_id=None, con=None):
    (con or connect()).execute("INSERT INTO automation_log(ts,stage,video_id,msg) VALUES(?,?,?,?)",
                               (time.time(), stage, video_id, msg))

def log_error(stage, error, video_id=None, con=None):
    (con or connect()).execute("INSERT INTO errors(ts,stage,video_id,error) VALUES(?,?,?,?)",
                               (time.time(), stage, video_id, str(error)[:2000]))

def import_published(path=None, con=None):
    """يستورد state/published.json القديم مرة واحدة (آمن للتكرار)."""
    c = con or connect(); p = Path(path or ROOT / "state" / "published.json")
    if not p.exists() or get_setting("published_imported", c) == "true":
        return 0
    n = 0
    for v in json.loads(p.read_text(encoding="utf-8")).get("videos", []):
        c.execute("INSERT INTO videos(topic,title,stage,youtube_id,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                  (v.get("topic"), v.get("title"), "uploaded", v.get("id"), time.time(), time.time())); n += 1
    set_setting("published_imported", "true", c)
    return n
