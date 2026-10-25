import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from breakpoint.evaluation import advisory, history
from breakpoint.evaluation.advisory import Skip
from breakpoint.evaluation.runner import run_eval
from breakpoint.evaluation.sets import load_set

from tests.test_evaluation import ConfirmAll, Fake, plain_reply, write_set

APP_JS = "\n".join(["const express = require('express');", "const app = express();", "app.get('/run', (req, res) => {",
                    "  const out = eval(req.query.code);", "  res.send(String(out));", "});", ""])


def git(repo: Path, *args: str, date: str | None = None) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout.rstrip("\n")


def make_history(fix_files: dict, base_files: dict | None = None, date: str = "2026-04-01T12:00:00+00:00"):
    """A repository with a parent commit and a fix commit. Returns (path, parent sha, fix sha)."""
    repo = Path(tempfile.mkdtemp(prefix="bp_adv_"))
    git(repo, "init", "-q")
    base = {"src/app.js": APP_JS, "test/app.test.js": "test('x', () => {});\n", "README.md": "hi\n", **(base_files or {})}
    for name, text in base.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "parent", date="2026-01-01T12:00:00+00:00")
    parent = git(repo, "rev-parse", "HEAD")
    for name, text in fix_files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fix", date=date)
    return repo, parent, git(repo, "rev-parse", "HEAD")


def github_for(repo: Path):
    """Stands in for api.github.com, answering from a real local repository: the same commit and tree shapes, real patches."""
    def api_get(url, params=None):
        parts = url.strip("/").split("/")
        if parts[3] == "commits":
            sha = parts[4]
            parents = git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
            files = []
            if parents:
                status = {"A": "added", "M": "modified", "D": "removed"}
                names = dict(l.split("\t", 1)[::-1] for l in git(repo, "diff", "--name-status", "--no-renames", parents[0], sha).splitlines())
                for line in git(repo, "diff", "--numstat", "--no-renames", parents[0], sha).splitlines():
                    add, rem, path = line.split("\t", 2)
                    diff = git(repo, "diff", parents[0], sha, "--", path)
                    files.append({"filename": path, "status": status[names[path]], "additions": int(add), "deletions": int(rem),
                                  "patch": diff[diff.index("@@"):] if "@@" in diff else ""})
            return {"parents": [{"sha": p} for p in parents], "files": files,
                    "commit": {"committer": {"date": git(repo, "show", "-s", "--format=%cI", sha)}}}, None
        if parts[3] == "git" and parts[4] == "trees":
            tree = []
            for line in git(repo, "ls-tree", "-r", "-l", parts[5]).splitlines():
                meta, _, path = line.partition("\t")
                tree.append({"path": path, "type": "blob", "size": int(meta.split()[3])})
            return {"truncated": False, "tree": tree}, None
        raise AssertionError(url)
    return api_get


def advisory_for(sha: str, **over) -> dict:
    adv = {"ghsa_id": "GHSA-aaaa-bbbb-cccc", "summary": "Code injection via eval", "description": "The code parameter reaches eval.",
           "severity": "high", "published_at": "2026-04-02T00:00:00Z", "html_url": "https://github.com/advisories/GHSA-aaaa-bbbb-cccc",
           "source_code_location": "https://github.com/o/r", "cwes": [{"cwe_id": "CWE-94", "name": "x"}],
           "references": [f"https://github.com/o/r/commit/{sha}", "https://example.com/post"],
           "vulnerabilities": [{"package": {"ecosystem": "npm", "name": "pkg"}, "vulnerable_version_range": "< 1.2.0",
                                "first_patched_version": "1.2.0"}]}
    adv.update(over)
    return adv


FIXED = APP_JS.replace("eval(req.query.code)", "JSON.parse(req.query.code)")


class Parsing(unittest.TestCase):
    def test_old_side_ranges_for_replaced_deleted_and_added_lines(self):
        patch = ("@@ -2,6 +2,5 @@\n a\n b\n-old\n+new\n c\n d\n"            # one line replaced: old line 4
                 "@@ -20,6 +19,3 @@\n e\n-x\n-y\n-z\n+w\n f\n g\n"            # three lines replaced by one: old lines 21 to 23
                 "@@ -40,3 +37,4 @@\n h\n i\n+added\n j\n")                   # only an insertion, after old line 41
        self.assertEqual(advisory.old_ranges(patch), [(4, 4, False), (21, 23, False), (41, 41, True)])

    def test_an_insertion_at_the_top_of_a_file_is_anchored_on_line_one(self):
        self.assertEqual(advisory.old_ranges("@@ -0,0 +1,3 @@\n+a\n+b\n+c\n"), [(1, 1, True)])

    def test_blank_line_changes_are_formatting_not_part_of_the_fix(self):
        patch = "@@ -5,5 +5,4 @@\n a\n-\n b\n c\n@@ -30,4 +29,5 @@\n d\n+\n e\n@@ -50,3 +50,3 @@\n f\n-old\n+new\n g\n"
        self.assertEqual(advisory.old_ranges(patch), [(51, 51, False)])

    def test_blank_lines_replaced_by_code_count_as_an_insertion_before_them(self):
        self.assertEqual(advisory.old_ranges("@@ -7,4 +7,4 @@\n a\n-\n+check()\n b\n"), [(7, 7, True)])

    def test_a_removed_line_that_starts_with_dashes_is_still_a_removed_line(self):
        self.assertEqual(advisory.old_ranges("@@ -1,2 +1,1 @@\n--- sql comment\n keep\n"), [(1, 1, False)])

    def test_nearby_ranges_merge_and_distant_ones_do_not(self):
        got = advisory.merge_ranges([(4, 4, False), (6, 7, False), (30, 31, True)])
        self.assertEqual(got, [(4, 7, False), (30, 31, True)])

    def test_only_full_commit_urls_in_the_references_count_and_duplicates_collapse(self):
        sha = "a" * 40
        adv = {"references": [f"https://github.com/O/R/commit/{sha}", f"https://github.com/o/r/commit/{sha}/",
                              "https://github.com/o/r/commit/abc1234", "https://github.com/o/r/pull/9", None]}
        self.assertEqual(advisory.fix_commits(adv), [("O", "R", sha)])

    def test_class_comes_from_the_first_known_cwe_and_unknown_ones_are_other(self):
        self.assertEqual(advisory.advisory_class({"cwes": [{"cwe_id": "CWE-1"}, {"cwe_id": "CWE-79"}]}), ("xss", "CWE-79"))
        self.assertEqual(advisory.advisory_class({"cwes": [{"cwe_id": "CWE-1"}]}), ("other", "CWE-1"))
        self.assertEqual(advisory.advisory_class({"cwes": []}), ("other", ""))

    def test_the_walk_order_depends_on_the_seed_and_the_id_only(self):
        advs = [{"ghsa_id": f"GHSA-{i}"} for i in range(20)]
        a = [x["ghsa_id"] for x in advisory.shuffled(advs, "s1")]
        self.assertEqual(a, [x["ghsa_id"] for x in advisory.shuffled(list(reversed(advs)), "s1")])
        self.assertNotEqual(a, [x["ghsa_id"] for x in advisory.shuffled(advs, "s2")])

    def test_tests_docs_and_vendored_files_are_not_source(self):
        for path in ("src/app.js", "lib/auth.py", "views/page.html"):
            self.assertTrue(advisory.is_source(path), path)
        for path in ("test/app.test.js", "docs/guide.md", "README.md", "package.json", "node_modules/x/index.js", "src/app.min.js"):
            self.assertFalse(advisory.is_source(path), path)


class FixCommits(unittest.TestCase):
    def inspect(self, repo, sha, **kw):
        with mock.patch.object(advisory, "api_get", github_for(repo)):
            return advisory.inspect_fix("o", "r", sha, **kw)

    def test_a_replaced_line_is_labelled_where_it_was(self):
        repo, parent, sha = make_history({"src/app.js": FIXED, "test/app.test.js": "test('y', () => {});\n"})
        info = self.inspect(repo, sha)
        self.assertEqual(info["parent"], parent)
        self.assertEqual(info["locations"], [{"file": "src/app.js", "lines": [4, 4]}])
        self.assertFalse(info["addition_only"])
        self.assertEqual((info["other_files_changed"], info["source_files_changed"]), (1, ["src/app.js"]))

    def test_a_fix_that_only_adds_a_check_is_labelled_on_the_line_before_and_says_so(self):
        lines = APP_JS.split("\n")
        lines.insert(3, "  if (!req.user) return res.sendStatus(401);")
        repo, _, sha = make_history({"src/app.js": "\n".join(lines)})
        info = self.inspect(repo, sha)
        self.assertEqual(info["locations"], [{"file": "src/app.js", "lines": [3, 3]}])
        self.assertTrue(info["addition_only"])

    def test_a_fix_that_touches_only_tests_or_docs_cannot_make_a_set(self):
        repo, _, sha = make_history({"test/app.test.js": "test('z', () => {});\n", "README.md": "changed\n"})
        with self.assertRaises(Skip) as cm:
            self.inspect(repo, sha)
        self.assertEqual(cm.exception.reason, "no_source_change")

    def test_a_large_fix_is_skipped(self):
        repo, _, sha = make_history({"src/app.js": APP_JS + "\n".join(f"const v{i} = {i};" for i in range(100)) + "\n"})
        with self.assertRaises(Skip) as cm:
            self.inspect(repo, sha)
        self.assertEqual(cm.exception.reason, "fix_too_large")

    def test_a_fix_that_only_creates_a_file_has_nothing_to_label(self):
        repo, _, sha = make_history({"src/guard.js": "module.exports = () => true;\n"})
        with self.assertRaises(Skip) as cm:
            self.inspect(repo, sha)
        self.assertEqual(cm.exception.reason, "no_old_lines")

    def test_a_repository_too_big_for_one_prompt_is_skipped_before_any_model_sees_it(self):
        repo, _, sha = make_history({"src/app.js": FIXED})
        with self.assertRaises(Skip) as cm:
            self.inspect(repo, sha, max_source_bytes=50)
        self.assertEqual(cm.exception.reason, "source_too_big_for_one_prompt")

    def test_a_merge_commit_is_not_a_fix(self):
        repo, parent, _ = make_history({"src/app.js": FIXED})
        git(repo, "checkout", "-q", "-b", "side", parent)
        (repo / "src" / "other.js").write_text("module.exports = 1;\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "side")
        git(repo, "checkout", "-q", "-")
        git(repo, "merge", "-q", "--no-ff", "-m", "merge", "side")
        with self.assertRaises(Skip) as cm:
            self.inspect(repo, git(repo, "rev-parse", "HEAD"))
        self.assertEqual(cm.exception.reason, "merge_or_root_commit")


class Building(unittest.TestCase):
    def setUp(self):
        self.repo, self.parent, self.sha = make_history({"src/app.js": FIXED})

    def build(self, adv=None, repo=None, **kw):
        with mock.patch.object(advisory, "api_get", github_for(repo or self.repo)):
            return advisory.build_set(adv or advisory_for(self.sha), **kw)

    def test_the_set_pins_the_parent_labels_the_fix_and_loads_in_the_harness(self):
        data = self.build()
        self.assertEqual((data["id"], data["role"]), ("ghsa-aaaa-bbbb-cccc", "heldout"))
        self.assertEqual(data["repo"], {"url": "https://github.com/o/r", "commit": self.parent, "partial": True})
        bug = data["bugs"][0]
        self.assertEqual((bug["class"], bug["cwe"]), ("injection", "CWE-94"))
        self.assertEqual(bug["locations"], [{"file": "src/app.js", "lines": [4, 4]}])
        self.assertEqual(data["language"], "javascript")
        h = data["history"]
        self.assertEqual((h["fix_commit"], h["package"], h["patched"], h["label_review"]), (self.sha, "pkg", "1.2.0", "not reviewed"))
        self.assertIn("after the 2026-03-03 release", data["contamination"])
        p = Path(tempfile.mkdtemp()) / "set.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        es = load_set(str(p))
        self.assertEqual((es.bugs[0].id, es.history["advisory"]), ("ghsa-aaaa-bbbb-cccc", "GHSA-aaaa-bbbb-cccc"))

    def test_a_fix_made_before_the_model_existed_is_refused_even_if_the_advisory_is_new(self):
        repo, _, sha = make_history({"src/app.js": FIXED}, date="2025-06-01T00:00:00+00:00")
        with self.assertRaises(Skip) as cm:
            self.build(advisory_for(sha), repo)
        self.assertEqual(cm.exception.reason, "fix_before_cutoff")

    def test_an_old_advisory_is_refused_without_asking_github_anything_else(self):
        with mock.patch.object(advisory, "api_get", side_effect=AssertionError("must not call")), self.assertRaises(Skip) as cm:
            advisory.build_set(advisory_for(self.sha, published_at="2025-02-01T00:00:00Z"))
        self.assertEqual(cm.exception.reason, "advisory_before_cutoff")

    def test_unclear_advisories_are_skipped_with_a_reason(self):
        other = "b" * 40
        cases = {"no_fix_commit_in_references": advisory_for(self.sha, references=["https://example.com"]),
                 "fix_commit_in_another_repository": advisory_for(self.sha, references=[f"https://github.com/x/y/commit/{self.sha}"]),
                 "several_fix_commits": advisory_for(self.sha, references=[f"https://github.com/o/r/commit/{self.sha}",
                                                                           f"https://github.com/o/r/commit/{other}"]),
                 "no_github_source_location": advisory_for(self.sha, source_code_location="https://gitlab.com/o/r")}
        for reason, adv in cases.items():
            with self.assertRaises(Skip) as cm:
                self.build(adv)
            self.assertEqual(cm.exception.reason, reason)


class Harvesting(unittest.TestCase):
    def test_every_advisory_considered_is_logged_in_a_fixed_order_and_a_rerun_changes_nothing(self):
        advs = [{"ghsa_id": f"GHSA-{i:04d}", "published_at": "2026-05-01T00:00:00Z"} for i in range(6)]

        def fake_build(adv, **kw):
            if adv["ghsa_id"].endswith(("1", "3")):
                raise Skip("no_fix_commit_in_references")
            return {"id": adv["ghsa_id"].lower(), "history": {"package": "p"}, "bugs": [{"class": "xss", "locations": [{}]}]}

        out = Path(tempfile.mkdtemp())
        with mock.patch.object(advisory, "list_advisories", lambda eco, sev, since, cap=600: advs if sev == "high" else []), \
                mock.patch.object(advisory, "build_set", fake_build):
            rec = advisory.harvest(["npm"], "2026-03-10", 3, "seed", out, log=lambda *_: None)
            again = advisory.harvest(["npm"], "2026-03-10", 3, "seed", out, log=lambda *_: None)
        order = [a["ghsa_id"] for a in advisory.shuffled(advs, "seed")]
        walked = [c["advisory"] for c in rec["considered"]]
        self.assertEqual(walked, order[:len(walked)])
        self.assertEqual(len(rec["kept"]), 3)
        self.assertTrue(all(c["outcome"] == "skipped" and c["reason"] for c in rec["considered"] if c["advisory"].endswith(("1", "3"))))
        self.assertEqual(rec["kept"], again["kept"])
        self.assertEqual(json.loads((out / "selection.json").read_text(encoding="utf-8"))["parameters"]["seed"], "seed")
        self.assertEqual(sorted(p.parent.name for p in out.glob("*/set.json")), sorted(k.lower() for k in rec["kept"]))

    def test_a_network_error_on_one_advisory_is_logged_and_the_walk_goes_on(self):
        advs = [{"ghsa_id": "GHSA-0001", "published_at": "2026-05-01T00:00:00Z"}, {"ghsa_id": "GHSA-0002", "published_at": "2026-05-01T00:00:00Z"}]

        def fake_build(adv, **kw):
            if adv["ghsa_id"] == "GHSA-0001":
                raise RuntimeError("GitHub API answered 502")
            return {"id": adv["ghsa_id"].lower(), "history": {"package": "p"}, "bugs": [{"class": "xss", "locations": [{}]}]}

        out = Path(tempfile.mkdtemp())
        with mock.patch.object(advisory, "list_advisories", lambda eco, sev, since, cap=600: advs if sev == "high" else []), \
                mock.patch.object(advisory, "build_set", fake_build):
            rec = advisory.harvest(["npm"], "2026-03-10", 5, "seed", out, log=lambda *_: None)
        self.assertEqual(rec["kept"], ["GHSA-0002"])
        self.assertIn(("GHSA-0001", "error"), [(c["advisory"], c.get("reason")) for c in rec["considered"]])


class HistoryTable(unittest.TestCase):
    def setUp(self):
        self.path = write_set(history={"advisory": "GHSA-x", "package": "mini-pkg", "label_review": "not reviewed"})
        self.es = load_set(str(self.path))
        self.out, self.cache = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        run_eval(self.es, "raw", ["plain"], 2, self.out, self.cache, llm=Fake(baseline=plain_reply()), verifier_factory=ConfirmAll,
                 log=lambda *_: None)

    def test_the_table_says_whether_the_flaw_was_proposed_and_kept_and_what_is_not_yet_read(self):
        s = history.summarize_history([self.es], self.out)
        row = s["rows"][0]
        self.assertEqual((row["runs"], row["proposed"], row["kept_mechanical"]), (2, 2, [1, 1]))
        self.assertIsNone(row["kept_adjudicated"])
        text = history.render(s, [self.es])
        self.assertIn("mini-pkg", text)
        self.assertIn("1 of 1 sets have a label nobody has checked", text)
        self.assertIn("location match 2/2", text)
        self.assertIn("not yet read by a person", text)

    def test_a_persons_verdicts_on_what_was_proposed_are_counted_strictly_and_leniently(self):
        (self.out / "proposed_read.json").write_text(json.dumps({"mini": {"verdicts": ["Y", "P"]}}), encoding="utf-8")
        s = history.summarize_history([self.es], self.out)
        self.assertEqual(s["rows"][0]["read"], {"yes": 1, "partial": 1, "no": 0, "unread": 0})
        self.assertEqual(s["totals"]["read"], {"sets": 1, "runs": 2, "yes": 1, "partial": 1, "sets_with_yes": 1, "sets_with_yes_or_partial": 1})
        text = history.render(s, [self.es])
        self.assertIn("strict), and described it or was in the right place and class in 2/2", text)
        self.assertIn("a candidate described the advisory's flaw in 1/2 runs", text)

    def test_runs_without_a_verdict_are_not_counted_as_misses(self):
        (self.out / "proposed_read.json").write_text(json.dumps({"mini": {"verdicts": ["N"]}}), encoding="utf-8")   # run 2 has none
        s = history.summarize_history([self.es], self.out)
        self.assertEqual(s["rows"][0]["read"]["unread"], 1)
        self.assertIsNone(s["totals"]["read"])                    # a set with an unread run is left out of the read totals

    def test_a_run_saved_before_candidates_were_recorded_has_no_proposed_figure(self):
        for f in (self.out / "mini__raw" / "plain").glob("run_*.json"):
            rec = json.loads(f.read_text(encoding="utf-8"))
            rec.pop("proposed")
            f.write_text(json.dumps(rec), encoding="utf-8")
        row = history.summarize_history([self.es], self.out)["rows"][0]
        self.assertIsNone(row["proposed"])

    def test_a_proposal_the_check_threw_away_is_visible_as_proposed_but_not_kept(self):
        class RejectAll(ConfirmAll):
            def __call__(self, findings):
                self.n = len(findings)
                return [{"status": "REFUTED", "code": "defence_found", "evidence_items": []} for _ in findings]

        out = Path(tempfile.mkdtemp())
        run_eval(self.es, "raw", ["plain"], 1, out, self.cache, llm=Fake(baseline=plain_reply()), verifier_factory=RejectAll,
                 log=lambda *_: None)
        row = history.summarize_history([self.es], out)["rows"][0]
        self.assertEqual((row["proposed"], row["kept_mechanical"]), (1, [0]))
        rec = json.loads(next((out / "mini__raw" / "plain").glob("run_1.json")).read_text(encoding="utf-8"))
        self.assertEqual(rec["proposed"][0]["outcome"], "REFUTED:defence_found")

    def test_sets_without_runs_are_listed_as_not_run(self):
        s = history.summarize_history([self.es], Path(tempfile.mkdtemp()))
        self.assertEqual((s["rows"], s["not_run"]), ([], ["mini"]))


if __name__ == "__main__":
    unittest.main()
