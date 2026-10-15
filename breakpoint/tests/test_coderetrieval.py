import json
import os
import unittest
from unittest import mock

from breakpoint.baseline import build_baseline, source_block
from breakpoint.codeindex import CodeIndex
from breakpoint.coderetrieval import CodeRetriever, check_refs, file_weight, markup_code_mask
from breakpoint.codeverify import CONFIRMED, UNVERIFIED, CodeVerifier
from breakpoint.evolution import _assign_categories, _render_prior, simulate
from breakpoint.models import Agent, Blueprint, Finding

from .test_codeindex import make_repo
from .test_codeverify import ScriptedLLM, ev, finding, locate

EVAL_LINE = "const preTax = eval(req.body.preTax);"
REDIRECT_LINE = "return res.redirect(req.query.url);"
WHERE_LINE = "$where: `this.userId == ${parsedUserId} && this.stocks > '${threshold}'`"
LOGIN_LINE = "req.session.userId = user._id;"
SECRET_LINE = 'cookieSecret: "session_cookie_secret_key_here",'

REPO = {
    "server.js": (
        "const session = require('express-session');\n"
        "app.use(session({\n"
        "    secret: cookieSecret,\n"
        "    saveUninitialized: true,\n"
        "    resave: true\n"
        "    /*\n"
        "    cookie: {\n"
        "        httpOnly: true\n"
        "    }\n"
        "    */\n"
        "}));\n"
        "// app.use(csrf());\n"
        "swig.setDefaults({ autoescape: false });\n"
    ),
    "app/routes/contributions.js": "function handle(req, res) {\n    " + EVAL_LINE + "\n    return res.render('c', { preTax });\n}\n",
    "app/routes/index.js": ("app.get('/learn', isLoggedIn, (req, res) => {\n    " + REDIRECT_LINE + "\n});\n"
                            "app.get('/benefits', isLoggedIn, benefits.display);\n"
                            "/* app.get('/benefits', isLoggedIn, isAdmin, benefits.display); */\n"),
    "app/routes/session.js": ("function login(req, res) {\n    // req.session.regenerate(() => {})\n    " + LOGIN_LINE + "\n    res.redirect('/dashboard');\n}\n"),
    "app/data/allocations-dao.js": "const criteria = () => {\n    return {\n        " + WHERE_LINE + "\n    };\n};\n",
    "config/env/all.js": "module.exports = {\n    " + SECRET_LINE + "\n    port: 4000\n};\n",
    "app/views/profile.html": "<form method=\"post\">\n  <input type=\"hidden\" name=\"_csrf\" value=\"{{csrftoken}}\">\n</form>\n",
    "app/views/tutorial/a1.html": ("<p>Never call <code>eval()</code> on input.</p>\n<pre>\nconst x = eval(req.body.q);\nres.redirect(req.query.next);\n</pre>\n"),
    "assets/vendor/jquery.js": "function a(s){ return eval(s); }\n" * 30,
    "test/e2e/login_spec.js": "it('x', () => { eval(req.body.zzz); });\n",
    ".env": "SESSION_SECRET=sk_live_1234567890abcdefghij\neval(req.body.fromenv)\n",
}


def shown(retrieval) -> str:
    return retrieval.text


class WhatEachCategoryGets(unittest.TestCase):
    def setUp(self):
        self.idx = CodeIndex.from_dir(make_repo(REPO))
        self.r = CodeRetriever(self.idx)

    def test_an_injection_agent_is_shown_the_dangerous_operations_with_true_line_numbers(self):
        text = shown(self.r.retrieve("injection"))
        for line in (EVAL_LINE, REDIRECT_LINE, WHERE_LINE):
            self.assertIn(line, text)
        self.assertIn("    2|     " + EVAL_LINE, text)                      # real line number from the file

    def test_other_categories_are_steered_to_their_own_code(self):
        self.assertIn(SECRET_LINE, shown(self.r.retrieve("crypto")))
        self.assertIn(LOGIN_LINE, shown(self.r.retrieve("auth")))
        config = shown(self.r.retrieve("config"))
        self.assertIn("app.use(session({", config)
        self.assertIn("autoescape: false", config)

    def test_third_party_test_and_secret_files_are_never_shown(self):
        for cat in ("injection", "auth", "config", "crypto", "authz"):
            text = shown(self.r.retrieve(cat))
            self.assertNotIn("vendor/jquery.js", text, cat)
            self.assertNotIn("zzz", text, cat)
            self.assertNotIn("fromenv", text, cat)
            self.assertNotIn("sk_live", text, cat)

    def test_code_printed_on_a_page_is_documentation_not_code(self):
        for cat in ("injection", "auth"):
            text = shown(self.r.retrieve(cat))
            self.assertNotIn("a1.html", text)
        self.assertEqual(markup_code_mask(["<p>text</p>", "<pre>", "eval(x)", "</pre>", "<script>", "var a = 1;", "</script>", "{{ name }}"]),
                         [False, False, False, False, True, True, True, True])
        self.assertEqual(file_weight("assets/vendor/jquery.js"), 0.0)
        self.assertLess(file_weight("test/e2e/login_spec.js"), file_weight("app/routes/index.js"))

    def test_comment_lines_are_marked_so_a_fix_that_is_only_a_comment_is_not_mistaken_for_code(self):
        text = shown(self.r.retrieve("config"))
        self.assertRegex(text, r"\n\s*\d+c\| +httpOnly: true")
        self.assertRegex(text, r"\n\s*\d+c\| +// app.use\(csrf\(\)\);")

    def test_commented_out_code_ranks_below_live_code_even_when_it_looks_scarier(self):
        r = CodeRetriever(CodeIndex.from_dir(make_repo({
            "old.js": "// const v = eval(req.body.a);\n",
            "live.js": "function go(req, res) {\n    return res.redirect(req.query.u);\n}\n"})))
        order = [x.path for x in r.regions["injection"]]
        self.assertEqual(order[0], "live.js")
        self.assertIn("old.js", order)                                           # still available, just later

    def test_the_control_search_separates_server_code_templates_and_comments(self):
        text = shown(self.r.retrieve("config"))
        self.assertIn("httpOnly cookie flag -> server code: NONE | commented out (NOT active): server.js:8", text)
        auth = shown(self.r.retrieve("auth"))
        # the token appears in a template and in a comment, never in server code: exactly the "rendered but not enforced" case
        self.assertRegex(auth, r"CSRF protection -> server code: NONE \| templates: app/views/profile.html:2 \| commented out \(NOT active\): server.js:12")
        self.assertIn("session id regenerated -> server code: NONE | commented out (NOT active): app/routes/session.js:2", auth)

    def test_the_budget_is_respected(self):
        small = CodeRetriever(self.idx, budget_chars=1500, whole_file_chars=300)
        self.assertLess(len(small.retrieve("injection").text), 4500)


class WhoLooksAtWhat(unittest.TestCase):
    def setUp(self):
        files = {f"app/routes/handler{i}.js": f"function h{i}(req, res) {{\n    const v = eval(req.body.field{i});\n    res.send(v);\n}}\n"
                 for i in range(8)}
        self.idx = CodeIndex.from_dir(make_repo(files))
        self.r = CodeRetriever(self.idx, budget_chars=2600, whole_file_chars=100, max_regions=3)

    def test_agents_sharing_a_category_are_given_different_code(self):
        first, second = self.r.assign(["injection", "injection"], [])
        a, b = {x.key for x in first.regions}, {x.key for x in second.regions}
        self.assertTrue(a and b)
        self.assertEqual(len(a & b), 0)

    def test_code_an_earlier_agent_already_read_is_shown_later_only_after_fresh_code(self):
        first = self.r.assign(["injection"], [])[0]
        later = self.r.assign(["injection"], [])[0]
        self.assertEqual(len({x.path for x in first.regions} & {x.path for x in later.regions}), 0)

    def test_code_that_a_verified_finding_points_at_is_shown_less(self):
        top = self.r.retrieve("injection").regions[0]
        done = Finding(title="t", generation=1, discovered_by="a", description="d",
                       evidence=[{"file": top.path, "line": 2, "quote": "x"}])
        after = self.r.retrieve("injection", covered=self.r._covered([done])).regions
        self.assertNotEqual(after[0].path, top.path)

    def test_categories_follow_the_code_not_a_fixed_list(self):
        plan = CodeRetriever(CodeIndex.from_dir(make_repo(REPO))).plan_categories(10, [])
        self.assertEqual(len(plan), 10)
        for cat in ("injection", "auth", "config"):
            self.assertIn(cat, plan)
        self.assertNotIn("billing", plan)               # the repository has nothing for it
        self.assertNotIn("supply_chain", plan)

    def test_a_category_cannot_get_more_agents_than_it_has_separate_code_for(self):
        r = CodeRetriever(CodeIndex.from_dir(make_repo({"a.js": "x = eval(req.body.a);\n"})))
        plan = r.plan_categories(4, [])
        self.assertEqual(plan.count("injection"), 1)
        self.assertEqual(len(plan), 4)                   # the rest fall back to the plain rotation

    def test_findings_in_a_category_use_up_its_room(self):
        r = CodeRetriever(CodeIndex.from_dir(make_repo(REPO)))
        before = r.room("injection", [])
        pts = [Finding(title="t", generation=1, discovered_by="a", description="d",
                       evidence=[{"file": "app/routes/contributions.js", "line": 2, "quote": "q"}])]
        self.assertEqual(r.room("injection", pts), before - 1)

    def test_with_no_code_leads_at_all_the_old_rotation_is_used(self):
        r = CodeRetriever(CodeIndex.from_dir(make_repo({"README.md": "hello\n"})))
        self.assertEqual(len(r.plan_categories(5, [])), 5)
        self.assertFalse(r.retrieve("injection"))

    def test_assign_categories_uses_the_retriever_only_when_given_one(self):
        agents = [Agent(name=str(i), archetype="A", age=1, backstory="", motivation="", goal="") for i in range(3)]
        self.assertEqual(_assign_categories(agents, []), ["auth", "authz", "rate_limiting"])         # unchanged without code
        self.assertEqual(_assign_categories(agents, [], self.r), self.r.plan_categories(3, []))


class Citations(unittest.TestCase):
    def setUp(self):
        self.idx = CodeIndex.from_dir(make_repo(REPO))

    def test_a_real_quote_gets_its_true_line_number(self):
        out = check_refs(self.idx, [{"file": "app/routes/contributions.js", "line": 40, "quote": EVAL_LINE}])
        self.assertEqual(out, [{"file": "app/routes/contributions.js", "line": 2, "quote": EVAL_LINE}])

    def test_invented_misplaced_or_commented_citations_are_dropped(self):
        refs = [{"file": "app/routes/contributions.js", "line": 2, "quote": "const total = unsafeEval(req.body.total);"},
                {"file": "nope/ghost.js", "line": 1, "quote": EVAL_LINE},
                {"file": "app/routes/session.js", "line": 2, "quote": "// req.session.regenerate(() => {})"},
                {"file": "app/routes/contributions.js", "line": 2},
                "not a dict", {"file": 5, "quote": 5}]
        self.assertEqual(check_refs(self.idx, refs), [])
        self.assertEqual(check_refs(self.idx, None), [])
        self.assertEqual(check_refs(self.idx, "nonsense"), [])

    def test_a_citation_is_a_hint_for_the_verifier_never_a_pass(self):
        """The agent cited a real file, so the judge is shown it; the judge's quote is still checked and the claim fails without one."""
        f = finding("Something about the redirect", "the thing", code_refs=[{"file": "app/routes/index.js", "line": 2, "quote": REDIRECT_LINE}])
        llm = ScriptedLLM(verify_locate=locate([], []), verify_judge={
            "verdict": "CONFIRMED", "impact_follows": True, "reasoning": "r",
            "evidence": [ev("app/routes/index.js", "return res.redirectUnsafe(req.query.target);")]})
        v = CodeVerifier(self.idx, llm)
        r = v.check(f)
        self.assertIn(REDIRECT_LINE, llm.prompts("verify_judge")[0])           # the cited file reached the judge
        self.assertEqual(r["status"], UNVERIFIED)                              # but an invented quote is still no evidence

    def test_a_cited_file_alone_does_not_skip_the_defender(self):
        f = finding("Open redirect", "d", code_refs=[{"file": "app/routes/index.js", "line": 2, "quote": REDIRECT_LINE}])
        llm = ScriptedLLM(verify_locate=locate([], []), verify_judge={
            "verdict": "CONFIRMED", "impact_follows": True, "reasoning": "r", "evidence": [ev("app/routes/index.js", REDIRECT_LINE)]},
            verify_defend={"defence_found": True, "reasoning": "allow-list", "evidence": [ev("app/routes/index.js", "app.get('/benefits', isLoggedIn, benefits.display);")]})
        self.assertEqual(CodeVerifier(self.idx, llm).check(f)["code"], "defence_found")


class AgentPrompts(unittest.TestCase):
    TITLES = ["Eval of contribution amounts", "Open redirect on learn", "Where injection in allocations", "Fixed session secret",
              "Session fixation on login", "Cookie flags missing", "Admin page open to all", "Plain passwords", "Zebra", "Quokka"]

    def make(self, with_retriever=True, verifier=None, gens=1):
        idx = CodeIndex.from_dir(make_repo(REPO))
        retriever = CodeRetriever(idx) if with_retriever else None
        n = {"i": 0}

        def agent_reply(user):
            n["i"] += 1
            return {"title": self.TITLES[(n["i"] - 1) % len(self.TITLES)] + f" {n['i']}", "description": "d", "steps_to_exploit": ["s"],
                    "attack_category": "injection", "exploitability": 5, "impact_score": 5, "spread": 5, "fix_difficulty": 1,
                    "code_refs": [{"file": "app/routes/contributions.js", "line": 1, "quote": EVAL_LINE},
                                  {"file": "app/routes/contributions.js", "line": 1, "quote": "made up code that is not there"}]}

        llm = ScriptedLLM(finding_gen1=agent_reply, finding_gen2=agent_reply, finding_gen3=agent_reply,
                          crossover={"name": "Kid", "age": 30, "backstory": "b", "motivation": "m", "goal": "g"})
        agents = [Agent(name=f"A{i}", archetype="A", age=30, backstory="b", motivation="m", goal="g") for i in range(4)]
        found = simulate(Blueprint(name="X", type="app", domain="d", stage="live"), agents, llm, generations=gens,
                         verifier=verifier, retriever=retriever)
        return found, llm

    def test_every_agent_reads_real_code_for_its_assigned_category(self):
        found, llm = self.make()
        prompts = llm.prompts("finding_gen1")
        self.assertEqual(len(prompts), 4)
        for p in prompts:
            self.assertIn("THE REAL SOURCE CODE", p)
            self.assertIn("RETRIEVED FOR YOUR ASSIGNED CATEGORY", p)
            self.assertIn("CONTROL SEARCH", p) if "'injection'" in p or "'config'" in p or "'auth'" in p else None
            self.assertIn("code_refs", p)
        assigned = {p.split("You MUST set attack_category to \"")[1].split("\"")[0] for p in prompts}
        self.assertGreaterEqual(len(assigned), 2)                                # not everyone is sent to the same angle
        injection = next(p for p in prompts if 'attack_category to "injection"' in p)
        self.assertIn(EVAL_LINE, injection)

    def test_citations_are_checked_and_only_real_ones_are_kept(self):
        found, _ = self.make()
        self.assertTrue(found)
        for f in found:
            self.assertEqual(f.code_refs, [{"file": "app/routes/contributions.js", "line": 2, "quote": EVAL_LINE}])

    def test_without_a_retriever_nothing_changes(self):
        found, llm = self.make(with_retriever=False)
        for p in llm.prompts("finding_gen1"):
            self.assertNotIn("REAL SOURCE CODE", p)
            self.assertNotIn("CONTROL SEARCH", p)
        self.assertTrue(all(f.code_refs == [] for f in found))

    def test_a_finding_still_has_to_pass_the_verifier_whatever_it_cites(self):
        seen = []

        def verifier(batch):
            seen.extend(batch)
            return [{"ok": False, "evidence": "NOT CONFIRMED IN THE CODE: nothing"} for _ in batch]

        found, llm = self.make(verifier=verifier)
        self.assertEqual(found, [])
        self.assertEqual(len(seen), 4)

    def test_later_generations_are_told_where_verified_findings_live_and_get_unread_code(self):
        def verifier(batch):
            return [{"ok": True, "evidence": "e", "status": "CONFIRMED",
                     "evidence_items": [{"file": "app/routes/contributions.js", "line": 2, "quote": EVAL_LINE}]} for _ in batch]

        found, llm = self.make(verifier=verifier, gens=2)
        gen2 = "\n".join(llm.prompts("finding_gen2"))
        self.assertIn("[code: app/routes/contributions.js:2]", gen2)
        self.assertIn("THE REAL SOURCE CODE", gen2)
        self.assertIn("is not already in the list of earlier findings", gen2)     # the fall-back when no real chain exists

    def test_render_prior_has_no_code_tag_for_unverified_findings(self):
        f = Finding(title="Some bug", generation=1, discovered_by="a", description="desc")
        self.assertNotIn("[code:", _render_prior([f], with_code=True))

    def test_the_code_tag_appears_only_in_retrieval_mode_so_no_retrieval_is_the_old_behaviour(self):
        f = Finding(title="Some bug", generation=1, discovered_by="a", description="desc",
                    evidence=[{"file": "a.js", "line": 3, "quote": "q"}])
        self.assertIn("[code: a.js:3]", _render_prior([f], with_code=True))
        self.assertNotIn("[code:", _render_prior([f]))


class SinglePromptBaseline(unittest.TestCase):
    def test_the_baseline_sees_the_apps_own_source_numbered_and_nothing_secret_or_third_party(self):
        idx = CodeIndex.from_dir(make_repo(REPO))
        text, meta = source_block(idx)
        self.assertIn("    2|     " + EVAL_LINE, text)
        self.assertRegex(text, r"\d+c\| +httpOnly: true")
        for forbidden in ("vendor/jquery.js", "sk_live", "fromenv", "zzz"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(meta["left_out"], [])

    def test_files_that_do_not_fit_are_reported_not_silently_cut(self):
        idx = CodeIndex.from_dir(make_repo(REPO))
        text, meta = source_block(idx, max_chars=300)
        self.assertTrue(meta["left_out"])
        self.assertLessEqual(len(text), 300)

    def test_claims_are_saved_in_the_shape_verify_report_reads_with_checked_citations(self):
        class Fake(ScriptedLLM):
            provider, model = "fake", "fake-1"

        reply = [{"title": "Eval on contributions", "attack_category": "injection", "description": "eval of body",
                  "steps_to_exploit": ["post a payload"], "impact": "RCE",
                  "code_refs": [{"file": "app/routes/contributions.js", "line": 9, "quote": EVAL_LINE},
                                {"file": "app/routes/contributions.js", "line": 9, "quote": "invented"}]},
                 {"description": "has no title, dropped"}, "garbage"]
        llm = Fake(baseline=reply)
        root = make_repo(REPO)
        data = build_baseline(root, llm, n=15)
        self.assertEqual(len(data["findings"]), 1)
        self.assertEqual(data["findings"][0]["code_refs"], [{"file": "app/routes/contributions.js", "line": 2, "quote": EVAL_LINE}])
        self.assertEqual(data["baseline"]["requested"], 15)
        self.assertIn("EVAL", llm.prompts("baseline")[0].upper())
        self.assertIn("15 most serious", llm.prompts("baseline")[0])
        from breakpoint.run import _finding_from_dict
        self.assertEqual(_finding_from_dict(data["findings"][0]).title, "Eval on contributions")

    def test_the_blueprint_context_is_the_old_thirty_five_by_five_thousand_sample(self):
        class Fake(ScriptedLLM):
            provider, model = "fake", "fake-1"

        llm = Fake(baseline=[{"title": "t", "description": "d"}])
        build_baseline(make_repo(REPO), llm, context="blueprint")
        self.assertIn("--- FILE:", llm.prompts("baseline")[0])


class WholePipeline(unittest.TestCase):
    """run._pipeline in codebase mode, with every model call scripted."""

    def run_pipeline(self, retrieval=True):
        from breakpoint import run as runmod

        class Fake(ScriptedLLM):
            provider, model, max_workers = "fake", "fake-1", 1

        n = {"i": 0}

        def agent_reply(user):
            n["i"] += 1
            return {"title": f"Eval number {n['i']}", "description": "eval of the body", "steps_to_exploit": ["s"], "attack_category": "injection",
                    "exploitability": 5, "impact_score": 5, "spread": 5, "fix_difficulty": 1,
                    "code_refs": [{"file": "app/routes/contributions.js", "line": 2, "quote": EVAL_LINE}]}

        persona = {"name": "P", "age": 30, "backstory": "b", "motivation": "m", "goal": "g"}
        blueprint = {"name": "Mini", "type": "web", "domain": "d", "stage": "live", "actors": [], "attack_surface": []}
        llm = Fake(blueprint_codebase=blueprint, brain_pass={}, agent=persona, product_agents=persona,
                   finding_gen1=agent_reply, finding_gen2=agent_reply,
                   crossover=persona, verify_locate=locate([], []),
                   verify_judge={"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "eval of input",
                                 "evidence": [ev("app/routes/contributions.js", EVAL_LINE)]},
                   verify_defend={"defence_found": False, "evidence": []})
        root = make_repo(REPO)
        with mock.patch.object(runmod, "LLMClient", lambda: llm):
            bp, findings, stats = runmod._pipeline(None, 2, 4, 0, False, codebase=root, retrieval=retrieval)
        return llm, findings, stats

    def test_codebase_runs_give_agents_code_and_still_verify_everything(self):
        llm, findings, stats = self.run_pipeline()
        self.assertTrue(all("THE REAL SOURCE CODE" in p for p in llm.prompts("finding_gen1")))
        self.assertTrue(findings)
        self.assertTrue(all(f.verification == CONFIRMED and f.evidence for f in findings))
        self.assertEqual(stats["checked"], len(llm.prompts("verify_judge")))

    def test_no_retrieval_flag_restores_the_blueprint_only_behaviour(self):
        llm, findings, stats = self.run_pipeline(retrieval=False)
        self.assertTrue(all("THE REAL SOURCE CODE" not in p for p in llm.prompts("finding_gen1")))
        self.assertEqual(stats["mode"], "source-code")                          # the verifier still runs

    def test_a_windows_console_that_cannot_print_the_report_no_longer_crashes_the_run(self):
        import io
        import sys
        from breakpoint import run as runmod
        old = sys.stdout
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        try:
            with self.assertRaises(UnicodeEncodeError):
                print("← all assumed")
                sys.stdout.flush()
            sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
            runmod._utf8_console()
            print("← all assumed")
            sys.stdout.flush()
        finally:
            sys.stdout = old

    def test_the_cli_exposes_the_new_switches(self):
        import io
        from contextlib import redirect_stdout
        from breakpoint import run as runmod
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit):
            runmod.main(["--help"])
        for flag in ("--no-retrieval", "--baseline", "--baseline-context", "--baseline-n"):
            self.assertIn(flag, buf.getvalue())


if __name__ == "__main__":
    unittest.main()
