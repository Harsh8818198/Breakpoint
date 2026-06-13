/**
 * Product decomposition prompt — extracts structured understanding from conversation.
 * V2: More granular gaps and risk signal extraction.
 */

export function getDecompositionPrompt(conversationHistory) {
  return `You are analyzing a product interrogation conversation to extract a structured decomposition. This decomposition will be used to generate targeted follow-up questions and eventually a Product Blueprint.

CONVERSATION SO FAR:
${conversationHistory}

Extract the following. For each category, distinguish what has been EXPLICITLY STATED vs what is IMPLIED but not confirmed.

Respond ONLY in valid JSON:

{
  "entities": {
    "stated": ["Explicitly mentioned actors/roles/resources: users, roles, content types, data stores"],
    "implied": ["Entities implied but not confirmed — e.g., 'admin role' if moderation was mentioned"]
  },
  "flows": {
    "stated": ["User journeys explicitly described: signup, question-asking, quiz generation, payment, etc."],
    "implied": ["Flows that probably exist but weren't described — e.g., 'account deletion flow'"]
  },
  "boundaries": {
    "stated": ["Explicit transitions: free→paid, anonymous→authenticated, private→shared, individual→group"],
    "implied": ["Boundaries that probably exist but weren't confirmed"]
  },
  "gaps": [
    "SPECIFIC unanswered questions about mechanics, edge cases, or boundary behavior. Each gap must be a single, answerable question. Minimum 8 gaps if possible.",
    "Examples of good gaps:",
    "  - 'When a Pro user creates a study room, can free users in that room generate quizzes?'",
    "  - 'Does the daily question counter reset at midnight UTC or user-local time?'",
    "  - 'What happens to room content when the room creator deletes their account?'",
    "  - 'Can a user be in multiple rooms simultaneously?'",
    "  - 'Are uploaded notes visible only to the uploader or to all room members?'"
  ],
  "keyFeatures": ["Main product features identified so far"],
  "riskSignals": [
    "Early exploitation opportunities you already spotted. Be SPECIFIC about the mechanic:",
    "  - 'Free users in Pro-created rooms may get unlimited quiz access through the room'",
    "  - 'Multiple Google accounts per person = trivial daily limit bypass'",
    "  - 'Client-side quiz answers = answer extraction via browser devtools'"
  ],
  "interestingImplications": [
    "Things that sound innocent but have interesting exploitation potential — note these so the follow-up can surface them to the user"
  ],
  "coverageScore": {
    "auth": 0,
    "pricing": 0,
    "data": 0,
    "social": 0,
    "limits": 0
  }
}

RULES:
- Gaps must be SPECIFIC and ANSWERABLE — not vague like "need more info about rooms"
- Risk signals must reference actual product mechanics you spotted, not generic risks
- coverageScore: 0 = not discussed, 1 = partially discussed, 2 = thoroughly covered
- Use these scores to determine which topic areas need more follow-up`;
}
