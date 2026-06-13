/**
 * Follow-up question generation prompt.
 * V2 spec: Themed, targeted, mechanic-probing — not generic.
 * Each round focuses on ONE area: auth, pricing, social dynamics.
 */

export function getFollowUpPrompt(decomposition, conversationHistory, roundNumber) {
  // Determine which topic area has the lowest coverage score
  const coverage = decomposition.coverageScore || {};
  const topicPriority = Object.entries(coverage)
    .sort(([, a], [, b]) => a - b)
    .map(([topic]) => topic);

  const roundFocus = {
    1: {
      theme: "Authentication & Identity",
      instruction: `Focus ONLY on authentication and identity mechanics:
- How does account creation work? What uniquely identifies a user?
- Can someone create multiple accounts? What would stop them?
- What happens if their auth provider (e.g., Google) suspends their account?
- Session management — how long do sessions last? What happens on expiry?
- Password reset, account recovery, device limits.`,
    },
    2: {
      theme: "Pricing, Limits & Enforcement",
      instruction: `Focus ONLY on monetization mechanics and limit enforcement:
- What exactly counts against the limit? What doesn't?
- How and when does the counter reset?
- Is limit enforcement server-side or client-side?
- What happens exactly when a limit is hit? Hard block or soft warning?
- Can Pro features leak into free tier through any mechanism (shared rooms, invites, etc.)?
- Are there referral, trial, or promo mechanisms that could be exploited?`,
    },
    3: {
      theme: "Social Dynamics & Data Ownership",
      instruction: `Focus ONLY on multi-user mechanics and data ownership:
- In collaborative features (rooms, shared content): who owns what?
- Can users export or extract data? In what formats?
- What happens to shared content when a user leaves or deletes their account?
- Are there any moderation or admin tools?
- Can users interact in ways that affect others (rating, reporting, inviting, kicking)?
- What privacy controls exist between users?`,
    },
  };

  const focus = roundFocus[roundNumber] || {
    theme: "Remaining Edge Cases",
    instruction: `Based on the remaining gaps: ${JSON.stringify(decomposition.gaps?.slice(0, 5))}
Ask about anything still undefined. Focus on temporal aspects (what changes over time), system interactions (feature A + feature B), and administrative controls.`,
  };

  // Build implications to surface from the last decomposition
  const implicationsText =
    decomposition.interestingImplications?.length > 0
      ? `\nIMPLICATIONS TO SURFACE (mention these naturally if relevant):\n${decomposition.interestingImplications.map((i) => `  - ${i}`).join("\n")}`
      : "";

  // Build already-covered gaps to avoid repetition
  const gapsText =
    decomposition.gaps?.length > 0
      ? `\nKNOWN GAPS (don't re-ask these if already answered):\n${decomposition.gaps.slice(0, 6).map((g) => `  - ${g}`).join("\n")}`
      : "";

  return `You are Breakpoint, continuing a product interrogation conversation.

CONVERSATION SO FAR:
${conversationHistory}

CURRENT UNDERSTANDING:
- Entities: ${JSON.stringify(decomposition.entities?.stated || [])}
- Flows: ${JSON.stringify(decomposition.flows?.stated || [])}
- Boundaries: ${JSON.stringify(decomposition.boundaries?.stated || [])}
${gapsText}
${implicationsText}

THIS ROUND: Round ${roundNumber} — Topic: "${focus.theme}"
${focus.instruction}

YOUR RESPONSE MUST:
1. ACKNOWLEDGE in 1-2 sentences what you just learned (reference specific things they said)
2. If you spotted an interesting implication, mention it naturally: "That's interesting — so [implication]. That's worth probing."
3. Ask 3-5 TARGETED questions about the topic area above, grouped together
4. Make it feel like a conversation, not an interrogation form

AVOID:
- Generic questions ("Can you tell me more about...?")
- Repeating anything already answered
- Asking about topics not in this round's focus area
- Overwhelming with too many questions

FORMAT: Write your response as NATURAL CONVERSATION. Do NOT use bullet point lists for your questions — weave them into paragraphs like a real conversation. Do NOT output JSON.`;
}
