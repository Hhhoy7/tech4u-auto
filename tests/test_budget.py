import os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import budget, db

PRICE = {"input": 3.0, "output": 15.0}   # أسعار وهمية للاختبار فقط
CFG = {"total_usd": 5.0, "hard_cap_usd": 4.0, "warn_usd": 3.0, "tokens_per_char_upper": 0.7,
       "pricing_verified": True, "pricing": {"m": PRICE}}

class Fake:
    def __init__(self, i=1000, o=1000, exc=None):
        self.calls = 0; self.i, self.o, self.exc = i, o, exc
        self.messages = NS(create=self._c)
    def _c(self, **kw):
        self.calls += 1
        if self.exc: raise self.exc
        return NS(usage=NS(input_tokens=self.i, output_tokens=self.o), content=[])

class T(unittest.TestCase):
    def setUp(self):
        self.f = tempfile.NamedTemporaryFile(suffix=".db", delete=False); self.f.close()
        os.environ["TECH4U_DB"] = self.f.name
        self.cfg = dict(CFG); budget._cfg = lambda: self.cfg
        self.con = db.connect()
    def tearDown(self): os.unlink(self.f.name)
    def call(self, client, max_tokens=1000, text="س" * 1000):
        return budget.guarded_create(client, purpose="t", con=self.con, model="m", max_tokens=max_tokens,
                                     messages=[{"role": "user", "content": text}])
    def enable(self): db.set_setting("claude_enabled", "true", self.con)

    def test_blocked_by_default_no_call(self):
        c = Fake()
        with self.assertRaises(budget.BudgetError): self.call(c)
        self.assertEqual(c.calls, 0)
    def test_blocked_when_pricing_unverified(self):
        self.enable(); self.cfg["pricing_verified"] = False; c = Fake()
        with self.assertRaises(budget.BudgetError): self.call(c)
        self.assertEqual(c.calls, 0)
    def test_blocked_when_price_missing(self):
        self.enable(); self.cfg["pricing"] = {"m": {"input": None, "output": None}}; c = Fake()
        with self.assertRaises(budget.BudgetError): self.call(c)
        self.assertEqual(c.calls, 0)
    def test_records_actual_cost(self):
        self.enable(); self.call(Fake(2000, 3000))
        self.assertAlmostEqual(budget.status(self.con)["spent_usd"], (2000*3 + 3000*15)/1e6, places=6)
    def test_never_exceeds_cap(self):
        self.enable(); c = Fake(10, 100000)   # كل استدعاء يحجز أسوأ حالة: 100k*15/1e6=1.5$
        n = 0
        while True:
            try: self.call(c, max_tokens=100000); n += 1
            except budget.BudgetError: break
            self.assertLess(n, 20)
        self.assertLessEqual(budget.status(self.con)["spent_usd"], 4.0)
        self.assertEqual(c.calls, n)            # المرفوض لم يصل للشبكة
    def test_worst_case_reserved_blocks_oversized(self):
        self.enable(); c = Fake()
        with self.assertRaises(budget.BudgetError): self.call(c, max_tokens=400000)   # 6$ > 4$
        self.assertEqual(c.calls, 0)
    def test_explicit_api_error_releases(self):
        self.enable(); e = Exception("x"); e.status_code = 429
        with self.assertRaises(Exception): self.call(Fake(exc=e))
        self.assertEqual(budget.status(self.con)["spent_usd"], 0)
    def test_timeout_charges_input_estimate(self):
        self.enable()
        with self.assertRaises(Exception): self.call(Fake(exc=TimeoutError()))
        self.assertGreater(budget.status(self.con)["spent_usd"], 0)
    def test_invalid_config_rejected(self):
        self.enable(); self.cfg["hard_cap_usd"] = 4.9
        with self.assertRaises(budget.BudgetError): self.call(Fake())
    def test_db_defaults_and_import(self):
        self.assertFalse(db.flag("publish_enabled", self.con)); self.assertFalse(db.flag("claude_enabled", self.con))
        p = Path(self.f.name + ".json"); p.write_text('{"videos":[{"topic":"a","title":"b","id":"x"}]}')
        self.assertEqual(db.import_published(p, self.con), 1); self.assertEqual(db.import_published(p, self.con), 0); p.unlink()

if __name__ == "__main__": unittest.main(verbosity=2)
