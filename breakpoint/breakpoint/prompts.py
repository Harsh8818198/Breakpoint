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
  "attack_category": str,          // one of: auth | authz | rate_limiting | data_privacy | billing | injection | crypto | config | supply_chain | ux
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

PRIOR_FINDINGS_HEADER = "----- WHAT EARLIER AGENTS ALREADY FOUND -----"
CATEGORY_DIVERSITY_HEADER = "----- ATTACK CATEGORY COVERAGE (steer toward uncovered categories) -----"

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
