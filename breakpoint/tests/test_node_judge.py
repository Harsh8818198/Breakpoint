import shutil
import tempfile
import unittest
from pathlib import Path

from breakpoint.judge import check_pair, judge_proof

VULN_SET = """
module.exports = function set(obj, path, value) {
  const keys = path.split('.');
  let cur = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    if (!(keys[i] in cur)) cur[keys[i]] = {};
    cur = cur[keys[i]];
  }
  cur[keys[keys.length - 1]] = value;
  return obj;
};
"""

FIXED_SET = VULN_SET.replace(
    "const keys = path.split('.');",
    "const keys = path.split('.');\n  if (keys.some((k) => k === '__proto__' || k === 'constructor' || k === 'prototype')) return obj;",
)

THROWING_FIX = VULN_SET.replace(
    "const keys = path.split('.');",
    "const keys = path.split('.');\n  if (keys.includes('__proto__')) throw new Error('unsafe key');",
)

VULN_READ = "module.exports = function read(o) { return o.a.b; };"
FIXED_READ = "module.exports = function read(o) { return o && o.a ? o.a.b : undefined; };"

POLLUTE = "const set = require(TARGET_DIR);\nset({}, '__proto__.polluted', 'yes');\n"
CRASH = "const read = require(TARGET_DIR);\nread({});\n"


def lib(root: Path, name: str, source: str) -> Path:
    d = root / name
    d.mkdir()
    (d / "package.json").write_text('{"name": "fake", "main": "index.js"}', encoding="utf-8")
    (d / "index.js").write_text(source, encoding="utf-8")
    return d


def proof(root: Path, name: str, source: str) -> Path:
    d = root / "proofs"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_text(source, encoding="utf-8")
    return p


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class NodeJudge(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.vuln = lib(self.root, "vuln", VULN_SET)
        self.fixed = lib(self.root, "fixed", FIXED_SET)

    def tearDown(self):
        self._tmp.cleanup()

    def test_real_pollution_works_before_and_is_stopped_after(self):
        p = proof(self.root, "ok.js", POLLUTE)
        pair = check_pair(self.vuln, self.fixed, p)
        self.assertTrue(pair["ok"], pair)
        self.assertEqual(pair["before"]["new_keys"], ["polluted"])
        self.assertEqual(pair["after"]["reason"], "no_effect")

    def test_a_fix_that_throws_counts_as_holding(self):
        throwing = lib(self.root, "throwing", THROWING_FIX)
        pair = check_pair(self.vuln, throwing, proof(self.root, "ok.js", POLLUTE))
        self.assertEqual(pair["after"]["reason"], "rejected_by_library")
        self.assertTrue(pair["ok"])

    def test_proof_that_never_loads_the_library_is_rejected(self):
        p = proof(self.root, "cheat.js", "Object.prototype.cheat = 1;")
        v = judge_proof(self.vuln, p)
        self.assertFalse(v.worked)
        self.assertEqual(v.reason, "library_not_used")

    def test_proof_that_pollutes_by_itself_is_rejected_by_the_control_run(self):
        p = proof(self.root, "self.js", "require(TARGET_DIR);\nObject.prototype.cheat = 1;")
        v = judge_proof(self.vuln, p)
        self.assertFalse(v.worked)
        self.assertEqual(v.reason, "self_triggering")
        self.assertTrue(v.control_fired)

    def test_proof_that_fails_on_its_own_is_not_counted_as_a_hold(self):
        p = proof(self.root, "broken.js", "require(TARGET_DIR);\nthrow new Error('typo in my proof');")
        pair = check_pair(self.vuln, self.fixed, p)
        self.assertEqual(pair["before"]["reason"], "proof_error")
        self.assertFalse(pair["ok"])

    def test_forbidden_code_is_never_run(self):
        p = proof(self.root, "bad.js", "const cp = require('child_process');\nrequire(TARGET_DIR);")
        v = judge_proof(self.vuln, p)
        self.assertEqual(v.reason, "forbidden_code")
        self.assertFalse(v.worked)

    def test_infinite_loop_times_out(self):
        p = proof(self.root, "loop.js", "require(TARGET_DIR);\nwhile (true) {}")
        v = judge_proof(self.vuln, p, timeout=2)
        self.assertEqual(v.reason, "timeout")

    def test_network_is_refused(self):
        # The proof marks Object.prototype only when the judge's block message comes back, so the key proves it.
        src = (
            "require(TARGET_DIR);\n"
            "fetch('http://127.0.0.1:9').catch((e) => {\n"
            "  if (/blocked by the judge/.test(e.message)) Object.prototype.sawBlock = 1;\n"
            "});\n"
        )
        v = judge_proof(self.vuln, proof(self.root, "net.js", src))
        self.assertEqual(v.new_keys, ["sawBlock"])
        self.assertFalse(v.worked)  # the proof did the marking itself, so the control run rejects it

    def test_crash_oracle(self):
        vuln, fixed = lib(self.root, "rv", VULN_READ), lib(self.root, "rf", FIXED_READ)
        pair = check_pair(vuln, fixed, proof(self.root, "crash.js", CRASH), oracle="crash")
        self.assertTrue(pair["ok"], pair)
        self.assertTrue(pair["before"]["crashed_in_target"])

    def test_crash_in_the_proof_itself_is_not_a_library_crash(self):
        fixed = lib(self.root, "rf2", FIXED_READ)
        src = "require(TARGET_DIR);\nconst x = null;\nx.boom;"
        v = judge_proof(fixed, proof(self.root, "own.js", src), oracle="crash")
        self.assertFalse(v.worked)
        self.assertEqual(v.reason, "proof_error")


if __name__ == "__main__":
    unittest.main()
