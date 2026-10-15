"""Give each attacker agent the real source code that matters for the attack category it was assigned.

Why this exists: agents used to see only the Blueprint, a summary written from about 35 files x their first 5,000
characters. On OWASP NodeGoat that was enough to find 2 of 13 known bugs, because the code that holds the other 11
(a `$where` query, a redirect, a fixed cookie secret, the session options) was never in front of any agent.

How it works (no model calls, nothing is executed):
  1. One pass over the read-only `CodeIndex` scores every line against cues for each attack category: dangerous sinks
     (`eval(`, `res.redirect(`, an HTTP client), places input enters (`req.query`), and the names of security controls
     (`httpOnly`, `csrf`, `regenerate(`). Comment lines count for little, except a commented-out control, which is a lead.
  2. Hits close together become *regions*. A region's score says how likely it is to matter for the category.
  3. `assign()` hands every agent the best regions for its category. Agents that share a category get different regions,
     and code that earlier verified findings already point at is shown less, so later generations look somewhere new.
  4. Each agent also gets a CONTROL SEARCH: for the controls a category depends on (CSRF token, session regeneration, cookie
     flags, hashing...) where they are live in the code and where they appear only in comments. A missing protection is
     a lead the agent can check, not something it has to guess.

Agents can cite `file:line`. `check_refs` verifies each cited quote exists in the file it names before the citation is kept.
The verifier (codeverify.py) is unchanged: every finding still has to pass it.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from .codeindex import CodeIndex

# ---------------------------------------------------------------------------- what to look for
ALL_CATEGORIES = ["auth", "authz", "rate_limiting", "data_privacy", "billing",
                  "injection", "crypto", "config", "supply_chain", "ux",
                  "architecture", "code_quality", "error_handling", "scalability"]

# How much of an agent's slots a category deserves when the code gives it equal room (security first).
CATEGORY_WEIGHT = {
    "auth": 1.0, "authz": 1.0, "injection": 1.0, "crypto": 1.0, "config": 1.0, "data_privacy": 1.0,
    "rate_limiting": 0.6, "billing": 0.5, "supply_chain": 0.5, "error_handling": 0.4,
    "ux": 0.25, "architecture": 0.25, "code_quality": 0.25, "scalability": 0.25,
}

# Where untrusted input enters. Not a finding on its own; it raises a line that also holds a risky operation.
_SOURCE = (r"\b(?:req|request)\.(?:query|body|params|headers|cookies|args|form|GET|POST|json|values|data|files)\b"
           r"|\$_(?:GET|POST|REQUEST|COOKIE|FILES)\b|\bparams\[|\bgetParameter\s*\(|\bevent\.(?:body|queryStringParameters)\b"
           r"|\bctx\.(?:request|query)\b")
_SOURCE_CATS = {"injection", "authz", "data_privacy", "billing", "rate_limiting"}

_SECRET_ASSIGN = (r"\b\w*(?:secret|passw(?:or)?d|passwd|api_?key|private_?key|signing_?key|token|salt|client_?secret)"
                  r"\w*['\"]?\s*[:=]\s*['\"][^'\"\s]{4,}['\"]")
_ROUTE_DEF = (r"\b(?:app|router|api|bp|blueprint|server)\.(?:get|post|put|delete|patch|all|route)\s*\("
              r"|@(?:app|bp|router|blueprint)\.(?:route|get|post|put|delete)|@(?:Get|Post|Put|Delete|Patch|Request)Mapping"
              r"|\bRoute::(?:get|post|put|delete)|\bpath\s*\(\s*['\"]|\burl\s*\(\s*r?['\"]")
_SQL_BUILD = (r"\b(?:select\b.{0,80}\bfrom|insert\s+into|update\s+\w+\s+set|delete\s+from)\b.{0,100}"
              r"(?:\+|\$\{|%s|%\(|\{\w+\}|\.format\s*\()")
_QUERY_TEMPLATE = r"\.(?:query|execute|raw|exec)\s*\(\s*(?:f?[\"'`])[^\"'`]*(?:\$\{|[\"'`]\s*\+|%s|\{\w+\})"
_TODO = r"\b(?:TODO|FIXME|HACK|XXX|WORKAROUND)\b"
_SWALLOWED = r"catch\s*(?:\(\s*\w*\s*\))?\s*\{\s*\}|except[^:\n]*:\s*(?:pass|continue)\s*$"
_PASSWORD = r"\bpass(?:word|wd)\b|\bbcrypt\b|\bargon2\b|\bscrypt\b|\bpbkdf2\b|compareSync|checkpw|password_hash|password_verify|make_password|check_password"


@dataclass(frozen=True)
class Cue:
    category: str
    label: str
    pattern: str
    weight: float
    comments: bool = False           # a comment line that matches still counts in full (a commented-out control)
    only: str = ""                   # "manifest": dependency files only
    rx: re.Pattern = field(init=False, compare=False, repr=False, default=None)  # type: ignore[assignment]

    def __post_init__(self):
        object.__setattr__(self, "rx", re.compile(self.pattern, re.I))


def _cues() -> list[Cue]:
    c = Cue
    return [
        # ---- injection: dangerous operations fed by input
        c("injection", "dynamic code evaluation", r"\beval\s*\(|\bnew\s+Function\s*\(|\bvm\.(?:runIn\w+|Script)|setTimeout\s*\(\s*['\"`]", 3.5),
        c("injection", "operating-system command", r"\bchild_process\b|\bexecSync\b|\bspawnSync\b|\bexecFile\b|\bshell_exec\b|\bpassthru\b|\bproc_open\b|\bpopen\b|\bos\.system\s*\(|\bsubprocess\.\w+\s*\(|\bProcessBuilder\b|Runtime\.getRuntime\(\)\.exec|\b(?:cp|child_process)\.(?:exec|spawn)\s*\(", 3.0),
        c("injection", "query built from strings", _SQL_BUILD, 3.5),
        c("injection", "query built from a template", _QUERY_TEMPLATE, 3.0),
        c("injection", "server-side JavaScript in a database query", r"\$where\b|\$function\b|\$accumulator\b|\bmapReduce\b", 3.5),
        c("injection", "NoSQL operator", r"\$(?:ne|gt|gte|lt|lte|regex|or|and|in|nin|expr)\b", 1.0),
        c("injection", "redirect", r"\bredirect\s*\(|\bres\.location\s*\(|\bsendRedirect\b|\bHttpResponseRedirect\b|\bredirect_to\b|header\s*\(\s*['\"]Location", 2.2),
        c("injection", "server-side HTTP request", r"\b(?:needle|axios|superagent|requests|httpx|urlopen|RestTemplate|WebClient|curl_exec|file_get_contents|HTTParty|Net::HTTP)\b|\bhttps?\.(?:get|request)\s*\(|\b(?:got|fetch|request)\s*\(", 2.5),
        c("injection", "output without HTML escaping", r"\binnerHTML\b|\bouterHTML\b|insertAdjacentHTML|document\.write|dangerouslySetInnerHTML|v-html|\|\s*safe\b|\{\{\{|<%-|mark_safe|\bMarkup\s*\(|render_template_string", 2.5),
        c("injection", "template auto-escaping off", r"autoescape\s*[:=]\s*(?:false|off)|sanitize\s*[:=]\s*false", 3.5),
        c("injection", "unsafe deserialization", r"pickle\.loads?|yaml\.load\s*\(|\bunserialize\s*\(|ObjectInputStream|marshal\.loads|node-serialize|XMLDecoder|Marshal\.load|jsonpickle", 3.0),
        c("injection", "file path from input", r"\b(?:readFile|readFileSync|createReadStream|sendFile|writeFile|writeFileSync|unlink|file_get_contents|fopen|send_file|send_from_directory|FileInputStream)\b|\.\./", 1.5),
        c("injection", "pattern built at run time", r"new\s+RegExp\s*\(|re\.compile\s*\(\s*\w", 1.5),
        c("injection", "XML parsing", r"\b(?:parseXml|libxmljs|DocumentBuilder|SAXParser|xml2js|etree\.parse|XMLReader)\b", 1.5),
        c("injection", "output escaping or sanitising", r"\bescape\w*\s*\(|sanitiz\w+|DOMPurify|\bbleach\b|htmlspecialchars|encodeURIComponent", 0.8, comments=True),
        # ---- authz: who may do what
        c("authz", "route registration", _ROUTE_DEF, 1.6),
        c("authz", "access-control check", r"\b(?:isAdmin\w*|is_admin|is_staff|is_superuser|hasRole|has_role|hasPermission|has_perm|authori[sz]\w*|permission\w*|ability|rbac|login_required|permission_required|requireAuth|ensureAuth\w*|isAuthenticated|isLoggedIn\w*|before_action|authenticate_user)\b|@PreAuthorize|@Secured|@RolesAllowed", 1.6, comments=True),
        c("authz", "object chosen by a client-supplied id", r"\b(?:req|request)\.(?:params|query|body)(?:\.\w*id\b|\[['\"]\w*id)|\bparams\[:?['\"]?\w*id\b|\b(?:findById|find_by_id|findByPk|get_object_or_404|getById|findUnique)\b", 2.2),
        c("authz", "user id", r"\buser_?id\b", 0.8),
        c("authz", "identity taken from the session", r"\b(?:req\.session|session)\.(?:userId|user_id|user|uid)\b|\breq\.user\b|\bcurrent_user\b|\bg\.user\b|\brequest\.user\b|SecurityContextHolder", 1.5),
        c("authz", "role or privilege field", r"\b(?:isAdmin|is_admin|role|roles|privilege|isSuperuser|userType|user_type)\b\s*[:=]", 1.5),
        # ---- auth: logging in, sessions, passwords
        c("auth", "login success point", r"\b(?:req\.session|request\.session|session)(?:\.|\[['\"])(?:userId|user_id|user|uid|loggedIn|isLoggedIn|authenticated)\b[^=\n]*=", 3.0),
        c("auth", "session id handling", r"\b(?:regenerate|session_regenerate_id|reset_session|rotate|cycle_key|destroy|logout_user|invalidate)\s*\(", 2.0, comments=True),
        c("auth", "password handling", _PASSWORD, 1.5),
        c("auth", "login / signup / reset handler", r"\b(?:login|logout|signin|sign_in|signup|sign_up|register|forgot|reset_?password|authenticate|handleLogin\w*|validateLogin|session_?handler)\b", 1.2),
        c("auth", "different message for unknown user and wrong password", r"(?:invalid|unknown|no such|incorrect|wrong|unregistered|not found)[\s_-]*(?:user\s?name|user|account|e-?mail|login)\b|(?:invalid|incorrect|wrong)[\s_-]*password", 2.5),
        c("auth", "CSRF token", r"\b(?:csrf|csurf|xsrf|anti[-_]?forgery)\w*", 2.0, comments=True),
        c("auth", "token / OAuth", r"\b(?:jwt|jsonwebtoken|bearer|oauth|openid|saml|passport)\b|\btoken\b", 1.2),
        c("auth", "session setup", r"\b(?:session|cookieSession|express-session)\s*\(\s*\{?", 1.5),
        c("auth", "rate limit / lockout", r"rate.?limit|throttle|lockout|max_?attempts|failed_?(?:login|attempts)|captcha", 1.5, comments=True),
        # ---- crypto
        c("crypto", "weak or broken primitive", r"\b(?:md5|sha-?1|3?des|rc4|rc2|blowfish|ecb)\b|createCipher\b|MessageDigest\.getInstance\(\s*['\"](?:MD5|SHA-?1)|hashlib\.(?:md5|sha1)", 3.0),
        c("crypto", "non-cryptographic randomness", r"\bMath\.random\b|\brandom\.(?:random|randint|choice)\b|\bmt_rand\b|\bnew\s+Random\s*\(|\bsrand\b", 2.0),
        c("crypto", "hard-coded secret or key", _SECRET_ASSIGN, 3.5),
        c("crypto", "password in a stored record", r"^\s*(?:password|passwd|pwd)\s*,?\s*(?://.*|#.*)?$|\bpassword\b[^\n]{0,40}\b(?:save|insert|store|hash|compare|equals)\b|\b(?:save|insert|store|hash|compare|equals)\b[^\n]{0,40}\bpassword\b|\bpassword\s*:\s*\w", 2.0),
        c("crypto", "hashing / encryption API", r"\b(?:createHash|createHmac|createCipheriv|createDecipheriv|hashlib|hmac|bcrypt|hashSync|compareSync|pbkdf2\w*|scrypt\w*|argon2\w*|jsonwebtoken)\b|\bCipher\.getInstance\b|\bjwt\.(?:sign|verify)\b", 1.5, comments=True),
        c("crypto", "certificate checks off", r"rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED|verify\s*=\s*False|InsecureSkipVerify|strictSSL\s*:\s*false|CURLOPT_SSL_VERIFYPEER", 3.5),
        c("crypto", "signing secret", r"\bsecret\b|\bcookieSecret\b|SECRET_KEY|\bsigning\b", 1.5),
        c("crypto", "unencrypted transport", r"http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|www\.w3)|\bhttp\.createServer\b", 1.5),
        # ---- config
        c("config", "session / cookie settings", r"\b(?:session|cookieSession|cookie-session|express-session|SessionMiddleware)\s*\(|\bcookie\s*:\s*\{|\.cookie\s*\(|\bset_cookie\s*\(|SESSION_COOKIE|\bsetCookie\b|Set-Cookie", 2.5),
        c("config", "cookie flag", r"\b(?:httpOnly|http_only|secure|sameSite|same_site|maxAge|max_age|expires)\s*[:=]", 2.0, comments=True),
        c("config", "security headers / CORS", r"\bhelmet\b|\bcors\s*\(|Access-Control-Allow|Content-Security-Policy|X-Frame-Options|X-Content-Type-Options|Strict-Transport-Security|x-powered-by|\bsetHeader\s*\(", 2.0, comments=True),
        c("config", "debug / verbose mode", r"\bdebug\s*[:=]\s*(?:true|1)\b|\bDEBUG\s*=\s*True|\bNODE_ENV\b|app\.run\s*\([^)]*debug|show_?errors|display_errors", 1.5),
        c("config", "server / listener setup", r"\.listen\s*\(|\bcreateServer\s*\(|\bapp\.run\s*\(|0\.0\.0\.0|ALLOWED_HOSTS|trust\s?proxy", 1.8),
        c("config", "template engine setup", r"\bautoescape\b|\bsetDefaults\b|app\.engine\s*\(|app\.set\s*\(\s*['\"]view", 2.0),
        c("config", "request body / upload handling", r"\bbodyParser\b|express\.json|express\.urlencoded|\bmulter\b", 1.2),
        c("config", "middleware stack", r"\bapp\.use\s*\(", 1.0),
        c("config", "secret in configuration", _SECRET_ASSIGN, 2.5),
        c("config", "session save options", r"\bsaveUninitialized\b|\bresave\b", 1.5),
        # ---- data privacy
        c("data_privacy", "sensitive personal field", r"\b(?:ssn|social_?security|dob|birth_?date|bank\w*|routing|account_?number|iban|credit_?card|card_?number|cvv|passport|salary|medical|diagnosis|tax_?id|phone|address|e-?mail)\b", 1.0),
        c("data_privacy", "password / secret field", r"\bpass(?:word|wd)\b|\bsecret\b|\btoken\b", 1.0),
        c("data_privacy", "value written to a log", r"\b(?:console\.(?:log|info|debug|error)|logger\.\w+|log\.(?:info|debug|warn|error)|System\.out\.print\w*|Log\.\w+)\s*\(", 1.2),
        c("data_privacy", "whole record returned or rendered", r"\bres\.(?:json|send|render)\s*\(|\bjsonify\s*\(|\bselect\s+\*|\.find\s*\(\s*\{\s*\}\s*\)|\.findAll\s*\(\s*\)|\.toJSON\s*\(|\.to_dict\s*\(", 1.5),
        c("data_privacy", "fields copied straight from the request", r"\bObject\.assign\s*\(|\.\.\.\s*req\.body|\$set\s*:\s*(?:req|\w*body)|update\w*\s*\(\s*(?:req|request)\.(?:body|json)|\*\*request\.(?:json|form|data)|params\.permit|\bfillable\b", 2.0),
        # ---- rate limiting
        c("rate_limiting", "rate limiter", r"rate.?limit|\bthrottle\b|\blimiter\b|slowDown|express-rate-limit|flask-limiter|@Throttle", 2.5, comments=True),
        c("rate_limiting", "attempt counting / lockout", r"max_?attempts|failed_?(?:login|attempts)|\block_?out\b|\brecaptcha\b|\bcaptcha\b|\bbrute\b", 2.5, comments=True),
        c("rate_limiting", "endpoint that sends mail / SMS", r"\b(?:sendMail|sendEmail|send_mail|nodemailer|twilio|sms|otp|sendgrid|smtp)\b|\bpassword_?reset|\bforgot", 1.8),
        c("rate_limiting", "login / signup endpoint", r"\b(?:login|signin|signup|register|authenticate)\b", 1.2),
        c("rate_limiting", "route registration", _ROUTE_DEF, 1.0),
        c("rate_limiting", "expensive operation", r"\bupload\b|\bmulter\b|\.skip\s*\(|\.limit\s*\(|\bfindAll\b|\bzip\b|\bpdf\b|\bexport\b", 0.8),
        # ---- billing / business rules
        c("billing", "money or quantity field", r"\b(?:price|amount|total|cost|fee|balance|credit|quantity|qty|discount|coupon|refund|currency|invoice|subtotal|wallet|points)\b", 1.2),
        c("billing", "payment provider", r"\b(?:stripe|paypal|razorpay|braintree|adyen|checkout|charge|payment|subscription|billing)\b", 1.5),
        c("billing", "limit or plan check", r"\b(?:quota|trial|premium|upgrade|entitlement|tier)\b|\bplan\b", 1.0),
        c("billing", "arithmetic on request values", r"\b(?:req|request)\.(?:body|query|params)\b[^\n]{0,60}[*+\-/]|[*+\-/][^\n]{0,60}\b(?:req|request)\.(?:body|query|params)\b", 1.5),
        # ---- supply chain
        c("supply_chain", "dependency", r"\"[@\w/.\-]+\"\s*:\s*\"[\^~*><=\w.\-]+\"|^[\w.\-]+\s*(?:==|>=|~=|<=)|^\s*(?:require|gem)\s+['\"]|<artifactId>|^\s*implementation\s", 1.0, only="manifest"),
        c("supply_chain", "install or build step", r"npm\s+(?:install|i)\b|pip\s+install|curl\s[^|\n]*\|\s*(?:sudo\s+)?(?:ba)?sh|wget\s[^|\n]*\|\s*(?:ba)?sh|apt-get\s+install|\bpostinstall\b|\bpreinstall\b|FROM\s+\S+:latest", 2.5),
        c("supply_chain", "unpinned version", r"[\"']\s*(?:\*|latest|x)\s*[\"']|[\^~]\d|>=\s*\d", 1.0, only="manifest"),
        c("supply_chain", "script loaded from another site", r"<script[^>]+src=[\"']https?://|importScripts|\bcdn\.", 2.0),
        c("supply_chain", "module loaded by a computed name", r"\brequire\s*\(\s*[^'\"\s)]|\bimport\s*\(\s*[^'\"\s)]|importlib\.import_module|__import__", 2.0),
        # ---- ux
        c("ux", "message shown to the user", r"\balert\s*\(|\bflash\s*\(|\btoast\b|\berrorMessage\b|\berror_message\b", 0.8),
        c("ux", "form input rules", r"\brequired\b|\bmaxlength\b|\bminlength\b|\bvalidate\w*|\bisValid\b|\bautocomplete\b|type=[\"']password", 1.0),
        c("ux", "form / destructive action", r"<form\b|\bconfirm\s*\(|\bunsubscribe\b|\bdestroy\b", 1.2),
        c("ux", "state change through GET", r"\bapp\.get\s*\([^)]*(?:delete|remove|logout|update|add|create)", 1.5),
        # ---- architecture
        c("architecture", "shared mutable state", r"\bglobal\.|\bglobalThis\.|\bwindow\.\w+\s*=|^\s*(?:var|let)\s+\w+\s*=\s*(?:\{\}|\[\])\s*;", 1.5),
        c("architecture", "in-process cache / queue / timer", r"\bsetInterval\b|\bnew\s+Map\s*\(|\bcache\b|\bqueue\b|\bcron\b|\bcluster\.fork\b|process\.on\s*\(", 1.3),
        c("architecture", "hard-wired dependency", r"\bnew\s+[A-Z]\w*(?:DAO|Service|Client|Repository|Manager|Handler)\s*\(", 1.3),
        c("architecture", "known shortcut", _TODO + r"|\btemporary\b|\bfor now\b", 1.5, comments=True),
        # ---- code quality
        c("code_quality", "TODO / FIXME / HACK", _TODO, 1.8, comments=True),
        c("code_quality", "lint or type checks suppressed", r"eslint-disable|\bjshint\b|noinspection|@ts-ignore|@ts-nocheck|type:\s*ignore|# noqa|pylint:\s*disable|NOSONAR", 2.0, comments=True),
        c("code_quality", "debug output left in", r"\bconsole\.log\b|\bdebugger\b|\bvar_dump\b", 0.8),
        c("code_quality", "error swallowed", _SWALLOWED, 2.5),
        c("code_quality", "commented-out code", r"^\s*(?://|#)\s*[\w.$]+\s*(?:\(|=).*[;{})]\s*$", 1.2, comments=True),
        # ---- error handling
        c("error_handling", "error details sent to the client", r"\b(?:err|error|e|ex)\.(?:stack|message)\b|printStackTrace|traceback\.|\.stack\b|\bres\.(?:send|json)\s*\(\s*(?:err|error|e)\b", 2.5),
        c("error_handling", "error swallowed", _SWALLOWED, 2.5),
        c("error_handling", "error handling", r"\b(?:catch|except|rescue|finally|errorHandler|uncaughtException|unhandledRejection)\b|next\s*\(\s*err|process\.exit", 1.0),
        c("error_handling", "error argument", r"function\s*\(\s*\w*err\w*\b|\(\s*err\s*,\s*[^)]*\)\s*=>", 1.0),
        c("error_handling", "throw / assert", r"\bthrow\b|\bassert\b|\braise\b", 0.8),
        # ---- scalability
        c("scalability", "unbounded query / load everything", r"\.find\s*\(\s*\{\s*\}\s*\)|\.findAll\s*\(|\bselect\s+\*|\.all\s*\(\s*\)|\.toArray\s*\(|objects\.all\(|\breadAll\b", 2.0),
        c("scalability", "blocking call", r"\breadFileSync\b|\bwriteFileSync\b|\bexecSync\b|\bspawnSync\b|time\.sleep|Thread\.sleep", 2.0),
        c("scalability", "await inside a loop", r"\b(?:for|while)\b[^\n]*\bawait\b|forEach\s*\(\s*async", 2.0),
        c("scalability", "in-process state", r"\bnew\s+Map\b|\bcache\b|\bglobal\.|MemoryStore|in-?memory|singleton", 1.5),
        c("scalability", "paging", r"\.limit\s*\(|\.skip\s*\(|\boffset\b|paginat|page_?size|per_?page", 1.2),
        c("scalability", "timer / background loop", r"\bsetInterval\b|while\s*\(\s*(?:true|1)\s*\)|\bcron\b|\bworker\b", 1.5),
    ]


# Protections each category depends on. The control search reports where each one is live and where it is only a comment.
CONTROLS: dict[str, list[tuple[str, str]]] = {
    "auth": [
        ("CSRF protection", r"csrf|csurf|xsrf|anti.?forgery"),
        ("session id regenerated", r"\bregenerate\s*\(|session_regenerate_id|reset_session|cycle_key"),
        ("password hashing", r"\bbcrypt\b|\bargon2\b|\bscrypt\b|\bpbkdf2\b|password_hash|make_password"),
        ("login rate limit / lockout", r"rate.?limit|throttle|lockout|max_?attempts|captcha"),
        ("session destroyed on logout", r"session\.destroy|logout_user|session\.clear|invalidate\s*\("),
    ],
    "authz": [
        ("role / admin check", r"\bisAdmin\w*|is_admin|is_staff|hasRole|has_role|hasPermission|authori[sz]\w*|@PreAuthorize|login_required|permission_required"),
        ("identity taken from the session", r"\breq\.session\.\w*id\b|\bsession\.(?:userId|user_id)\b|\breq\.user\b|\bcurrent_user\b|\brequest\.user\b"),
    ],
    "config": [
        ("httpOnly cookie flag", r"httpOnly|http_only|SESSION_COOKIE_HTTPONLY"),
        ("Secure cookie flag", r"\bsecure\s*:\s*true|SESSION_COOKIE_SECURE|cookie_secure"),
        ("SameSite cookie flag", r"sameSite|same_site|SESSION_COOKIE_SAMESITE"),
        ("security headers / CSP", r"\bhelmet\b|Content-Security-Policy|X-Frame-Options|X-Content-Type-Options|Strict-Transport-Security"),
        ("CORS policy", r"\bcors\b|Access-Control-Allow"),
        ("HTTPS / TLS server", r"https\.createServer|SECURE_SSL_REDIRECT|ssl_context|\bhsts\b"),
        ("CSRF protection", r"csrf|csurf|xsrf"),
    ],
    "crypto": [
        ("password hashing", r"\bbcrypt\b|\bargon2\b|\bscrypt\b|\bpbkdf2\b|password_hash|make_password"),
        ("secure randomness", r"randomBytes|secrets\.token|SecureRandom|crypto\.random"),
        ("secret read from the environment", r"process\.env|os\.environ|getenv|System\.getenv|ENV\["),
        ("TLS certificate verification", r"rejectUnauthorized\s*:\s*true|verify\s*=\s*True"),
    ],
    "injection": [
        ("output escaping / sanitising", r"\bescape\w*\s*\(|sanitiz\w+|DOMPurify|\bbleach\b|htmlspecialchars|autoescape\s*[:=]\s*true"),
        ("input validation library", r"\bvalidator\b|\bjoi\b|\bzod\b|marshmallow|pydantic|express-validator"),
        ("parameterised queries", r"\bprepare\s*\(|parameteri[sz]ed|\bbindParam\b|bind_param|PreparedStatement"),
        ("redirect target allow-list", r"allowlist|whitelist|allowed_?hosts|is_safe_url|url_has_allowed_host"),
    ],
    "rate_limiting": [("rate limiter", r"rate.?limit|throttle|\blimiter\b|slowDown"),
                      ("lockout / captcha", r"lockout|max_?attempts|captcha")],
    "data_privacy": [
        ("encryption of stored data", r"\bencrypt\w*|\bcipher\b|\bkms\b|\bvault\b"),
        ("log redaction", r"\bredact\w*|\bmask\w*"),
        ("field allow-list on input", r"\.pick\s*\(|\bpermit\s*\(|attributes\s*:|\bonly\s*\("),
    ],
}

_VENDOR_SEGS = {"vendor", "vendors", "third_party", "third-party", "thirdparty", "bower_components", "node_modules",
                "site-packages", "external", "externals"}
_TEST_SEGS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "cypress", "fixtures", "__mocks__", "mocks", "testdata", "testing"}
_DOC_SEGS = {"docs", "doc", "documentation", "examples", "example", "samples", "sample"}
_DOC_EXTS = {".md", ".rst", ".txt", ".adoc", ".markdown"}
_DOC_NAMES = {"license", "licence", "copying", "authors", "notice", "changelog", "contributing", "readme", "code_of_conduct"}
_MANIFESTS = {"package.json", "requirements.txt", "pipfile", "pyproject.toml", "go.mod", "pom.xml", "gemfile",
              "composer.json", "build.gradle", "cargo.toml"}
_MARKUP_EXTS = {".html", ".htm", ".xml", ".vue", ".svelte", ".njk", ".jinja", ".erb"}
_TEMPLATE_CODE = re.compile(r"\{\{|\{%|<%|<\?|<script|</script|<form|<input|<iframe|\bon\w+\s*=|\bsrc\s*=", re.I)


def markup_code_mask(lines: list[str]) -> list[bool]:
    """For a page or template: True on lines that can run or submit something (template tags, <script> bodies, forms,
    event handlers). Prose, links, and anything inside <pre> are documentation about code, not code."""
    out, in_pre, in_script = [], False, False
    for ln in lines:
        low = ln.lower()
        if "<pre" in low:
            in_pre = True
        out.append(not in_pre and (in_script or bool(_TEMPLATE_CODE.search(ln))))
        if "</pre" in low:
            in_pre = False
        if "<script" in low and "</script" not in low:
            in_script = True
        elif "</script" in low:
            in_script = False
    return out


_ENTRY_NAMES = re.compile(r"server|app|main|index|route|controller|handler|view|api|auth|session|login|user|config|setting|middleware|dao|model", re.I)
_MAXLEN = 600


def file_weight(path: str) -> float:
    """How much the code in this file deserves to be shown. 0 = third-party / generated: never retrieved."""
    p = path.lower().replace("\\", "/")
    parts = p.split("/")
    name = parts[-1]
    ext = os.path.splitext(name)[1]
    if any(s in _VENDOR_SEGS for s in parts[:-1]) or ".min." in name or name.startswith(("jquery", "bootstrap")):
        return 0.0
    w = 1.0
    if name in _MANIFESTS:
        return 1.0
    if any(s in _TEST_SEGS for s in parts[:-1]) or name.startswith(("test_", "spec_")) or re.search(r"[._-](test|spec)\.\w+$", name):
        w = 0.2
    elif any(s in _DOC_SEGS for s in parts[:-1]) or ext in _DOC_EXTS or name in _DOC_NAMES:
        w = 0.1
    elif ext in (".css", ".scss", ".less"):
        w = 0.2
    elif ext in (".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf"):
        w = 0.6
    elif ext in _MARKUP_EXTS:
        w = 0.8
    if _ENTRY_NAMES.search(name):
        w *= 1.15
    return w


@dataclass(frozen=True)
class Region:
    """A stretch of one file that is worth an agent's attention for one category."""
    path: str
    start: int
    end: int
    score: float
    labels: tuple[str, ...]
    category: str

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.path, self.start, self.end)


@dataclass
class Retrieval:
    """What one agent is shown: numbered source for its category plus the control search."""
    category: str
    text: str
    regions: list[Region] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.regions)


def check_refs(index: CodeIndex, refs) -> list[dict]:
    """Keep only citations whose quote really exists as live code in the file named, and give each its true line number.
    A citation proves only that the code exists, not that the claim about it is right: the verifier decides that."""
    out: list[dict] = []
    for r in refs[:4] if isinstance(refs, list) else []:
        if not isinstance(r, dict):
            continue
        path = index.resolve_path(r.get("file", ""))
        quote = r.get("quote", "")
        if not path or not isinstance(quote, str) or not quote.strip():
            continue
        near = r.get("line") if isinstance(r.get("line"), int) else None
        line = index.find_quote(path, quote, near=near)
        if line is None or index.span_is_comment(path, line, quote):
            continue
        out.append({"file": path, "line": line, "quote": " ".join(quote.split())[:240]})
    return out


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


class CodeRetriever:
    PAD_BEFORE, PAD_AFTER, GAP, MAX_SPAN = 6, 14, 10, 50
    MIN_REGION_SCORE = 1.2          # below this a region is noise
    STRONG = 2.5                    # a region at least this strong counts as "room" for another agent
    ROOM_CAP = 8

    def __init__(self, index: CodeIndex, *, budget_chars: int = 22000, max_regions: int = 16, whole_file_chars: int = 4500):
        self.index = index
        self.budget, self.max_regions, self.whole = budget_chars, max_regions, whole_file_chars
        self._cues = _cues()
        by_cat: dict[str, list[Cue]] = {}
        for cue in self._cues:
            by_cat.setdefault(cue.category, []).append(cue)
        self._by_cat = by_cat
        self._cat_rx = {c: re.compile("|".join(f"(?:{q.pattern})" for q in cs), re.I) for c, cs in by_cat.items()}
        self._master = re.compile("|".join(f"(?:{q.pattern})" for q in self._cues), re.I)
        self._source = re.compile(_SOURCE, re.I)
        self._shown: dict[str, Counter] = {}
        self._controls: dict[str, str] = {}
        self.regions: dict[str, list[Region]] = {c: [] for c in ALL_CATEGORIES}
        self._scan()

    # ------------------------------------------------------------------ the one pass over the repository
    def _scan(self) -> None:
        index = self.index
        hits: dict[str, dict[str, list[tuple[int, float, str]]]] = {c: {} for c in ALL_CATEGORIES}
        for path in index.paths():
            fw = file_weight(path)
            if fw <= 0:
                continue
            ext = os.path.splitext(path)[1].lower()
            manifest = os.path.basename(path).lower() in _MANIFESTS
            lines = index.lines(path)
            code_like = markup_code_mask(lines) if ext in _MARKUP_EXTS else None
            for i, raw in enumerate(lines):
                text = raw[:_MAXLEN]
                display = code_like is not None and not code_like[i]    # prose / <pre> examples on a page are not code
                if not text.strip() or not self._master.search(text):
                    continue
                comment = index.is_comment(path, i + 1)
                has_source = None
                for cat, cues in self._by_cat.items():
                    if cat not in hits or not self._cat_rx[cat].search(text):
                        continue
                    score, labels = 0.0, []
                    for cue in cues:
                        if cue.only == "manifest" and not manifest:
                            continue
                        if not cue.rx.search(text):
                            continue
                        w = cue.weight * (0.3 if comment and not cue.comments else 1.0)
                        score += w
                        labels.append(cue.label)
                    if not labels:
                        continue
                    if cat in _SOURCE_CATS:
                        if has_source is None:
                            has_source = bool(self._source.search(text))
                        if has_source:
                            score += 1.0
                            labels.append("request input")
                    score = min(score, 6.0) * fw * (0.1 if display else 1.0)
                    if score > 0:
                        hits[cat].setdefault(path, []).append((i + 1, score, labels[0] if len(labels) == 1 else ", ".join(dict.fromkeys(labels))))
        for cat in ALL_CATEGORIES:
            regions: list[Region] = []
            for path, lines in hits[cat].items():
                regions += self._regions(cat, path, lines)
            regions.sort(key=lambda r: (-r.score, r.path, r.start))
            self.regions[cat] = regions

    def _regions(self, cat: str, path: str, lines: list[tuple[int, float, str]]) -> list[Region]:
        n = len(self.index.lines(path))
        groups: list[list[tuple[int, float, str]]] = []
        for hit in lines:
            if groups and hit[0] - groups[-1][-1][0] <= self.GAP and hit[0] - groups[-1][0][0] <= self.MAX_SPAN:
                groups[-1].append(hit)
            else:
                groups.append([hit])
        out = []
        for g in groups:
            ss = sorted((s for _, s, _ in g), reverse=True)
            score = sum(s * (0.85 ** k) for k, s in enumerate(ss))
            if score < self.MIN_REGION_SCORE:
                continue
            labels: dict[str, None] = {}
            for _, _, lab in sorted(g, key=lambda h: -h[1]):
                for part in lab.split(", "):
                    labels.setdefault(part, None)
            out.append(Region(path, max(1, g[0][0] - self.PAD_BEFORE), min(n, g[-1][0] + self.PAD_AFTER),
                              round(score, 2), tuple(list(labels)[:3]), cat))
        return out

    # ------------------------------------------------------------------ who looks at what
    def _covered(self, findings: Iterable) -> list[tuple[str, int]]:
        pts = []
        for f in findings:
            for e in list(getattr(f, "evidence", None) or []) + list(getattr(f, "code_refs", None) or []):
                if isinstance(e, dict) and e.get("file") and isinstance(e.get("line"), int):
                    pts.append((e["file"], e["line"]))
        return pts

    @staticmethod
    def _is_covered(r: Region, pts: list[tuple[str, int]]) -> bool:
        return any(p == r.path and r.start - 2 <= ln <= r.end + 2 for p, ln in pts)

    def room(self, category: str, findings: Iterable = ()) -> int:
        """How many separate strong regions of unexamined code this category still has."""
        pts = self._covered(findings)
        strong = [r for r in self.regions.get(category, []) if r.score >= self.STRONG and not self._is_covered(r, pts)]
        return min(len(strong), self.ROOM_CAP)

    def plan_categories(self, n_agents: int, findings: list) -> list[str]:
        """One attack category per agent. A category earns agents in proportion to how much unexamined code it has
        (a category the repository gives nothing to gets none), so several agents can work the busy ones, each on
        different code. Falls back to the plain round-robin when the code offers no leads at all."""
        have = Counter(getattr(f, "attack_category", "") for f in findings)
        room = {c: self.room(c, findings) for c in ALL_CATEGORIES}
        taken: Counter = Counter()
        chosen: list[str] = []
        for _ in range(n_agents):
            best, best_p = None, 0.0
            for c in ALL_CATEGORIES:
                if room[c] <= 0 or taken[c] >= room[c]:
                    continue
                p = CATEGORY_WEIGHT.get(c, 0.25) * (0.3 if have[c] >= 3 else 1.0) * room[c] / (taken[c] + 1)
                if p > best_p:
                    best, best_p = c, p
            if best is None:
                break
            taken[best] += 1
            chosen.append(best)
        if len(chosen) < n_agents:
            rest = sorted(ALL_CATEGORIES, key=lambda c: (have[c] >= 3, have[c] + taken[c]))
            for i in range(n_agents - len(chosen)):
                chosen.append(rest[i % len(rest)])
        return chosen

    def assign(self, categories: list[str], findings: list) -> list[Retrieval]:
        """A Retrieval per agent, aligned with `categories`. Agents with the same category get different regions."""
        pts = self._covered(findings)
        out: list[Retrieval | None] = [None] * len(categories)
        groups: dict[str, list[int]] = {}
        for i, c in enumerate(categories):
            groups.setdefault(c, []).append(i)
        for cat, idxs in groups.items():
            for slot, i in enumerate(idxs):
                out[i] = self.retrieve(cat, slot=slot, slots=len(idxs), covered=pts)
        for cat, idxs in groups.items():
            seen = self._shown.setdefault(cat, Counter())
            for i in idxs:
                for r in out[i].regions:                  # type: ignore[union-attr]
                    seen[r.key] += 1
        return out                                         # type: ignore[return-value]

    def retrieve(self, category: str, *, slot: int = 0, slots: int = 1, covered: list[tuple[str, int]] | None = None) -> Retrieval:
        pts = covered or []
        seen = self._shown.get(category, Counter())
        pool = self.regions.get(category) or self._fallback_regions()

        def rank(r: Region) -> float:
            return r.score * (0.35 if self._is_covered(r, pts) else 1.0) * (0.6 ** seen.get(r.key, 0))

        ranked = sorted(pool, key=lambda r: (-rank(r), r.path, r.start))
        own = [r for i, r in enumerate(ranked) if i % max(slots, 1) == slot]
        rest = [r for i, r in enumerate(ranked) if i % max(slots, 1) != slot]
        chosen: list[Region] = []
        used: dict[str, list[tuple[int, int]]] = {}
        for r in own + rest:
            if len(chosen) >= self.max_regions:
                break
            trial = dict(used)
            trial[r.path] = used.get(r.path, []) + [(r.start, r.end)]
            if chosen and self._cost(trial) > self.budget:
                continue
            chosen.append(r)
            used = trial
        return Retrieval(category, self._render(category, chosen, used), chosen, list(used))

    def _fallback_regions(self) -> list[Region]:
        pool = [r for c in ("injection", "auth", "authz", "config", "crypto") for r in self.regions.get(c, [])]
        return sorted(pool, key=lambda r: -r.score)

    # ------------------------------------------------------------------ rendering
    def _ranges(self, path: str, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        lines = self.index.lines(path)
        merged = _merge(ranges)
        size = sum(len(x) + 1 for x in lines)
        shown = sum(sum(len(x) + 1 for x in lines[a - 1:b]) for a, b in merged)
        if size <= self.whole or shown >= 0.6 * size:
            return [(1, len(lines))]
        return merged

    def _cost(self, used: dict[str, list[tuple[int, int]]]) -> int:
        total = 0
        for path, rs in used.items():
            lines = self.index.lines(path)
            total += sum(sum(len(x) + 14 for x in lines[a - 1:b]) for a, b in self._ranges(path, rs)) + len(path) + 40
        return total

    def _render(self, category: str, chosen: list[Region], used: dict[str, list[tuple[int, int]]]) -> str:
        if not chosen:
            return ""
        best: dict[str, float] = {}
        leads: dict[str, dict[str, None]] = {}
        for r in chosen:
            best[r.path] = max(best.get(r.path, 0.0), r.score)
            for lab in r.labels:
                leads.setdefault(r.path, {}).setdefault(lab, None)
        blocks = []
        for path in sorted(used, key=lambda p: (-best[p], p)):
            body = self.index._render(path, self._ranges(path, used[path]), limit=None)
            hint = ", ".join(list(leads.get(path, {}))[:4])
            blocks.append(body + (f"\n      | (why retrieved: {hint})" if hint else ""))
        head = (f"RETRIEVED FOR YOUR ASSIGNED CATEGORY '{category}': {len(chosen)} code regions from {len(used)} files, "
                f"most relevant first. Not the whole repository: other files exist.")
        return head + "\n\n" + "\n\n".join(blocks) + self._control_search(category)

    # ------------------------------------------------------------------ control search (live vs commented out)
    def _control_search(self, category: str) -> str:
        cached = self._controls.get(category)
        if cached is None:
            cached = self._controls[category] = self._build_controls(category)
        return cached

    def _build_controls(self, category: str) -> str:
        controls = CONTROLS.get(category)
        if not controls:
            return ""
        rxs = [(label, re.compile(pat, re.I)) for label, pat in controls]
        kinds = ("server code", "templates", "dependency list")
        live: dict[str, dict[str, list[tuple[str, int]]]] = {label: {k: [] for k in kinds} for label, _ in rxs}
        dead: dict[str, list[tuple[str, int]]] = {label: [] for label, _ in rxs}
        for path in self.index.paths():
            if file_weight(path) < 0.5:
                continue
            lines = self.index.lines(path)
            ext = os.path.splitext(path)[1].lower()
            templ = ext in _MARKUP_EXTS
            code_like = markup_code_mask(lines) if templ else None
            kind = ("dependency list" if os.path.basename(path).lower() in _MANIFESTS
                    else "templates" if templ else "server code")
            for i, raw in enumerate(lines):
                if code_like is not None and not code_like[i]:
                    continue
                text = raw[:_MAXLEN]
                for label, rx in rxs:
                    if rx.search(text):
                        if self.index.is_comment(path, i + 1):
                            dead[label].append((path, i + 1))
                        else:
                            live[label][kind].append((path, i + 1))

        def where(items: list[tuple[str, int]]) -> str:
            return ", ".join(f"{p}:{ln}" for p, ln in items[:3]) + (" ..." if len(items) > 3 else "")

        rows = []
        for label, _ in rxs:
            parts = [f"{k}: {where(live[label][k])}" for k in kinds if live[label][k]]
            if not live[label]["server code"]:
                parts.insert(0, "server code: NONE")
            if dead[label]:
                parts.append(f"commented out (NOT active): {where(dead[label])}")
            rows.append(f"  {label} -> " + " | ".join(parts))
        return ("\n\nCONTROL SEARCH for '" + category + "' (every source file; a name that only appears in a template, a dependency "
                "list or a comment is NOT proof the server enforces it. A control missing from server code is a lead to check in "
                "the code above, not proof):\n" + "\n".join(rows))

    # ------------------------------------------------------------------ citations
    def check_refs(self, refs) -> list[dict]:
        return check_refs(self.index, refs)

    def summary(self) -> dict[str, int]:
        return {c: sum(1 for r in rs if r.score >= self.STRONG) for c, rs in self.regions.items()}
