# Positioning: what Breakpoint is, who pays, how to say it

Researched 2026-10-29 (web search, sources at the bottom). Read this as a recommendation, not a fact. The "who pays" part is a guess nobody has tested.

## What the research says

1. **The pain is real and growing.** curl ended its bug bounty on 2026-01-31 after the share of real reports fell below 5%. Google paused its open-source bounty in October 2026. Bugcrowd's queues grew 334% in three weeks. HackerOne says 60-80% of submissions are invalid. Anthropic's Glasswing disclosed 1,596 findings across 281 projects and only 97 were confirmed patched. Microsoft now says the bottleneck is deciding which reports are real. "Verification is the bottleneck" is the mainstream view.
2. **A mixed signal.** curl's real-report rate recovered to about 15-16% by April 2026, through policy (no cash, reports through HackerOne), not through a tool. So "maintainers need a tool" is not proven, and maintainers do not pay.
3. **"A tool that proves a finding is exploitable" is crowded.** Funded: ZAST.AI ($6M seed), Staris ($5.7M), MindFort (YC, $3M+), Veria Labs (YC, $3.2M), Parameter (YC W26), 0.security (YC F26), OpenHack (YC F26, one founder), Provally. HackerOne (Hai Triage, paid) and Bugcrowd have their own. Free tools for maintainers already exist: ZeroQuarry, Ravn, Substantiate, sloptriage, VulnRap.
4. **"Automated security research lab" is not a unique phrase.** MindFort ("applied AI security lab"), Cracken ("applied AI lab"), and ZAST ("automated security research") all use it.
5. **Where the gap is.** Vendors grade themselves. Devin's own post says vendor benchmarks "quote recall numbers we can't audit". RealVuln, the best open benchmark, uses teaching apps and lists post-cutoff repos as future work. Nobody I found measures **how stable a verdict is when you ask again**. That is our actual, measured finding.

## Recommendation

**Say this:** "Breakpoint is the independent referee for AI-found vulnerabilities. When a tool or a bounty hunter says 'this is a real bug', we check it against the real code, and we publish how often we're right, including how often we change our mind."

**First product:** a verdict on each incoming vulnerability report, with the evidence and a measured accuracy. Start with one language and one bug class where running the exploit is feasible (Node, e.g. prototype pollution and path traversal).

**Who pays (hypothesis):** companies and platforms that run bounty or disclosure programs and get flooded. They already pay for triage (HackerOne sells it).

**Who gets it free:** open-source maintainers. It builds trust, and every human verdict becomes labelled data for the accuracy numbers.

**Where the lab fits:** the long-term shape. Lead with the referee, not the lab.

## What must be true before this is fundable

- Executable proof for one narrow bug class, so the verdict is not a coin flip.
- One honest number on held-out, post-cutoff real bugs, with repeats.
- Three conversations with people who run a bounty or disclosure program, to test whether they would pay.

## Words to drop

"scanner", "evolutionary adversarial simulation", "agent populations", "lab" as the headline.

## Sources

- Ars Technica, curl ends bounty: https://arstechnica.com/security/2026/01/overrun-with-ai-slop-curl-scraps-bug-bounties-to-ensure-intact-mental-health/
- OpenSSF guidance with curl's 2026 rates: https://best.openssf.org/Finding-and-Fixing-Vulnerabilities-Using-AI/handle-external-findings.html
- Computer Weekly, Google pauses OSS VRP: https://www.computerweekly.com/news/366651792/AI-slop-overwhelms-Googles-OSS-bug-bounty-programme
- Bugcrowd, queues up 334%: https://www.bugcrowd.com/blog/bugcrowd-policy-changes-to-address-ai-slop-submissions/
- HackerOne Hai Triage: https://www.hackerone.com/platform/triage
- Microsoft, validation is the new constraint: https://www.microsoft.com/en-us/security/blog/2026/10/07/3-lessons-from-frontier-ai-vulnerability-research/
- Glasswing remediation gap numbers: https://tensorr.com/blog/ai-remediation-gap
- Funded competitors: https://www.ycombinator.com/companies/industry/Cybersecurity, https://www.mindfort.ai/blog/seed-announcement, https://verialabs.com/blog/announcing-veria-labs-seed-round/
- Free maintainer tools: https://zeroquarry.com/open-source/, https://github.com/RavnSecurity/ravn-platform, https://pypi.org/project/substantiate/
- Benchmarks: https://realvuln.com/, https://devin.ai/blog/security-swarm-eval

Vendor figures (precision, noise removed) come from the vendors' own pages and were not checked.
