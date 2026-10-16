"""All prompt templates.

The GENERATION_INSTRUCTIONS dict is the product's actual moat: each generation
asks a *structurally different question*, which is what forces Gen 5 output to
be categorically different from Gen 1 rather than just a reworded restatement.
"""

# --- Blueprint decomposition (spec POINT 1, "Product Decomposition" call) -----

BLUEPRINT_SYSTEM = (
    "You are a product-security analyst. Decompose a product description into a "
    "structured attack-surface blueprint. Distinguish STATED mechanics (explicitly "
    "in the description) from ASSUMED mechanics by appending ' (ASSUMED)' to "
    "inferred items. Do NOT invent product features absent from the description — "
    "mark gaps as known_unknowns instead. "
    "Output ONLY valid JSON, no prose, no markdown fences."
)

BLUEPRINT_USER = """Decompose the following product into this exact JSON schema:

{{
  "name": str,
  "type": str,                  // e.g. "SaaS web app", "mobile app"
  "domain": str,                // e.g. "EdTech", "Fintech"
  "stage": str,                 // "Pre-launch" | "Beta" | "Live"
  "actors": [str],              // every role incl. anonymous + API consumer
  "resources": [str],           // what the system manages
  "boundaries": [str],          // where transitions happen (free->paid, etc.)
  "flows": [{{"name": str, "steps": [str]}}],
  "mechanical_details": [str],  // edge-case specifics, with "(?)" where unsure
  "known_unknowns": [str],      // gaps the founder hasn't decided - CRITICAL
  "attack_surface": [str]       // high-value targets derived from the above
}}

Be aggressive about populating known_unknowns: list every mechanic that was
implied but never specified. These are the highest-value entries.

PRODUCT DESCRIPTION:
{description}
"""

# --- Follow-up interrogation (spec POINT 1, MODE 1) ---------------------------

FOLLOWUP_SYSTEM = (
    "You are Breakpoint, interrogating a founder about their product. You ask "
    "the specific mechanical questions a founder forgets to answer, because "
    "those gaps are where exploits live. Output ONLY a JSON array of question "
    "strings."
)

FOLLOWUP_USER = """Given this draft blueprint, write 5-8 targeted clarifying
questions about MECHANICS at the edges (ownership, limits, identity, reset
behavior, what-happens-when). Not generic questions. Probe the known_unknowns.

DRAFT BLUEPRINT:
{blueprint}

Return: ["question 1", "question 2", ...]
"""

# --- Agent generation (spec POINT 3) -----------------------------------------

ARCHETYPES = [
    ("THE FREELOADER", "never pay", "cost"),
    ("THE GUARDIAN", "protect privacy", "safety"),
    ("THE HACKER", "break things", "curiosity"),
    ("THE ORGANIZER", "coordinate groups", "social"),
    ("THE POWER USER", "maximize efficiency", "output"),
    ("THE CRITIC", "find UX failures", "frustration"),
    ("THE COMPETITOR", "extract intelligence", "business"),
    ("THE GRIEFER", "ruin others' experience", "chaos"),
    ("THE NAIVE USER", "just use the product", "task completion"),
    ("THE REGULATOR", "find compliance issues", "legal"),
    ("THE SCALPER", "exploit for profit", "money"),
    ("THE ADVOCATE", "warn others", "community"),
    # --- structural / deep-code archetypes ---
    ("THE ARCHITECT", "expose design flaws and structural tech debt", "durability"),
    ("THE CODE AUDITOR", "find code smells, anti-patterns, and hidden quality risks", "cleanliness"),
]

AGENT_SYSTEM = (
    "You generate realistic threat-actor personas for product red-teaming. "
    "Each persona is a real-feeling person with a backstory, not a parameter "
    "vector - a rich backstory gives far stronger behavioral anchoring. "
    "Output ONLY valid JSON."
)

AGENT_USER = """Create one persona for this archetype, tailored to the product's
domain so its knowledge and tactics are domain-specific.

ARCHETYPE: {archetype} (goal: {goal}; core motivation: {motivation})
PRODUCT DOMAIN: {domain}
PRODUCT: {name}

Return JSON:
{{
  "name": str,
  "age": int,
  "backstory": str,                 // 2-3 sentences, concrete and specific
  "motivation": str,
  "goal": str,                      // specific goal with THIS product
  "knowledge": [str],               // domain-specific things they know
  "willing_to": [str],
  "unwilling_to": [str],
  "personality": {{"frugality": 0-1, "tech_savvy": 0-1, "risk_tolerance": 0-1,
                   "social_coordination": 0-1, "patience": 0-1, "ethics": 0-1}}
}}
"""

PRODUCT_SPECIFIC_AGENTS_SYSTEM = (
    "You invent specialized threat actors unique to a specific product type. "
    "Output ONLY a JSON array."
)

PRODUCT_SPECIFIC_AGENTS_USER = """Read this blueprint and invent ONE threat
actor that is UNIQUE to this exact product (like THE EXAM CHEATER for a
tutoring app, or THE SHILL BIDDER for a marketplace). They must exploit
something specific to this product's mechanics that a generic attacker would miss.

BLUEPRINT:
{blueprint}

Return a single JSON object (not an array):
{{"name": str, "age": int, "backstory": str, "motivation": str, "goal": str,
  "knowledge": [str], "willing_to": [str], "unwilling_to": [str],
  "personality": {{"frugality": 0-1, "tech_savvy": 0-1, "risk_tolerance": 0-1,
                  "social_coordination": 0-1, "patience": 0-1, "ethics": 0-1}},
  "archetype": "PRODUCT-SPECIFIC"}}"""

# --- The evolutionary generation instructions (spec POINT 3) -----------------
# This is the core differentiator. Same agents, DIFFERENT question per gen.

GENERATION_INSTRUCTIONS = {
    1: (
        "You have just discovered this product for the first time. Based on your "
        "persona and goals, find ONE weakness by examining the product surfaces "
        "directly. Reference ONLY direct product features - you know nothing that "
        "other users have found. Report your immediate, single-feature reaction."
    ),
    2: (
        "You've used this product for a week and heard from other users about the "
        "findings below. COMBINE or EXTEND at least two of them into a NEW exploit "
        "that emerges only when you put them together. It must be different from "
        "both parents."
    ),
    3: (
        "You know the findings below and understand how this product actually works. "
        "Find a CHAINED exploit: A→B→C where exploiting finding A unlocks a new "
        "capability that directly enables finding B, and B enables finding C. Each "
        "step must change what an attacker can do next — not just 'more users doing "
        "the same thing'. Think privilege escalation chains, token reuse across "
        "components, or one bug whose fix introduces a second exploitable surface."
    ),
    4: (
        "Analyze this product from a MARKET perspective. Given the known "
        "vulnerabilities below, identify the second-order BUSINESS CONSEQUENCES: "
        "what happens to the company's revenue, reputation, and user trust? Reference "
        "business impact, not just a technical exploit."
    ),
    5: (
        "You know EVERYTHING previous agents found (below). Find the ONE vulnerability "
        "nobody else found - hiding in the interaction of 3+ features, visible only "
        "with the full picture. Consider temporal attacks (work over time), cascade "
        "failures (one exploit enables another), and meta-exploits (exploiting the FIX "
        "for a previous exploit). If it restates any prior finding it is worthless."
    ),
}

AGENT_RUN_SYSTEM = (
    "You are role-playing a specific threat actor red-teaming a product. Stay "
    "fully in character; reason from the persona's actual motivations and "
    "knowledge. You output ONE concrete vulnerability as valid JSON only."
)

AGENT_RUN_USER = """{persona}

----- PRODUCT BLUEPRINT -----
{blueprint}

----- GROUNDING RULE (critical) -----
Only reference mechanics EXPLICITLY stated in the blueprint above. If you must
reference a mechanic not stated there, prepend "(ASSUMED)" to your title and
set confidence below 0.5. Do NOT invent product features from general knowledge
about similar products.

----- YOUR TASK (Generation {generation}) -----
{instruction}

{prior_block}
{category_block}

Return JSON for the single best vulnerability you found:
{{
  "title": str,                    // short, specific, memorable
  "attack_category": str,          // one of: auth | authz | rate_limiting | data_privacy | billing | injection | crypto | config | supply_chain | ux | architecture | code_quality | error_handling | scalability
  "description": str,              // what the weakness is, in your voice
  "steps_to_exploit": [str],       // 3-5 concrete steps
  "impact": str,                   // who is harmed and how
  "evolved_from": [str],           // titles of prior findings you built on ([] for Gen 1)
  "confidence": 0.0-1.0,           // how grounded in STATED blueprint facts (not assumed/invented)
  "exploitability": 0-10,          // how easy for a typical user
  "impact_score": 0-10,            // revenue + reputation + user harm
  "spread": 0-10,                  // how virally users would share it
  "fix_difficulty": 1-10
}}
"""

# Codebase mode: the same task, but the agent is shown real source retrieved for its assigned category
# (see coderetrieval.py) and must tie its claim to lines in it.
AGENT_RUN_USER_CODE = """{persona}

----- PRODUCT BLUEPRINT (a summary written from part of the code; the source below is the ground truth) -----
{blueprint}

----- THE REAL SOURCE CODE ({category}) -----
Line format: `<line number>| <code>`. A number followed by `c` (for example `12c|`) is a COMMENT line, not active code.
Secret values are redacted. This is a selection from a larger repository, chosen for your assigned category.

{code_block}

----- GROUNDING RULE (critical) -----
Everything you claim must be visible in the source above.
- Name the exact lines where the flaw bites in "code_refs": the file path exactly as shown, the line number, and the
  line(s) copied character-for-character (without the number and the `|`). Citations are checked against the files.
- Before you say a protection is missing, look for it in the excerpts and in the CONTROL SEARCH. A protection that
  exists only in a comment, only in a template, or only as an unused dependency is NOT enforced. A protection that is
  applied where the attacker's request is handled means there is no finding.
- The harm you describe must follow from those lines. Do not invent features, plans, quotas or business rules that the
  code does not contain, and do not assume code you cannot see.
- Do not report anything covered by an ALREADY PATCHED or TESTED AND REFUTED list below.

----- YOUR TASK (Generation {generation}) -----
{instruction}
{code_task_note}

{prior_block}
{category_block}

Return JSON for the single best vulnerability you found:
{{
  "title": str,                    // short, specific, memorable
  "attack_category": str,          // one of: auth | authz | rate_limiting | data_privacy | billing | injection | crypto | config | supply_chain | ux | architecture | code_quality | error_handling | scalability
  "description": str,              // what the weakness is, citing file:line, in your voice
  "steps_to_exploit": [str],       // 3-5 concrete steps
  "impact": str,                   // who is harmed and how
  "code_refs": [                   // 1-3 citations of the vulnerable live code
    {{"file": str, "line": int, "quote": str}}
  ],
  "evolved_from": [str],           // titles of prior findings you built on ([] for Gen 1)
  "confidence": 0.0-1.0,           // how well the code above supports the claim
  "exploitability": 0-10,          // how easy for a typical user
  "impact_score": 0-10,            // revenue + reputation + user harm
  "spread": 0-10,                  // how virally users would share it
  "fix_difficulty": 1-10
}}
"""

CODE_TASK_NOTE = (
    "You are reading real code. If the question above has no genuine answer in the code you were given (there is no "
    "real combination or chain to be found here), do not stretch the code to fit it: report instead the most serious "
    "REAL vulnerability visible above that is not already in the list of earlier findings."
)

# Plain single-prompt baseline: one model, asked once. Used only to measure whether the evolutionary engine beats it.
BASELINE_SYSTEM = (
    "You are a senior application-security engineer reviewing a codebase. Output ONLY valid JSON."
)

BASELINE_USER = """Review the source code below and list the {n} most serious security vulnerabilities in it.

Line format: `<line number>| <code>`. A number followed by `c` (for example `12c|`) marks a comment line, not active code.
Secret values are redacted.

SOURCE CODE
{code_block}

Return a JSON array of exactly {n} objects, most serious first:
[
  {{
    "title": str,                    // short and specific
    "attack_category": str,          // one of: auth | authz | rate_limiting | data_privacy | billing | injection | crypto | config | supply_chain | ux | architecture | code_quality | error_handling | scalability
    "description": str,              // what the weakness is, citing file:line
    "steps_to_exploit": [str],       // 3-5 concrete steps
    "impact": str,                   // who is harmed and how
    "code_refs": [ {{"file": str, "line": int, "quote": str}} ]   // the vulnerable line(s), copied exactly, without the number and the `|`
  }}
]
"""

PRIOR_FINDINGS_HEADER = "----- WHAT EARLIER AGENTS ALREADY FOUND -----"
CATEGORY_DIVERSITY_HEADER = "----- ATTACK CATEGORY COVERAGE (steer toward uncovered categories) -----"
KNOWN_FIXED_HEADER = (
    "----- ALREADY PATCHED (DO NOT RE-REPORT) -----\n"
    "The developer has already fixed the following vulnerabilities. "
    "Any finding that overlaps with these — even under a different title — is WORTHLESS. "
    "You MUST find something genuinely new that is NOT covered by any item below:\n"
)
REFUTED_HEADER = (
    "----- CLAIMS ALREADY TESTED AND REFUTED -----\n"
    "These claims were checked against the real thing (the running app or its actual source code) "
    "and did not hold: the product behaved as intended or already has the protection. "
    "Do not repeat them. The evidence shown is real; use it to work out where the product "
    "actually differs from its stated rules:\n"
)

# --- Code verification (every codebase finding is checked against the real source) ----

VERIFY_LOCATE_SYSTEM = (
    "You help a code reviewer find where, in a repository, a claimed security problem can be checked. "
    "You never judge the claim. Output ONLY valid JSON."
)

VERIFY_LOCATE_USER = """CLAIM
Title: {title}
Description: {description}
Steps: {steps}

REPOSITORY FILES
{file_list}

Return JSON:
{{
  "files": ["up to 6 paths copied EXACTLY from the list above: the files most likely to contain the code this claim is about, INCLUDING files where a protection against it would live (auth, validation, storage, config)"],
  "search_terms": ["up to 8 literal strings likely to appear in the relevant code: function names, file names, config keys, status codes, and words for checks that could block the claim such as 'state', 'csrf', 'verify', 'keyring'"]
}}"""

VERIFY_JUDGE_SYSTEM = (
    "You are a skeptical senior application-security engineer. A junior analyst wrote a vulnerability claim "
    "WITHOUT reading the whole code, so most such claims are wrong: they describe protections as missing that "
    "exist a few lines away, or describe behaviour the code does not have. You check the claim against the REAL "
    "source excerpts you are given.\n"
    "Rules:\n"
    "- Use ONLY the code shown. Never assume code you cannot see.\n"
    "- CONFIRMED only if (1) the shown code contains the specific vulnerable behaviour the claim describes, "
    "(2) no shown code prevents or contradicts it, and (3) the attacker needs no more access than the claim states "
    "(an attacker who already controls the user's machine or admin account is NOT a vulnerability).\n"
    "- REFUTED if shown code contradicts the claim or already contains the protection it says is missing "
    "(a state/CSRF check, auth middleware, parameterised query, keyring storage, a rate limit, a size cap...). "
    "Quote that protection.\n"
    "- UNVERIFIABLE if the excerpts do not contain the relevant code. Do not guess.\n"
    "- A missing best practice, a design trade-off, or an intended feature is NOT a vulnerability.\n"
    "- Judge the claimed IMPACT, not only the code. If the code really does the thing quoted (for example it "
    "swallows an exception) but the consequence the claim promises (bypass, takeover, leak, free access) does "
    "not follow from what the code does, the claim is REFUTED.\n"
    "- A protection only counts if the code that handles the attacker's request ENFORCES it. A token merely rendered "
    "in a template, a check defined but never applied to that route, or a comment describing a fix is not enforcement.\n"
    "- If the harm the claim describes depends on a product feature or business rule (free trials, plans, quotas, "
    "billing, tiers) that you cannot find in the code, the claim invented it: impact_follows is false.\n"
    "- For a claim that something is MISSING (no rate limit, no ownership check), use the REPO-WIDE LITERAL SEARCH "
    "at the top of the excerpts: zero hits for the obvious names is evidence of absence, a hit means go and look at it. "
    "Absence only matters if the code shows what an attacker gains from it.\n"
    "- A line that merely CALLS a function proves nothing about what that function does. If the claim depends on "
    "the body of a function you were not shown, answer UNVERIFIABLE.\n"
    "- Quote the line where the flaw actually bites (where attacker input reaches the dangerous operation, or "
    "where the missing check should be), not just a line that mentions the feature.\n"
    "Output ONLY valid JSON."
)

VERIFY_JUDGE_USER = """CLAIM
Title: {title}
Category: {category}
Description: {description}
Steps: {steps}
Impact: {impact}

SOURCE EXCERPTS (line-numbered; the number and '|' are not part of the code; 'c|' marks a comment line, which is NOT active code)
{excerpts}

Return JSON:
{{
  "verdict": "CONFIRMED" | "REFUTED" | "UNVERIFIABLE",
  "reasoning": "at most 60 words: what the code actually does versus what the claim says",
  "attacker_needs": "the access the attacker must already have for this to work",
  "exploit_path": "at most 50 words: what the attacker does, which line the flaw is on, and the concrete harm that results",
  "impact_follows": true | false,
  "evidence": [
    {{"file": "path exactly as in the excerpts", "start_line": 1, "end_line": 1,
      "quote": "1-3 lines copied CHARACTER-FOR-CHARACTER from the excerpt, without the line-number gutter"}}
  ],
  "defense_search_terms": ["up to 6 literal strings that would appear in code that blocks this claim, if any exists elsewhere"],
  "need_to_see": ["only when UNVERIFIABLE: up to 5 literal names (variables, functions, files, config keys) whose definitions you needed but were not shown"]
}}
For CONFIRMED the evidence is the vulnerable code. For REFUTED it is the code that contradicts or prevents the claim. A verdict without a real quote is worthless."""

VERIFY_DEFEND_SYSTEM = (
    "You are the defender of a codebase. A reviewer has CONFIRMED a vulnerability claim. Your job is to find the "
    "strongest reason it is NOT a real, exploitable vulnerability, using ONLY the source shown: an existing check "
    "elsewhere in the code, the attacker needing capabilities the claim ignores, a code path that is unreachable "
    "or never receives attacker input, or an impact that does not follow. If you find none, say it stands. "
    "A defence counts only if it blocks the SPECIFIC attacker the claim describes: a login check does not stop an "
    "already-logged-in user from reading another user's data (authentication is not authorization), and a CSRF "
    "token on one form does not protect a different form. A defence must also be ENFORCED where the request is "
    "handled: a token only rendered in a template, a function never applied to the route, or a commented-out fix "
    "is not a defence. Read the claim's own steps for what access the attacker already has: if they already "
    "assume that access (for example 'log in as any user'), a login check is not a defence. A check that merely "
    "narrows, delays or reduces the harm does not defeat the claim either: answer defence_found true only if the "
    "attack as described becomes impossible. "
    "Do not invent defences. Output ONLY valid JSON."
)

VERIFY_DEFEND_USER = """CLAIM
Title: {title}
Description: {description}
Steps: {steps}
Impact: {impact}

THE REVIEWER'S CASE
{reasoning}

SOURCE EXCERPTS (line-numbered; the number and '|' are not part of the code; 'c|' marks a comment line, which is NOT active code)
{excerpts}

Return JSON (explain first, then answer):
{{
  "reasoning": "at most 60 words: does any ENFORCED, live code defeat this specific claim?",
  "defence_found": true | false,
  "evidence": [
    {{"file": "path exactly as in the excerpts", "start_line": 1, "end_line": 1,
      "quote": "1-3 lines of LIVE code copied CHARACTER-FOR-CHARACTER from the excerpt that defeat the claim"}}
  ]
}}
defence_found is false when the claim stands. Say true only if you can quote the code that defeats it."""

VERIFY_APPEAL_SYSTEM = (
    "You are an appeals reviewer. A first reviewer REFUTED a vulnerability claim by citing some code. First "
    "reviewers often cite code that does not really defend: a token that is rendered but never validated, a check "
    "that is defined but never applied to the route, a value that is read from a config file whose actual content "
    "is itself the flaw, or a commented-out fix. Decide whether the cited code truly enforces a defence against the "
    "SPECIFIC attacker the claim describes, using ONLY the source shown. Lines marked with 'c|' are comments, "
    "not code. If the refutation is sound, say so. If the vulnerability is still real, quote the live vulnerable "
    "code. Output ONLY valid JSON."
)

VERIFY_APPEAL_USER = """CLAIM
Title: {title}
Description: {description}
Steps: {steps}
Impact: {impact}

THE FIRST REVIEWER REFUTED IT BECAUSE
{reasoning}

CODE THE REFUTATION CITES
{cited}

SOURCE EXCERPTS (line-numbered; the number and '|' are not part of the code; 'c|' marks a comment line)
{excerpts}

Return JSON (explain first, then answer):
{{
  "reasoning": "at most 60 words: does the cited code really enforce a defence on the attacker's path?",
  "refutation_holds": true | false,
  "exploit_path": "at most 50 words: if it does not hold, what the attacker does and which live line is the flaw",
  "impact_follows": true | false,
  "defense_search_terms": ["up to 6 literal strings that would appear in code that blocks this claim, if any exists elsewhere"],
  "evidence": [
    {{"file": "path exactly as in the excerpts", "start_line": 1, "end_line": 1,
      "quote": "1-3 lines of LIVE vulnerable code copied CHARACTER-FOR-CHARACTER, only if refutation_holds is false"}}
  ]
}}"""

# --- Custom Agent & Crossover (spec V2 backend features) ----------------------

CUSTOM_AGENT_SYSTEM = (
    "You generate realistic threat-actor personas for product red-teaming based on a custom scenario. "
    "Output ONLY valid JSON."
)

CUSTOM_AGENT_USER = """Create one persona based on the following custom scenario description, tailored to the product's domain.

CUSTOM SCENARIO: {scenario}
PRODUCT DOMAIN: {domain}
PRODUCT: {name}

Return JSON:
{{
  "name": str,
  "age": int,
  "backstory": str,                 // 2-3 sentences, concrete and specific
  "motivation": str,
  "goal": str,                      // specific goal with THIS product
  "knowledge": [str],               // domain-specific things they know
  "willing_to": [str],
  "unwilling_to": [str],
  "personality": {{"frugality": 0-1, "tech_savvy": 0-1, "risk_tolerance": 0-1,
                   "social_coordination": 0-1, "patience": 0-1, "ethics": 0-1}}
}}
"""

CROSSOVER_SYSTEM = (
    "You are a threat-intelligence analyst. You combine two distinct threat actor personas "
    "into a hybrid threat actor that inherits the traits, backstory elements, motivations, and goals of both. "
    "Output ONLY valid JSON."
)

CROSSOVER_USER = """Create a hybrid threat-actor persona by performing a crossover between these two parent personas:

PARENT 1:
{parent1}

PARENT 2:
{parent2}

The hybrid persona must combine:
1. Backstory: Synthesize a coherent backstory that merges details from both parents.
2. Motivation: Combine their core drivers/motivations.
3. Goal: Combine their goals relative to this product.
4. Knowledge: Merge and deduplicate their knowledge lists.
5. willing_to / unwilling_to: Merge and deduplicate.

Return JSON:
{{
  "name": str,                      // invent a name that reflects the hybrid character
  "age": int,                       // average of parents or a reasonable mid-point
  "backstory": str,                 // 2-3 sentences, concrete and specific
  "motivation": str,
  "goal": str,
  "knowledge": [str],
  "willing_to": [str],
  "unwilling_to": [str]
}}
"""

# --- Mode 2 & Mode 3 Intake (spec features) -----------------------------------

BLUEPRINT_FROM_DOCS_SYSTEM = (
    "You are a principal security architect. You analyze product documentation (PRDs, API specs, database schemas, etc.) "
    "and extract a structured, unified attack-surface blueprint. Distinguish STATED features from ASSUMED features by appending "
    "' (ASSUMED)' to inferred items. Output ONLY valid JSON, no prose, no markdown fences."
)

BLUEPRINT_FROM_DOCS_USER = """Analyze the following product documentation files and construct a single, comprehensive attack-surface blueprint.

DOCUMENTATION:
{docs_block}

Output a single JSON object matching this exact schema:
{{
  "name": str,
  "type": str,                  // e.g. "SaaS web app", "mobile app"
  "domain": str,                // e.g. "EdTech", "Fintech"
  "stage": str,                 // "Pre-launch" | "Beta" | "Live"
  "actors": [str],              // every role incl. anonymous + API consumer
  "resources": [str],           // what the system manages
  "boundaries": [str],          // where transitions happen (free->paid, user->admin, public->private)
  "flows": [{{"name": str, "steps": [str]}}],
  "mechanical_details": [str],  // specific business rules and edge cases from documentation
  "known_unknowns": [str],      // gaps, undefined behaviors, or missing info in the docs
  "attack_surface": [str]       // high-value targets for penetration testing
}}
"""

BLUEPRINT_FROM_CODE_SYSTEM = (
    "You are a principal security architect. You analyze codebase extracts (routes, database models, controllers, middleware, etc.) "
    "and extract a structured, unified attack-surface blueprint. Distinguish STATED features from ASSUMED features by appending "
    "' (ASSUMED)' to inferred items. Output ONLY valid JSON, no prose, no markdown fences."
)

BLUEPRINT_FROM_CODE_USER = """Analyze the following codebase files and structure and construct a single, comprehensive attack-surface blueprint.

CODE FILES & DETAILS:
{code_block}

Output a single JSON object matching this exact schema:
{{
  "name": str,
  "type": str,                  // e.g. "SaaS web app", "mobile app"
  "domain": str,                // e.g. "EdTech", "Fintech"
  "stage": str,                 // "Pre-launch" | "Beta" | "Live"
  "actors": [str],              // every role incl. anonymous + API consumer
  "resources": [str],           // what the system manages
  "boundaries": [str],          // where transitions happen
  "flows": [{{"name": str, "steps": [str]}}],
  "mechanical_details": [str],  // security controls, rate limiting, auth middlewares, DB constraints from code
  "known_unknowns": [str],      // gaps, missing auth checks, or unvalidated parameters in code
  "attack_surface": [str]       // actual routes, endpoints, and data tables exposed in code
}}
"""

# --- Code Intelligence "Brain" Pass (deep structural analysis) ----------------
# A SECOND dedicated LLM call on Mode 3 codebase scans.
# Finds hidden, non-obvious structural issues adversarial agents miss.

CODE_BRAIN_SYSTEM = (
    "You are a senior staff engineer and codebase forensics expert. You read code "
    "the way a detective reads a crime scene — looking for what is missing, hidden, "
    "inconsistent, or will silently fail under real load or adversarial conditions. "
    "Output ONLY valid JSON, no prose, no markdown."
)

CODE_BRAIN_USER = """Perform a deep structural and quality intelligence pass on this codebase.
Go beyond the obvious. Find hidden coupling, silent failure points, missing safeguards,
and architectural decisions that cause real harm (data loss, downtime, security breach,
runaway costs) that a typical security review would miss.

STRUCTURAL SIGNALS:
{structural_signals}

CODE FILES:
{code_block}

Return JSON with these exact fields:
{{
  "architecture_risks": [str],   // tight coupling, god objects, circular deps, monolith risks
  "hidden_failure_points": [str],// unhandled errors, missing retries, silent data loss paths
  "scalability_bombs": [str],    // N+1 queries, no pagination, blocking I/O, in-memory state
  "code_quality_debt": [str],    // hardcoded secrets, magic numbers, dead code that still executes
  "missing_safeguards": [str],   // no rate limiting evidence, no input validation patterns seen
  "dependency_risks": [str],     // pinned vs unpinned deps, outdated packages, missing lockfile
  "observability_gaps": [str],   // no logging, no metrics, no tracing, swallowed exceptions
  "deployment_risks": [str]      // no CI/CD evidence, hardcoded envs, missing health checks
}}

Be specific: reference actual file names, function names, or patterns you observed.
Empty array for categories with no findings.
"""

# --- Causal Vulnerability Graph (CVG) ------------------------------------------

CVG_SYSTEM = (
    "You are a causal security analyst. Your job is to identify the shared root "
    "causes that explain clusters of related vulnerabilities. A root cause is a "
    "design decision, architectural choice, or missing control that, if fixed, "
    "would eliminate multiple findings simultaneously. Be structural and precise — "
    "look for the *why*, not just the *what*. "
    "Output ONLY valid JSON, no prose, no markdown fences."
)

CVG_USER = """Analyze these vulnerability findings and identify their shared root causes.

FINDINGS:
{findings_block}

Return a JSON object with this exact schema:
{{
  "root_causes": [
    {{
      "id": "rc_<short_slug>",
      "label": "one-line description of the root design flaw or missing control",
      "category": "one of: auth|authz|rate_limiting|data_privacy|billing|injection|crypto|config|supply_chain|ux|architecture|code_quality|error_handling|scalability",
      "finding_ids": ["exact_id_1", "exact_id_2"],
      "fix_hint": "one concrete, actionable sentence on what to change in the product design"
    }}
  ]
}}

Rules:
- Every finding_id MUST be copied character-for-character from the ID= values in FINDINGS above
- A finding can appear in AT MOST ONE root cause group
- Only group findings that share a genuine causal link (same design gap, same missing control)
- Findings with no shared root cause should NOT appear in any group
- Aim for 3-7 root causes total; do NOT create one root cause per finding
- Order root causes by impact: most findings eliminated first
"""

# --- Claim extraction (claim-driven verification layer) -----------------------

CLAIM_SYSTEM = (
    "You are a security-minded product analyst. Read this Product Blueprint the "
    "way an AI safety evaluator reads a safety case: not 'what could go wrong in "
    "general' but 'what does this design specifically claim to guarantee, and "
    "what is the precise scenario where that claim is false?' "
    "Output ONLY valid JSON, no prose, no markdown fences."
)

CLAIM_USER = """Extract every guarantee this blueprint implies — from actors,
resources, boundaries, and flows. A claim is a specific, falsifiable statement
like "only the resource owner can read a private resource" or "crossing from
free tier to paid tier requires the trigger condition to be met." Do not
extract vague claims like "the system is secure."

BLUEPRINT:
{blueprint_block}

For each claim, decide whether it is FORMALIZABLE: expressible as a predicate
over actors/resources/state. Business/UX claims that can't reduce to a
predicate are still valid claims — mark them not formalizable.

Return a JSON object with this exact schema:
{{
  "claims": [
    {{
      "statement": "plain-language guarantee, one sentence",
      "category": "one of: auth|rate_limit|data_isolation|payment|business_logic|ux|compliance|other",
      "feature_refs": ["names of actors/resources/boundaries/flows this claim depends on"],
      "formalizable": true,
      "predicate": "short pseudo-logic expression if formalizable, else null",
      "severity_if_false": "critical|high|medium|low"
    }}
  ]
}}

Extract as many distinct, falsifiable claims as the blueprint supports —
typically 15-40 for a moderately complex product. Prefer specific over
general. Every attack_surface entry and every boundary should yield at least
one claim.
"""

# --- Attack agent (claim-driven verification layer) ----------------------------

ATTACK_SYSTEM = (
    "You are testing one specific claim about a live HTTP API. Your job is to "
    "try to falsify it — find a request whose response proves the claim is "
    "false. If you can't, say so honestly; do not force a conclusion. "
    "Output ONLY valid JSON, no prose, no markdown fences."
)

ATTACK_INTRO = """CLAIM TO TEST:
"{statement}"

{api_surface}

You have up to {max_turns} turns. On each turn, respond with JSON in exactly
one of these two shapes:

To try a request:
{{"action": "request", "method": "GET", "path": "/some/path", "query": {{"key": "value"}}}}

To conclude (only once you've actually tried a request you believe proves
your answer):
{{"action": "conclude", "falsified": true, "proofRequest": {{"method": "GET", "path": "/...", "query": {{}}}}, "reasoning": "one or two sentences"}}
or
{{"action": "conclude", "falsified": false, "reasoning": "one or two sentences"}}

Rules:
- Only GET requests against the listed endpoints. Use the known entities to
  construct meaningful parameters.
- "falsified: true" requires a proofRequest — the exact request whose response
  you're pointing to as evidence. It will be re-run independently to check
  your claim, so make sure it's the real request, not a paraphrase.
- If you run out of good ideas, conclude with falsified: false rather than
  guessing endlessly.

Respond with the JSON for your first action now.
"""

# --- Per-route review (one route, one kind of problem, the code that matters) --------

ROUTE_REVIEW_SYSTEM = (
    "You are a senior application-security engineer doing a focused review of ONE part of a web application. "
    "You report only problems you can prove from the code shown, and only inside your focus. "
    "Output ONLY valid JSON."
)

ROUTE_REVIEW_USER = """FOCUS: {focus_name}
{focus_question}

{subject_kind}
{subject_facts}

APP-WIDE SETUP (applies to every route)
{app_facts}

CODE
Line format: `<line number>| <code>`; a number followed by `c` (for example `12c|`) marks a comment: it is NOT active code
and never protects anything. Secret values are redacted.
{code_block}

RULES
- Judge only what the CODE shows. A protection counts only if it is applied to this route (listed under "protections in
  front") or is app-wide and active. A check that is defined but not applied here, or that sits in a comment, protects nothing.
- Report a problem only if you can copy the exact vulnerable line(s) from the CODE, without the line number and the `|`.
  For a protection that is missing or switched off, quote the line where it should be or the commented-out line.
- Stay inside your focus; other reviewers cover other kinds of problem. If there is no problem in your focus, return
  {{"findings": []}}. Do not pad: zero is a good answer.
- At most {max_findings} findings, most serious first.

Return JSON:
{{"findings": [
  {{
    "title": str,                      // short and specific
    "attack_category": str,            // one of: {categories}
    "description": str,                // what is wrong and why an attacker can reach it, citing file:line
    "steps_to_exploit": [str],         // 2-4 concrete steps for an outsider or low-privilege user
    "impact": str,                     // who is harmed and how
    "exploitability": int, "impact_score": int, "spread": int, "fix_difficulty": int,   // each 0-10 (fix_difficulty 1-10)
    "code_refs": [ {{"file": str, "line": int, "quote": str}} ]
  }}
]}}
"""

ROUTE_FOCUS = {
    "authz": (
        "Access control",
        "Can someone who should not be able to use this route use it? Look for: a login or admin check that the route "
        "needs but does not have; a check on the GET page that is missing on the POST that changes data; an identifier "
        "taken from the URL, query string or body (instead of the session) that decides whose data is read or changed; "
        "a protection that exists only in a comment; a role check that only hides a button. Compare with the "
        "protections listed for this route and with any switched-off variant of it.",
    ),
    "injection": (
        "Untrusted input reaching an interpreter",
        "Can request input reach an interpreter without being made safe? Look for: eval or new Function, shell "
        "commands, database queries built by string concatenation or template strings (including $where and operator "
        "injection in NoSQL queries), and request values written into HTML or into a template whose escaping is off.",
    ),
    "outbound": (
        "Where the server sends users, connects, or reads files",
        "Can request input control where the server redirects the user, which address the server connects to, or "
        "which file it touches? Look for: redirects to a URL taken from the request, outbound HTTP requests to a URL "
        "built from request input (server-side request forgery), and file paths built from request input.",
    ),
    "session": (
        "Credentials, sessions and the login flow",
        "Are credentials and sessions handled safely? Look for: passwords stored or compared in plain text, weak or "
        "missing hashing, a session id that is not regenerated at login, a session that survives logout, error "
        "messages that reveal whether an account exists, hard-coded secrets, and tokens or passwords written to logs "
        "or responses.",
    ),
    "app": (
        "App-wide configuration",
        "Is the setup that affects every route safe? Look for: session cookie flags (httpOnly, secure, sameSite) and "
        "cookie names; hard-coded or default signing secrets; missing CSRF protection on state-changing routes; "
        "template engines with escaping disabled; missing or switched-off security headers (helmet, CSP, HSTS); "
        "verbose error or debug output; secrets in config files. Remember that code inside a comment is switched off.",
    ),
}
