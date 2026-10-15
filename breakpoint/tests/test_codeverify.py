import json
import threading
import unittest

from breakpoint.codeindex import CodeIndex
from breakpoint.codeverify import CONFIRMED, ERROR, REFUTED, UNVERIFIED, CodeVerifier, claim_terms, verify_findings
from breakpoint.evolution import simulate
from breakpoint.models import Agent, Blueprint, Finding

from .test_codeindex import make_repo

AUTH = ("def callback(request):\n"
        "    code = request.args['code']\n"
        "    if request.args.get('state') != session['state']:\n"
        "        raise AuthError('bad state')\n"
        "    return exchange(code)\n")
DB = ("def get_user(name):\n"
      "    return db.execute(\"SELECT * FROM users WHERE name = '\" + name + \"'\")\n")

UPHELD = {"refutation_holds": True, "reasoning": "the cited code does enforce it"}
STATE_CHECK = "if request.args.get('state') != session['state']:"
SQL_LINE = "return db.execute(\"SELECT * FROM users WHERE name = '\" + name + \"'\")"


class ScriptedLLM:
    """Replies per task. A reply may be a dict (sent as JSON), a string, or an Exception to raise."""
    max_workers = 1

    def __init__(self, **replies):
        self.replies, self.calls, self._lock = replies, [], threading.Lock()

    def scale_tokens(self, base):
        return base

    def complete(self, system, user, *, task="", max_tokens=0):
        with self._lock:
            self.calls.append((task, user))
        r = self.replies[task]
        if callable(r):
            r = r(user)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r)

    def prompts(self, task):
        return [u for t, u in self.calls if t == task]


def finding(title, desc="d", **kw):
    return Finding(title=title, generation=1, discovered_by="A", description=desc, **kw)


def locate(files=("auth.py",), terms=("state",)):
    return {"files": list(files), "search_terms": list(terms)}


def ev(file, quote, line=1):
    return {"file": file, "start_line": line, "end_line": line, "quote": quote}


class Verdicts(unittest.TestCase):
    def setUp(self):
        self.idx = CodeIndex.from_dir(make_repo({"auth.py": AUTH, "db.py": DB}))

    def run_one(self, llm, f=None, **kw):
        v = CodeVerifier(self.idx, llm, **kw)
        return v.check(f or finding("Missing state check on OAuth callback")), v

    def test_a_claim_the_code_contradicts_is_refuted_with_the_protecting_line(self):
        llm = ScriptedLLM(verify_locate=locate(), verify_appeal=UPHELD, verify_judge={
            "verdict": "REFUTED", "reasoning": "state is compared to the session value", "evidence": [ev("auth.py", STATE_CHECK, 3)]})
        r, _ = self.run_one(llm)
        self.assertEqual(r["status"], REFUTED)
        self.assertEqual(r["evidence"][0]["line"], 3)

    def test_a_real_flaw_is_confirmed_and_carries_its_true_line_number(self):
        llm = ScriptedLLM(verify_locate=locate(["db.py"], ["execute"]), verify_judge={
            "verdict": "CONFIRMED", "impact_follows": True, "reasoning": "string concatenation", "evidence": [ev("db.py", SQL_LINE, 99)]},
            verify_defend={"defence_found": False, "reasoning": "no escaping anywhere", "evidence": []})
        r, _ = self.run_one(llm, finding("SQL injection in get_user"))
        self.assertEqual(r["status"], CONFIRMED)
        self.assertEqual(r["evidence"], [{"file": "db.py", "line": 2, "quote": SQL_LINE}])   # 99 was wrong; the file says 2

    def test_a_verdict_with_an_invented_quote_is_not_evidence(self):
        llm = ScriptedLLM(verify_locate=locate(), verify_judge={
            "verdict": "CONFIRMED", "impact_follows": True, "reasoning": "r", "evidence": [ev("auth.py", "if not validate_state(request): abort(403)")]})
        r, _ = self.run_one(llm)
        self.assertEqual(r["status"], UNVERIFIED)

    def test_a_verdict_citing_a_file_that_does_not_exist_is_not_evidence(self):
        llm = ScriptedLLM(verify_locate=locate(), verify_judge={
            "verdict": "CONFIRMED", "impact_follows": True, "reasoning": "r", "evidence": [ev("../../etc/passwd", "root:x:0:0:root:/root:/bin/bash")]})
        self.assertEqual(self.run_one(llm)[0]["status"], UNVERIFIED)

    def test_unverifiable_and_garbage_verdicts_do_not_pass(self):
        for reply in ({"verdict": "UNVERIFIABLE", "evidence": []}, {"verdict": "maybe"}, {"reasoning": "no verdict"}):
            llm = ScriptedLLM(verify_locate=locate(), verify_judge=reply)
            self.assertEqual(self.run_one(llm)[0]["status"], UNVERIFIED, reply)

    def test_code_that_does_the_thing_but_not_the_claimed_harm_is_refuted(self):
        reply = {"verdict": "CONFIRMED", "impact_follows": False, "reasoning": "it swallows an error, nothing is bypassed",
                 "evidence": [ev("db.py", SQL_LINE)]}
        r, _ = self.run_one(ScriptedLLM(verify_locate=locate(), verify_judge=reply))
        self.assertEqual(r["status"], REFUTED)
        self.assertIn("claimed impact does not follow", r["reasoning"])

    def test_a_confirmation_that_never_says_the_impact_follows_is_not_accepted(self):
        reply = {"verdict": "CONFIRMED", "reasoning": "r", "evidence": [ev("db.py", SQL_LINE)]}
        r, _ = self.run_one(ScriptedLLM(verify_locate=locate(), verify_judge=reply))
        self.assertEqual(r["status"], UNVERIFIED)

    def test_the_defender_can_overturn_a_confirmation_only_by_quoting_code(self):
        confirm = {"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "r", "evidence": [ev("db.py", SQL_LINE)]}
        quoted = ScriptedLLM(verify_locate=locate(), verify_judge=confirm, verify_defend={
            "defence_found": True, "reasoning": "state is checked", "evidence": [ev("auth.py", STATE_CHECK)]})
        self.assertEqual(self.run_one(quoted)[0]["status"], REFUTED)
        unquoted = ScriptedLLM(verify_locate=locate(), verify_judge=confirm, verify_defend={
            "defence_found": True, "reasoning": "trust me", "evidence": [ev("auth.py", "invented protective code here")]})
        self.assertEqual(self.run_one(unquoted)[0]["status"], CONFIRMED)

    def test_defender_pass_can_be_turned_off(self):
        llm = ScriptedLLM(verify_locate=locate(), verify_judge={
            "verdict": "CONFIRMED", "impact_follows": True, "reasoning": "r", "evidence": [ev("db.py", SQL_LINE)]})
        r, _ = self.run_one(llm, defend=False)
        self.assertEqual(r["status"], CONFIRMED)
        self.assertEqual(llm.prompts("verify_defend"), [])

    def test_a_failed_locate_step_falls_back_to_the_words_in_the_claim(self):
        llm = ScriptedLLM(verify_locate=RuntimeError("boom"), verify_appeal=UPHELD, verify_judge=lambda user: {
            "verdict": "REFUTED", "reasoning": "r", "evidence": [ev("auth.py", STATE_CHECK)]} if "def callback" in user else {"verdict": "UNVERIFIABLE"})
        f = finding("Missing check in `callback`", "the callback handler skips validation")
        self.assertEqual(self.run_one(llm, f)[0]["status"], REFUTED)

    def test_an_invented_file_from_the_locate_step_is_ignored(self):
        llm = ScriptedLLM(verify_locate=locate(["nope/ghost.py", "auth.py"], ["state"]), verify_appeal=UPHELD, verify_judge={
            "verdict": "REFUTED", "reasoning": "r", "evidence": [ev("auth.py", STATE_CHECK)]})
        self.assertEqual(self.run_one(llm)[0]["status"], REFUTED)

    def test_a_model_error_becomes_an_error_status_not_a_crash(self):
        llm = ScriptedLLM(verify_locate=locate(), verify_judge=RuntimeError("HTTP 500"))
        r, _ = self.run_one(llm)
        self.assertEqual(r["status"], ERROR)
        self.assertIn("HTTP 500", r["reasoning"])

    def test_a_claim_unrelated_to_any_file_is_unverified_without_asking_the_judge(self):
        llm = ScriptedLLM(verify_locate=locate([], []), verify_judge=RuntimeError("must not be called"))
        r, _ = self.run_one(llm, finding("Kubernetes ingress zzqx misconfiguration", "nothing here matches"))
        self.assertEqual(r["status"], UNVERIFIED)
        self.assertEqual(llm.prompts("verify_judge"), [])


class WhatTheModelIsShown(unittest.TestCase):
    def test_the_check_two_hundred_lines_down_is_in_front_of_the_defender(self):
        """The original failure: agents never saw code past the first few thousand characters."""
        filler = "\n".join(f"# padding line {i} " + "x" * 60 for i in range(500))
        big = ("def handler(req):\n    return db.execute(\"SELECT \" + req.args['q'])\n\n" + filler +
               "\n\ndef verify_state(req):\n    if req.args.get('state') != session['state']:\n        raise Denied('csrf')\n")
        idx = CodeIndex.from_dir(make_repo({"web.py": big}))
        llm = ScriptedLLM(verify_locate=locate(["web.py"], ["execute"]), verify_judge={
            "verdict": "CONFIRMED", "impact_follows": True, "reasoning": "r",
            "evidence": [ev("web.py", "return db.execute(\"SELECT \" + req.args['q'])")]},
            verify_defend={"defence_found": False, "reasoning": "none", "evidence": []})
        CodeVerifier(idx, llm).check(finding("SQL injection in handler", "uses `execute`"))
        self.assertIn("raise Denied('csrf')", llm.prompts("verify_defend")[0])

    def test_a_mid_sized_file_is_shown_whole_not_cut_short(self):
        """First live run: an 11,000-character file was cut at 9,000, hiding the state check at its end."""
        body = "\n".join(f"# filler line {i} " + "y" * 20 for i in range(260))
        body += "\nif got.get('state') != state:\n    raise AuthError('check failed')\n"
        self.assertTrue(8_000 < len(body) < 24_000)
        idx = CodeIndex.from_dir(make_repo({"auth.py": body}))
        self.assertIn("raise AuthError('check failed')", idx.excerpt("auth.py", [1]))

    def test_secret_files_never_reach_a_model(self):
        root = make_repo({".env": "STRIPE_SECRET=sk_live_1234567890abcdefghij\nstate_check=1\n", "app.py": AUTH,
                          "keys/server.pem": "-----BEGIN PRIVATE KEY-----\nMIIEv\n-----END PRIVATE KEY-----\n"})
        llm = ScriptedLLM(verify_locate=locate(["app.py", ".env"], ["STRIPE_SECRET", "state"]),
                          verify_judge={"verdict": "UNVERIFIABLE"})
        CodeVerifier(CodeIndex.from_dir(root), llm).check(finding("Leaked STRIPE_SECRET", "state_check"))
        sent = "\n".join(u for _, u in llm.calls)
        self.assertNotIn("sk_live", sent)
        self.assertNotIn("MIIEv", sent)

    def test_the_claims_own_code_words_are_used_for_search(self):
        f = finding("Quota bypass via session.json", "the `_folder` scan and KEYRING_SERVICE in auth.py ignore limits")
        terms = claim_terms(f)
        for t in ("session.json", "_folder", "KEYRING_SERVICE", "auth.py"):
            self.assertIn(t, terms)


class InsideTheSimulation(unittest.TestCase):
    def test_confirmed_findings_keep_their_evidence_and_refuted_ones_teach_the_next_generation(self):
        idx = CodeIndex.from_dir(make_repo({"auth.py": AUTH, "db.py": DB}))
        titles = ["Injection in get_user", "Missing state check on OAuth callback"]
        n = {"i": 0}

        def agent_reply(user):
            n["i"] += 1
            return {"title": titles[(n["i"] - 1) % 2] if n["i"] <= 2 else f"Another idea {n['i']}", "description": "d",
                    "steps_to_exploit": ["s"], "attack_category": "auth", "exploitability": 5, "impact_score": 5,
                    "spread": 5, "fix_difficulty": 1}

        def judge(user):
            if "Injection" in user:
                return {"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "concat", "evidence": [ev("db.py", SQL_LINE)]}
            if "state check" in user:
                return {"verdict": "REFUTED", "reasoning": "state is compared", "evidence": [ev("auth.py", STATE_CHECK)]}
            return {"verdict": "UNVERIFIABLE"}

        llm = ScriptedLLM(finding_gen1=agent_reply, finding_gen2=agent_reply, verify_locate=locate(["auth.py", "db.py"], ["state"]),
                          verify_judge=judge, verify_appeal=UPHELD, verify_defend={"defence_found": False, "evidence": []},
                          crossover={"name": "Kid", "age": 30, "backstory": "b", "motivation": "m", "goal": "g"})
        agents = [Agent(name=x, archetype="A", age=30, backstory="b", motivation="m", goal="g") for x in ("Ann", "Ben")]
        verifier = CodeVerifier(idx, llm)
        found = simulate(Blueprint(name="X", type="app", domain="d", stage="live"), agents, llm, generations=2, verifier=verifier)

        injection = next(f for f in found if f.title == "Injection in get_user")
        self.assertEqual(injection.verification, CONFIRMED)
        self.assertEqual(injection.evidence[0]["file"], "db.py")
        self.assertNotIn("Missing state check on OAuth callback", [f.title for f in found])
        self.assertIn("REFUTED BY THE CODE", "\n".join(llm.prompts("finding_gen2")))
        self.assertGreaterEqual(verifier.stats()["refuted"], 1)

    def test_verify_findings_returns_only_what_holds_and_counts_the_rest(self):
        idx = CodeIndex.from_dir(make_repo({"auth.py": AUTH, "db.py": DB}))
        llm = ScriptedLLM(verify_locate=locate(["auth.py", "db.py"], []), verify_appeal=UPHELD, verify_judge=lambda user: (
            {"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "r", "evidence": [ev("db.py", SQL_LINE)]} if "Injection" in user
            else {"verdict": "REFUTED", "reasoning": "r", "evidence": [ev("auth.py", STATE_CHECK)]}),
            verify_defend={"defence_found": False, "evidence": []})
        kept, stats = verify_findings([finding("Injection in get_user"), finding("No state check")], idx, llm)
        self.assertEqual([f.title for f in kept], ["Injection in get_user"])
        self.assertEqual((stats["checked"], stats["confirmed"], stats["refuted"]), (2, 1, 1))
        self.assertEqual(stats["rejected"][0]["title"], "No state check")


if __name__ == "__main__":
    unittest.main()


class WhatTheJudgeIsGiven(unittest.TestCase):
    def test_route_names_in_a_claim_become_search_terms_and_reach_the_right_file(self):
        f = finding("Account takeover through unvalidated redirect", "an attacker abuses the `/learn` endpoint and /allocations/:userId")
        self.assertIn("/learn", claim_terms(f))
        self.assertIn("/allocations/:userId", claim_terms(f))

    def test_the_judge_sees_repo_wide_search_counts_so_absence_can_be_checked(self):
        idx = CodeIndex.from_dir(make_repo({"auth.py": AUTH, "db.py": DB}))
        llm = ScriptedLLM(verify_locate=locate(["db.py"], ["rate_limit", "execute"]), verify_judge={"verdict": "UNVERIFIABLE"})
        CodeVerifier(idx, llm).check(finding("No rate_limit on get_user"))
        sent = llm.prompts("verify_judge")[0]
        self.assertIn("REPO-WIDE LITERAL SEARCH", sent)
        self.assertIn("'rate_limit': 0 file(s)", sent)
        self.assertIn("'execute': 1 file(s)", sent)

    def test_rejected_claims_keep_their_text_for_later_audit(self):
        idx = CodeIndex.from_dir(make_repo({"auth.py": AUTH}))
        llm = ScriptedLLM(verify_locate=locate(), verify_judge={"verdict": "UNVERIFIABLE"})
        v = CodeVerifier(idx, llm)
        v([finding("Some claim", "the full text of the claim", attack_category="auth")])
        rec = v.stats()["rejected"][0]
        self.assertEqual((rec["claim"], rec["category"]), ("the full text of the claim", "auth"))


class DedupHappensAfterVerification(unittest.TestCase):
    def test_a_badly_worded_claim_cannot_shadow_a_sound_one_about_the_same_bug(self):
        titles = ["Insecure Direct Object Reference in Allocations", "Insecure Direct Object Reference in Allocation Threshold"]
        n = {"i": 0}

        def agent_reply(user):
            n["i"] += 1
            return {"title": titles[(n["i"] - 1) % 2], "description": "d", "steps_to_exploit": ["s"], "attack_category": "authz",
                    "exploitability": 5, "impact_score": 5, "spread": 5, "fix_difficulty": 1}

        seen_by_verifier = []

        def verifier(batch):
            seen_by_verifier.extend(f.title for f in batch)
            return [{"ok": "Threshold" not in f.title, "evidence": "e", "status": "CONFIRMED" if "Threshold" not in f.title else "REFUTED",
                     "evidence_items": []} for f in batch]

        llm = ScriptedLLM(finding_gen1=agent_reply)
        agents = [Agent(name=x, archetype="A", age=30, backstory="b", motivation="m", goal="g") for x in ("Ann", "Ben")]
        found = simulate(Blueprint(name="X", type="app", domain="d", stage="live"), agents, llm, generations=1, verifier=verifier)
        self.assertEqual(sorted(seen_by_verifier), sorted(titles))            # both were checked, not just the first
        self.assertEqual([f.title for f in found], [titles[0]])               # the sound one survives


NODE_INDEX = (
    "const isLoggedIn = session.isLoggedIn;\n"
    "app.get('/benefits', isLoggedIn, benefits.display);\n"
    "/* Fix for A7\n"
    "app.get('/benefits', isLoggedIn, isAdmin, benefits.display);\n"
    "*/\n"
)
NODE_SESSION = (
    "this.isAdminUserMiddleware = (req, res, next) => {\n"
    "    return user && user.isAdmin ? next() : res.redirect('/login');\n"
    "};\n"
)
OPEN_ROUTE = "app.get('/benefits', isLoggedIn, benefits.display);"
COMMENTED_GUARD = "app.get('/benefits', isLoggedIn, isAdmin, benefits.display);"
ADMIN_CHECK = "return user && user.isAdmin ? next() : res.redirect('/login');"


class CommentsAreNotCode(unittest.TestCase):
    def setUp(self):
        self.idx = CodeIndex.from_dir(make_repo({"index.js": NODE_INDEX, "session.js": NODE_SESSION}))

    def run_one(self, llm, **kw):
        return CodeVerifier(self.idx, llm, **kw).check(finding("Non-admin users can open the admin benefits page"))

    def test_the_excerpt_marks_comment_lines(self):
        text = self.idx.excerpt("index.js")
        self.assertIn("    2| app.get('/benefits', isLoggedIn, benefits.display);", text)
        self.assertIn("    4c| app.get('/benefits', isLoggedIn, isAdmin", text)

    def test_a_commented_out_guard_is_not_evidence_of_a_defence(self):
        llm = ScriptedLLM(verify_locate=locate(["index.js"], ["benefits"]), verify_appeal=UPHELD, verify_judge={
            "verdict": "REFUTED", "reasoning": "the admin guard is applied", "evidence": [ev("index.js", COMMENTED_GUARD, 4)]})
        r = self.run_one(llm)
        self.assertEqual((r["status"], r["code"]), (UNVERIFIED, "quote_is_comment"))

    def test_a_defence_that_is_only_defined_but_never_applied_does_not_beat_a_real_flaw(self):
        judge = {"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "route has no admin guard",
                 "evidence": [ev("index.js", OPEN_ROUTE, 2)]}
        # The defender points at the middleware definition (live code) -> counts as a defence...
        live = ScriptedLLM(verify_locate=locate(["index.js"], ["benefits"]), verify_judge=judge, verify_defend={
            "defence_found": True, "reasoning": "admin middleware exists", "evidence": [ev("session.js", ADMIN_CHECK)]})
        self.assertEqual(self.run_one(live)["code"], "defence_found")
        # ...but pointing at the commented-out line does not.
        commented = ScriptedLLM(verify_locate=locate(["index.js"], ["benefits"]), verify_judge=judge, verify_defend={
            "defence_found": True, "reasoning": "guard applied", "evidence": [ev("index.js", COMMENTED_GUARD, 4)]})
        self.assertEqual(self.run_one(commented)["status"], CONFIRMED)


class Appeals(unittest.TestCase):
    def setUp(self):
        self.idx = CodeIndex.from_dir(make_repo({"auth.py": AUTH, "db.py": DB, "index.js": NODE_INDEX, "session.js": NODE_SESSION}))
        self.refute = {"verdict": "REFUTED", "reasoning": "admin middleware exists", "evidence": [ev("session.js", ADMIN_CHECK)]}
        self.recover = {"refutation_holds": False, "impact_follows": True, "reasoning": "defined but never applied to /benefits",
                        "exploit_path": "any user opens /benefits", "evidence": [ev("index.js", OPEN_ROUTE, 2)]}

    def run_one(self, llm, **kw):
        return CodeVerifier(self.idx, llm, **kw).check(finding("Non-admin users can open the admin benefits page"))

    def test_a_refutation_that_does_not_hold_up_is_overturned_and_still_faces_the_defender(self):
        llm = ScriptedLLM(verify_locate=locate(["index.js", "session.js"], ["benefits"]), verify_judge=self.refute,
                          verify_appeal=self.recover, verify_defend={"defence_found": False, "evidence": []})
        r = self.run_one(llm)
        self.assertEqual((r["status"], r["code"]), (CONFIRMED, "confirmed_on_appeal"))
        self.assertEqual(r["evidence"][0]["file"], "index.js")
        self.assertEqual(len(llm.prompts("verify_defend")), 1)

    def test_the_appeal_is_shown_the_files_named_by_the_cited_lines(self):
        llm = ScriptedLLM(verify_locate=locate(["session.js"], []), verify_judge=self.refute,
                          verify_appeal=UPHELD)
        self.run_one(llm)
        self.assertIn("isAdminUserMiddleware", llm.prompts("verify_appeal")[0])
        self.assertIn("res.redirect('/login')", llm.prompts("verify_appeal")[0])

    def test_a_recovered_claim_cannot_skip_the_defender(self):
        llm = ScriptedLLM(verify_locate=locate(["index.js"], ["benefits"]), verify_judge=self.refute, verify_appeal=self.recover,
                          verify_defend={"defence_found": True, "reasoning": "x", "evidence": [ev("session.js", ADMIN_CHECK)]})
        self.assertEqual(self.run_one(llm)["code"], "defence_found")

    def test_an_appeal_without_a_real_vulnerable_quote_changes_nothing(self):
        for reply in ({**self.recover, "evidence": [ev("index.js", "this line does not exist anywhere in the repo")]},
                      {**self.recover, "impact_follows": False}, {"refutation_holds": True}):
            llm = ScriptedLLM(verify_locate=locate(["index.js"], []), verify_judge=self.refute, verify_appeal=reply)
            self.assertEqual(self.run_one(llm)["status"], REFUTED, reply)

    def test_a_failing_appeal_leaves_the_refutation_standing(self):
        llm = ScriptedLLM(verify_locate=locate(["index.js"], []), verify_judge=self.refute, verify_appeal=RuntimeError("HTTP 500"))
        self.assertEqual(self.run_one(llm)["status"], REFUTED)

    def test_appeals_can_be_switched_off(self):
        llm = ScriptedLLM(verify_locate=locate(["index.js"], []), verify_judge=self.refute)
        self.assertEqual(self.run_one(llm, appeal=False)["status"], REFUTED)
        self.assertEqual(llm.prompts("verify_appeal"), [])


class ReasonCodes(unittest.TestCase):
    def test_every_rejection_says_why(self):
        idx = CodeIndex.from_dir(make_repo({"auth.py": AUTH}))
        cases = [
            ({"verdict": "UNVERIFIABLE"}, "judge_unverifiable"),
            ({"verdict": "maybe"}, "invalid_verdict"),
            ({"verdict": "CONFIRMED", "impact_follows": True, "evidence": [ev("auth.py", "no such line in the file at all")]}, "quote_not_in_code"),
            ({"verdict": "CONFIRMED", "evidence": [ev("auth.py", STATE_CHECK)]}, "impact_not_established"),
            ({"verdict": "CONFIRMED", "impact_follows": False, "evidence": [ev("auth.py", STATE_CHECK)]}, "impact_does_not_follow"),
        ]
        for reply, code in cases:
            llm = ScriptedLLM(verify_locate=locate(), verify_judge=reply, verify_appeal=UPHELD)
            v = CodeVerifier(idx, llm)
            v([finding("claim")])
            rec = v.stats()["rejected"][0]
            self.assertEqual(rec["code"], code, reply)
            self.assertTrue(rec["why"] and rec["why"] != code)


class SecondLook(unittest.TestCase):
    def test_when_the_reviewer_asks_for_code_it_was_not_shown_it_gets_it_and_looks_again(self):
        config = "module.exports = {\n    cookieSecret: \"fixed_signing_string_here\",\n    port: 4000\n};\n"
        server = "const { cookieSecret } = require('./config');\napp.use(session({ secret: cookieSecret }));\n"
        idx = CodeIndex.from_dir(make_repo({"server.js": server, "config/env/all.js": config}))
        secret_line = 'cookieSecret: "fixed_signing_string_here",'

        def judge(user):
            if "fixed_signing_string_here" in user:
                return {"verdict": "CONFIRMED", "impact_follows": True, "reasoning": "literal secret in config",
                        "evidence": [ev("config/env/all.js", secret_line, 2)]}
            return {"verdict": "UNVERIFIABLE", "reasoning": "cookieSecret comes from ./config which I cannot see",
                    "need_to_see": ["cookieSecret"]}

        # the first pass is only shown server.js; the second pass is given where cookieSecret is defined
        llm = ScriptedLLM(verify_locate=locate(["server.js"], ["session"]), verify_judge=judge,
                          verify_defend={"defence_found": False, "evidence": []})
        r = CodeVerifier(idx, llm).check(finding("Hard-coded session signing secret", "the secret used to sign cookies is fixed"))
        self.assertEqual((r["status"], r["evidence"][0]["file"]), (CONFIRMED, "config/env/all.js"))
        self.assertEqual(len(llm.prompts("verify_judge")), 2)

    def test_it_only_looks_again_once_and_only_when_asked(self):
        idx = CodeIndex.from_dir(make_repo({"server.js": "app.use(session({ secret: cookieSecret }));\n"}))
        asks = ScriptedLLM(verify_locate=locate(["server.js"], ["session"]),
                           verify_judge={"verdict": "UNVERIFIABLE", "need_to_see": ["cookieSecret"]})
        CodeVerifier(idx, asks).check(finding("Hard-coded session signing secret"))
        self.assertEqual(len(asks.prompts("verify_judge")), 2)
        silent = ScriptedLLM(verify_locate=locate(["server.js"], ["session"]), verify_judge={"verdict": "UNVERIFIABLE"})
        CodeVerifier(idx, silent).check(finding("Hard-coded session signing secret"))
        self.assertEqual(len(silent.prompts("verify_judge")), 1)
