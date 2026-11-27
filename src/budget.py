"""حارس رصيد Claude: لا استدعاء إلا إذا (1) فعّلته أنت، (2) الأسعار مؤكدة، (3) أسوأ تكلفة ممكنة تتسع في الرصيد.
بلا أي اتصال شبكة للتقدير: التقدير محلي ومتحفظ. الأرقام الفعلية تؤخذ من usage في الرد.
CLI:  python src/budget.py status | enable | disable
"""
import sys, time
from common import load_config
import db

class BudgetError(RuntimeError):
    pass

def _cfg():
    return load_config()["budget"]

def _cost(price, in_tok, out_tok):
    return (in_tok * price["input"] + out_tok * price["output"]) / 1_000_000

def price_for(model, b=None):
    b = b or _cfg()
    if not b.get("pricing_verified"):
        raise BudgetError("الأسعار لم تُؤكَّد بعد (budget.pricing_verified=false). يؤكدها المالك من الصفحة الرسمية قبل أول استدعاء.")
    p = (b.get("pricing") or {}).get(model)
    if not p or p.get("input") is None or p.get("output") is None:
        raise BudgetError(f"لا سعر مضبوط للنموذج {model} في config.yaml")
    return p

def committed_usd(con):
    r = con.execute("SELECT COALESCE(SUM(cost_usd),0) s FROM claude_ledger").fetchone()
    return float(r["s"])

def status(con=None):
    con = con or db.connect(); b = _cfg(); spent = committed_usd(con)
    return {"enabled": db.flag("claude_enabled", con), "pricing_verified": bool(b.get("pricing_verified")),
            "spent_usd": round(spent, 4), "hard_cap_usd": b["hard_cap_usd"], "warn_usd": b["warn_usd"],
            "remaining_usd": round(b["hard_cap_usd"] - spent, 4)}

def estimate_input_tokens(system, messages, b=None):
    b = b or _cfg(); chars = len(system or "")
    for m in messages:
        c = m["content"]
        chars += len(c) if isinstance(c, str) else sum(len(x.get("text", "")) for x in c)
    return int(chars * b["tokens_per_char_upper"]) + 50

def validate_config(b):
    if not (0 < b["warn_usd"] < b["hard_cap_usd"] <= b["total_usd"] - 0.5):
        raise BudgetError("إعداد الميزانية غير صالح: يجب warn < hard_cap وأن يبقى احتياطي ≥ 0.5$ من الإجمالي")

def reserve(con, model, system, messages, max_tokens, purpose, video_id=None):
    """يحجز أسوأ تكلفة داخل معاملة واحدة؛ يرفع BudgetError إن لم تتسع. يعيد (id, est_in)."""
    b = _cfg(); validate_config(b)
    if not db.flag("claude_enabled", con):
        raise BudgetError("استدعاءات Claude مغلقة. لم يوافق المالك بعد (python src/budget.py enable).")
    price = price_for(model, b)
    est_in = estimate_input_tokens(system, messages, b)
    worst = _cost(price, est_in, max_tokens)
    con.execute("BEGIN IMMEDIATE")
    try:
        spent = committed_usd(con)
        if spent + worst > b["hard_cap_usd"]:
            raise BudgetError(f"مرفوض: المنفَق {spent:.3f}$ + أسوأ تكلفة {worst:.3f}$ يتجاوز السقف {b['hard_cap_usd']}$")
        cur = con.execute("INSERT INTO claude_ledger(ts,model,purpose,video_id,status,est_in_tokens,max_out_tokens,cost_usd)"
                          " VALUES(?,?,?,?, 'reserved',?,?,?)", (time.time(), model, purpose, video_id, est_in, max_tokens, worst))
        rid = cur.lastrowid
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK"); raise
    return rid, est_in, price

def settle(con, rid, price, usage):
    i = int(getattr(usage, "input_tokens", 0) or 0)
    o = int(getattr(usage, "output_tokens", 0) or 0)
    cw = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)   # متحفظ: نحسبها كإدخال عادي ×1.25
    cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cost = _cost(price, i + cr + int(cw * 1.25), o)
    con.execute("UPDATE claude_ledger SET status='settled', in_tokens=?, out_tokens=?, cost_usd=? WHERE id=?",
                (i + cw + cr, o, cost, rid))
    return cost

def release(con, rid, price, est_in, charge_input):
    if charge_input:   # فشل غامض (انقطاع) قد يكون فُوتر: نحسب كلفة الإدخال المقدّرة فقط
        con.execute("UPDATE claude_ledger SET status='failed_unknown', cost_usd=? WHERE id=?",
                    (_cost(price, est_in, 0), rid))
    else:
        con.execute("DELETE FROM claude_ledger WHERE id=?", (rid,))

def guarded_create(client, *, purpose, video_id=None, con=None, **kw):
    """بديل client.messages.create. kw: model, max_tokens, system, messages ..."""
    con = con or db.connect()
    rid, est_in, price = reserve(con, kw["model"], kw.get("system"), kw["messages"], kw["max_tokens"], purpose, video_id)
    try:
        resp = client.messages.create(**kw)
    except Exception as e:
        # أخطاء الحالة 4xx/5xx الصريحة لا تُفوتر؛ الباقي (مهلة/انقطاع) نحسبه احتياطاً
        explicit = getattr(e, "status_code", None) is not None
        release(con, rid, price, est_in, charge_input=not explicit); raise
    cost = settle(con, rid, price, resp.usage)
    s = status(con)
    if s["spent_usd"] >= _cfg()["warn_usd"]:
        print(f"⚠️ رصيد Claude: صُرف {s['spent_usd']}$ من السقف {s['hard_cap_usd']}$")
    return resp

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    con = db.connect()
    if cmd == "enable":
        b = _cfg(); validate_config(b)
        if not b.get("pricing_verified"):
            sys.exit("ارفض التفعيل: ثبّت الأسعار الرسمية في config.yaml ثم اضبط pricing_verified: true")
        db.set_setting("claude_enabled", "true", con); print("تم تفعيل Claude (ضمن السقف).")
    elif cmd == "disable":
        db.set_setting("claude_enabled", "false", con); print("تم إيقاف Claude.")
    print(status(con))
