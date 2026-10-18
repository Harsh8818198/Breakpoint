import json
import tempfile
import unittest
from pathlib import Path

from breakpoint.codeindex import CodeIndex
from breakpoint.evaluation import score
from breakpoint.evaluation.arms import ArmUnsupported, from_sarif, import_findings, run_arm
from breakpoint.evaluation.cli import main as eval_main
from breakpoint.evaluation.runner import run_eval, run_file
from breakpoint.evaluation.sets import load_set, materialize, sanitize_text
from breakpoint.usage import MeteredLLM

from tests.test_codeindex import make_repo
from tests.test_codeverify import ScriptedLLM
from tests.test_routemap import APP

EVAL_LINE = "const n = eval(req.body.n);"          # routes/handler.js line 12 in the shared test app


class Fake(ScriptedLLM):
    provider, model = "fake", "fake-1"


class ConfirmAll:
    """Stands in for the code check: keeps every finding and reports its cited lines as evidence."""

    def __init__(self, index, llm):
        self.n = 0

    def __call__(self, findings):
        self.n = len(findings)
        return [{"status": "CONFIRMED", "evidence_items": list(f.code_refs)} for f in findings]

    def stats(self):
        return {"checked": self.n, "confirmed": self.n, "refuted": 0, "unverified": 0, "errors": 0}


def write_set(repo_files=None, **over) -> Path:
    root = make_repo(repo_files or APP)
    data = {"id": "mini", "title": "Mini", "role": "heldout", "repo": {"path": root},
            "bugs": [{"id": "eval", "title": "eval on the request body", "class": "injection",
                      "locations": [{"file": "routes/handler.js", "lines": [12, 12]}]},
                     {"id": "redirect", "title": "open redirect", "locations": [{"file": "routes/index.js", "lines": [12, 12]}]}]}
    data.update(over)
    p = Path(tempfile.mkdtemp(prefix="bp_set_")) / "set.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def plain_reply(line=12, quote=EVAL_LINE, title="Remote code execution via eval"):
    return [{"title": title, "attack_category": "injection", "description": "eval of the body", "steps_to_exploit": ["post"],
             "impact": "rce", "code_refs": [{"file": "routes/handler.js", "line": line, "quote": quote}]},
            {"title": "A second claim", "description": "d", "code_refs": []}]


class Sets(unittest.TestCase):
    def test_a_set_needs_ids_titles_and_locations(self):
        for bad in ({"bugs": [{"id": "a", "title": "t"}]}, {"bugs": [{"id": "a", "title": "t", "locations": [1]},
                                                                      {"id": "a", "title": "u", "locations": [1]}]}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    load_set(str(write_set(**bad)))

    def test_text_cleaning_never_changes_the_number_of_lines(self):
        text = "// Fix for A8 - CSRF\napp.use(csrf());\n// ordinary note\nx = 1; // vuln-code-snippet vuln-line k\n// vuln-code-snippet start k\n"
        spec = {"blank_comment_lines_matching": ["(?i)fix for"], "strip_regex": [r"\s*//\s*vuln-code-snippet.*$"],
                "blank_lines_matching": [r"vuln-code-snippet start"]}
        out = sanitize_text("a.js", text, spec)
        self.assertEqual(out.count("\n"), text.count("\n"))
        self.assertEqual(out.split("\n"), ["//", "app.use(csrf());", "// ordinary note", "x = 1;", "//", ""])
        self.assertEqual(sanitize_text("a.js", text, {"blank_all_comments": True}).split("\n")[2], "//")

    def test_cleaning_a_block_comment_never_turns_commented_out_code_into_live_code(self):
        from breakpoint.codeindex import comment_mask
        text = "/* Fix for A7 - access control\n   app.get('/x', isAdmin, h)\n*/\napp.get('/x', h)\n// Fix for A2\n"
        for spec in ({"blank_comment_lines_matching": ["(?i)fix for"]}, {"blank_all_comments": True}):
            with self.subTest(spec=spec):
                out = sanitize_text("a.js", text, spec).split("\n")
                self.assertEqual(len(out), len(text.split("\n")))
                self.assertNotIn("Fix for", "\n".join(out))
                mask = comment_mask("a.js", out)
                self.assertEqual(mask[:3], [True, True, True])               # the old block is still one comment
                self.assertFalse(mask[3])                                    # the live route is still live
                self.assertTrue(mask[4])

    def test_a_cleaned_variant_keeps_line_numbers_drops_files_and_is_cached(self):
        files = dict(APP)
        files["README.md"] = "The eval route is vulnerable.\n"
        files["routes/handler.js"] = files["routes/handler.js"].replace(EVAL_LINE, EVAL_LINE + " // Insecure: eval")
        files[".env"] = "SECRET=1\n"
        p = write_set(files, variants={"clean": {"drop_paths": ["README.md"], "strip_regex": [r"\s*//\s*Insecure.*$"]}})
        es, cache = load_set(str(p)), Path(tempfile.mkdtemp())
        raw, clean = materialize(es, "raw", cache), materialize(es, "clean", cache)
        self.assertNotEqual(str(raw), str(clean))
        self.assertFalse((clean / "README.md").exists())
        self.assertTrue((raw / "README.md").exists())
        self.assertFalse((clean / ".env").exists())
        lines = (clean / "routes" / "handler.js").read_text(encoding="utf-8").split("\n")
        self.assertEqual(lines[11], "        " + EVAL_LINE)                # the known bug is still on line 12
        self.assertEqual(materialize(es, "clean", cache), clean)           # second call reuses the copy
        with self.assertRaises(KeyError):
            materialize(es, "nope", cache)


class LabelChecks(unittest.TestCase):
    def test_a_variant_that_blanks_or_drops_the_vulnerable_code_is_reported(self):
        from breakpoint.evaluation.sets import validate_labels
        p = write_set(variants={"good": {"strip_regex": [r"\s*// note.*$"]},
                                "blanked": {"blank_lines_matching": [r"eval\(req\.body\.n\)"]},
                                "dropped": {"drop_paths": ["routes/handler.js"]}})
        es, cache = load_set(str(p)), Path(tempfile.mkdtemp())
        self.assertEqual(validate_labels(es, "raw", cache)[:0], [])
        self.assertTrue(any(x.startswith("eval:") for x in validate_labels(es, "blanked", cache)))
        self.assertTrue(any(x.startswith("eval:") for x in validate_labels(es, "dropped", cache)))
        self.assertFalse(any(x.startswith("eval:") for x in validate_labels(es, "good", cache)))

    def test_labels_are_read_from_snippet_markers_and_keys_that_mark_the_same_lines_become_one_bug(self):
        from breakpoint.evaluation.snippets import challenge_names, labels_from_snippets
        files = {
            "routes/login.ts": ("// vuln-code-snippet start loginAdminChallenge loginJimChallenge\n"
                                "export function login () {\n"
                                "  db.query(`SELECT ${req.body.email}`) // vuln-code-snippet vuln-line loginAdminChallenge loginJimChallenge\n"
                                "}\n// vuln-code-snippet end loginAdminChallenge loginJimChallenge\n"),
            "server.ts": ("app.use('/ftp', serveIndex('ftp')) // vuln-code-snippet vuln-line dirChallenge\n"
                          "// vuln-code-snippet vuln-line dirChallenge\napp.use('/ftp/:file', servePublicFiles())\n"),
            "data/static/challenges.yml": ("-\n  name: 'Login Admin'\n  category: 'Injection'\n  key: loginAdminChallenge\n"
                                           "-\n  name: 'Login Jim'\n  category: 'Injection'\n  key: loginJimChallenge\n"
                                           "-\n  name: 'Confidential Document'\n  category: 'Sensitive Data Exposure'\n  key: dirChallenge\n"),
        }
        root = make_repo(files)
        names = challenge_names(files["data/static/challenges.yml"])
        self.assertEqual(names["dirChallenge"], {"name": "Confidential Document", "category": "Sensitive Data Exposure"})
        bugs = labels_from_snippets(root, Path(root) / "data/static/challenges.yml")
        self.assertEqual(len(bugs), 2)
        login = next(b for b in bugs if b["id"] == "loginAdminChallenge")
        self.assertIn("Login Jim", login["title"])
        self.assertEqual(login["locations"], [{"file": "routes/login.ts", "lines": [3, 3]}])
        ftp = next(b for b in bugs if b["id"] == "dirChallenge")
        self.assertEqual(ftp["locations"], [{"file": "server.ts", "lines": [1, 1]}, {"file": "server.ts", "lines": [3, 3]}])


class Scoring(unittest.TestCase):
    def test_a_finding_counts_when_its_evidence_is_inside_a_location_with_two_lines_of_slack(self):
        es = load_set(str(write_set()))
        f = lambda line: {"evidence": [{"file": "routes/handler.js", "line": line, "quote": "x"}]}   # noqa: E731
        self.assertEqual(score.bugs_hit(f(14), es.bugs), ["eval"])
        self.assertEqual(score.bugs_hit(f(15), es.bugs), [])
        self.assertEqual(score.bugs_hit({"evidence": [{"file": "other.js", "line": 12}]}, es.bugs), [])

    def test_findings_cluster_by_evidence_location_or_by_similar_title_in_one_file(self):
        ev = lambda file, line: [{"file": file, "line": line, "quote": "q"}]                          # noqa: E731
        run = {"arm": "a", "run": 1}
        items = [(run, {"title": "Eval injection", "evidence": ev("a.js", 10)}),
                 (run, {"title": "Totally different words", "evidence": ev("a.js", 12)}),            # 2 lines away: same issue
                 (run, {"title": "Remote code execution via eval", "evidence": ev("a.js", 60)}),     # far, dissimilar title
                 (run, {"title": "Remote code execution via eval statement", "evidence": ev("a.js", 80)}),   # same file, similar title
                 (run, {"title": "Remote code execution via eval", "evidence": ev("b.js", 60)})]    # similar title, other file
        keys = sorted(c["key"] for c in score.cluster(items))
        self.assertEqual(keys, ["a.js:10", "a.js:60", "b.js:60"])


class Arms(unittest.TestCase):
    def setUp(self):
        self.root = make_repo(APP)
        self.index = CodeIndex.from_dir(self.root)

    def test_the_plain_arm_returns_claims_with_checked_citations(self):
        r = run_arm("plain", self.root, self.index, Fake(baseline=plain_reply(line=99)))
        self.assertEqual([f.title for f in r.findings], ["Remote code execution via eval", "A second claim"])
        self.assertEqual(r.findings[0].code_refs, [{"file": "routes/handler.js", "line": 12, "quote": EVAL_LINE}])   # 99 corrected

    def test_route_review_says_so_when_there_is_no_express_app(self):
        root = make_repo({"app.py": "print('hi')\n"})
        with self.assertRaises(ArmUnsupported):
            run_arm("route-review", root, CodeIndex.from_dir(root), Fake())

    def test_findings_made_elsewhere_can_be_imported_from_json_and_sarif(self):
        d = Path(tempfile.mkdtemp())
        (d / "minimal.json").write_text(json.dumps([{"title": "eval", "file": "routes/handler.js", "line": 12}]), encoding="utf-8")
        got = import_findings(str(d / "minimal.json"), self.index)
        self.assertEqual(got[0].code_refs, [{"file": "routes/handler.js", "line": 12, "quote": EVAL_LINE}])
        sarif = {"runs": [{"tool": {"driver": {"rules": [{"id": "js/eval", "shortDescription": {"text": "Code injection"}}]}},
                           "results": [{"ruleId": "js/eval", "message": {"text": "eval of user input"},
                                        "locations": [{"physicalLocation": {"artifactLocation": {"uri": "file:///repo/routes/handler.js"},
                                                                            "region": {"startLine": 12}}}]}]}]}
        f = from_sarif(sarif, self.index)[0]
        self.assertEqual((f.title, f.code_refs[0]["file"], f.code_refs[0]["line"]), ("Code injection", "routes/handler.js", 12))
        (d / "bad.json").write_text("not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            import_findings(str(d / "bad.json"), self.index)

    def test_metered_calls_are_counted_and_failures_pass_through(self):
        llm = MeteredLLM(Fake(x="hello"))
        self.assertEqual(llm.complete("sys", "user", task="x"), "hello")
        self.assertEqual(llm.provider, "fake")
        with self.assertRaises(KeyError):
            llm.complete("s", "u", task="missing")
        snap = llm.meter.snapshot()
        self.assertEqual((snap["calls"], snap["failed"]), (2, 1))
        self.assertEqual(snap["by_task"]["x"]["est_tokens"], round((len("sys") + len("user") + len("hello")) / 4))


class Running(unittest.TestCase):
    def go(self, arms, runs=2, **kw):
        es = load_set(str(write_set()))
        out, cache = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        files = run_eval(es, "raw", arms, runs, out, cache, llm=Fake(baseline=plain_reply()), verifier_factory=ConfirmAll,
                         log=lambda *_: None, **kw)
        return es, out, cache, files

    def test_every_run_is_saved_with_its_findings_cost_and_model(self):
        es, out, _, files = self.go(["plain"], runs=2)
        self.assertEqual(len(files), 2)
        rec = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual((rec["status"], rec["arm"], rec["run"], rec["model"]), ("ok", "plain", 1, "fake/fake-1"))
        self.assertEqual(rec["candidates"], 2)
        self.assertEqual(len(rec["kept"]), 2)
        self.assertEqual(rec["usage"]["arm"]["calls"], 1)
        self.assertGreater(rec["usage"]["arm"]["est_tokens"], 0)
        self.assertEqual(rec["kept"][0]["evidence"][0]["line"], 12)

    def test_resume_skips_runs_already_on_disk_and_fresh_redoes_them(self):
        es, out, cache, files = self.go(["plain"], runs=1)
        before = files[0].stat().st_mtime_ns
        llm = Fake(baseline=plain_reply())
        run_eval(es, "raw", ["plain"], 1, out, cache, llm=llm, verifier_factory=ConfirmAll, log=lambda *_: None)
        self.assertEqual(llm.prompts("baseline"), [])                        # nothing was asked again
        self.assertEqual(files[0].stat().st_mtime_ns, before)
        run_eval(es, "raw", ["plain"], 1, out, cache, llm=llm, verifier_factory=ConfirmAll, resume=False, log=lambda *_: None)
        self.assertEqual(len(llm.prompts("baseline")), 1)

    def test_an_arm_that_cannot_run_is_recorded_not_crashed(self):
        es = load_set(str(write_set({"app.py": "print('hi')\n"})))
        out, cache = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        files = run_eval(es, "raw", ["route-review"], 1, out, cache, llm=Fake(), log=lambda *_: None)
        self.assertEqual(json.loads(files[0].read_text(encoding="utf-8"))["status"], "unsupported")

    def test_without_the_code_check_the_cited_lines_are_the_evidence_and_the_run_says_so(self):
        es, out, _, files = self.go(["plain"], runs=1, verify=False)
        rec = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertFalse(rec["verify"])
        self.assertEqual(rec["kept"][0]["evidence"][0]["line"], 12)

    def test_an_imported_result_runs_once_whatever_the_run_count(self):
        d = Path(tempfile.mkdtemp())
        f = d / "other.json"
        f.write_text(json.dumps([{"title": "eval", "file": "routes/handler.js", "line": 12}]), encoding="utf-8")
        es, out, _, files = self.go([f"import:{f}"], runs=3)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].parent.name, "import-other")


class Reporting(unittest.TestCase):
    def setUp(self):
        self.es = load_set(str(write_set(role="dev", contamination="very public")))
        self.out, self.cache = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        run_eval(self.es, "raw", ["plain"], 2, self.out, self.cache, llm=Fake(baseline=plain_reply()), verifier_factory=ConfirmAll,
                 log=lambda *_: None)
        self.runs = score.load_runs(self.out, "mini", "raw")

    def test_mechanical_summary_and_every_caveat_that_applies(self):
        s = score.summarize(self.es, "raw", self.runs)
        a = s["arms"]["plain"]
        self.assertEqual(a["runs"], 2)
        self.assertEqual(a["mechanical"]["found_per_run"], [1, 1])
        self.assertEqual(a["mechanical"]["found_in_all"], ["eval"])
        self.assertEqual(a["cost"]["calls_per_bug_found"], a["cost"]["calls"]["mean"])
        flags = " ".join(s["flags"])
        for needle in ("DEV SET", "very public", "Fewer than 3 runs", "Mechanical scores only"):
            self.assertIn(needle, flags)
        self.assertEqual(s["issues"], 2)

    def test_adjudication_changes_the_numbers_and_leaves_undecided_issues_visible(self):
        s0 = score.summarize(self.es, "raw", self.runs)
        keys = {c["key"] for c in score.adjudication_todo(self.es, "raw", self.runs)["clusters"]}
        eval_key = next(k for k in keys if k.startswith("routes/handler.js"))
        s1 = score.summarize(self.es, "raw", self.runs, {eval_key: {"verdict": "real", "bug": "eval"}})
        adj = s1["arms"]["plain"]["adjudicated"]
        self.assertFalse(adj["complete"])                                    # the second claim has no verdict
        self.assertEqual(adj["found_per_run"], [1, 1])
        self.assertEqual(adj["undecided"], 2)
        self.assertTrue(any("no verdict yet" in f for f in s1["flags"]))
        other = next(k for k in keys if k != eval_key)
        s2 = score.summarize(self.es, "raw", self.runs, {eval_key: {"verdict": "real", "bug": "eval"}, other: {"verdict": "mixed"}})
        adj2 = s2["arms"]["plain"]["adjudicated"]
        self.assertTrue(adj2["complete"])
        self.assertEqual(adj2["precision"]["mean"], 0.5)                     # one real issue, one mixed (counts as wrong)
        self.assertEqual(s2["arms"]["plain"]["cost"]["basis"], "adjudicated")
        self.assertEqual(s0["arms"]["plain"]["cost"]["basis"], "mechanical")

    def test_one_finding_can_be_judged_to_cover_several_known_bugs(self):
        keys = [c["key"] for c in score.adjudication_todo(self.es, "raw", self.runs)["clusters"]]
        eval_key = next(k for k in keys if k.startswith("routes/handler.js"))
        other = next(k for k in keys if k != eval_key)
        s = score.summarize(self.es, "raw", self.runs, {eval_key: {"verdict": "real", "bug": ["eval", "redirect"]},
                                                       other: {"verdict": "false"}})
        self.assertEqual(s["arms"]["plain"]["adjudicated"]["found_per_run"], [2, 2])

    def test_a_mechanical_credit_that_a_person_rejects_is_not_counted(self):
        keys = [c["key"] for c in score.adjudication_todo(self.es, "raw", self.runs)["clusters"]]
        verdicts = {k: {"verdict": "false"} for k in keys}                   # the person says nothing was real
        s = score.summarize(self.es, "raw", self.runs, verdicts)
        self.assertEqual(s["arms"]["plain"]["mechanical"]["found_per_run"], [1, 1])
        self.assertEqual(s["arms"]["plain"]["adjudicated"]["found_per_run"], [0, 0])

    def test_the_todo_file_keeps_verdicts_already_given_and_loads_back_as_a_verdict_file(self):
        todo = score.adjudication_todo(self.es, "raw", self.runs)
        todo["clusters"][0]["verdict"], todo["clusters"][0]["bug"] = "real", "eval"
        p = Path(tempfile.mkdtemp()) / "adjudication-todo.json"
        p.write_text(json.dumps(todo), encoding="utf-8")
        loaded = score.load_adjudication(p)
        self.assertEqual(list(loaded.values()), [{"verdict": "real", "bug": "eval", "note": ""}])
        again = score.adjudication_todo(self.es, "raw", self.runs, loaded)
        self.assertEqual(sum(1 for c in again["clusters"] if c["verdict"]), 1)

    def test_a_run_whose_clock_ran_while_the_machine_slept_shows_call_time_and_says_so(self):
        runs = json.loads(json.dumps(self.runs))
        runs[0]["seconds"]["total"] = 33489.0
        s = score.summarize(self.es, "raw", runs)
        self.assertEqual(s["arms"]["plain"]["clock_anomaly_runs"], [1])
        self.assertLess(s["arms"]["plain"]["cost"]["seconds"]["max"], 100)
        self.assertTrue(any("machine probably slept" in f for f in s["flags"]))

    def test_the_rendered_report_carries_the_table_the_per_bug_matrix_and_the_warnings(self):
        text = score.render(score.summarize(self.es, "raw", self.runs))
        for needle in ("| plain | 2 | 1 of 2 |", "eval on the request body | 2/2", "open redirect | 0/2", "DEV SET",
                       "Estimated tokens are characters / 4"):
            self.assertIn(needle, text)

    def test_the_command_line_reports_from_saved_runs(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = eval_main(["report", "--set", str(self.es.path), "--out", str(self.out)])
        self.assertEqual(code, 0)
        self.assertIn("plain", buf.getvalue())
        self.assertTrue((self.out / "mini__raw" / "summary.md").exists())


if __name__ == "__main__":
    unittest.main()
