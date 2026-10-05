import { getAttackSystemPrompt } from "@/lib/prompts/agents/attackLoop";

/**
 * Runs the ReAct-style attack loop for one claim against one live target.
 * The agent only ever sees HTTP responses — same interface an attacker
 * would have. It proposes a proofRequest when it concludes falsified, but
 * does not get to decide the final verdict itself; the caller re-runs that
 * exact request independently (claimVerifier.replayAndCheck) before trusting it.
 *
 * @returns {Promise<{concluded: boolean, claimedFalsified: boolean, proofRequest: Object|null, reasoning: string, turns: number, transcript: Array}>}
 */
export async function runAttackLoop(llm, claim, apiSurface, baseUrl, { maxTurns = 6 } = {}) {
  const messages = [{ role: "user", content: getAttackSystemPrompt(claim, apiSurface, maxTurns) }];
  const transcript = [];

  for (let turn = 0; turn < maxTurns; turn++) {
    const { data: action } = await llm.chatJSON(messages);
    messages.push({ role: "assistant", content: JSON.stringify(action) });

    if (action?.action === "conclude") {
      transcript.push({ turn, action });
      return {
        concluded: true,
        claimedFalsified: Boolean(action.falsified),
        proofRequest: action.falsified ? action.proofRequest || null : null,
        reasoning: action.reasoning || "",
        turns: turn + 1,
        transcript,
      };
    }

    if (action?.action === "request" && action.method === "GET" && action.path) {
      const { status, body } = await sendRequest(baseUrl, action);
      transcript.push({ turn, action, observed: { status, body } });
      messages.push({
        role: "user",
        content: `Response: status=${status} body=${JSON.stringify(body)}\n\nWhat's your next action?`,
      });
      continue;
    }

    transcript.push({ turn, action, observed: null });
    messages.push({
      role: "user",
      content: "That action wasn't understood or isn't allowed. Only GET requests to the listed endpoints, or a conclude action. Try again.",
    });
  }

  return {
    concluded: false,
    claimedFalsified: false,
    proofRequest: null,
    reasoning: "Ran out of turns without concluding.",
    turns: maxTurns,
    transcript,
  };
}

/**
 * Fires one GET request at a target and returns its parsed response.
 * Shared by the live attack loop and the independent replay step, so both
 * paths exercise the target the same way.
 */
export async function sendRequest(baseUrl, { path, query }) {
  const url = new URL(path, baseUrl);
  for (const [key, value] of Object.entries(query || {})) {
    url.searchParams.set(key, value);
  }

  const res = await fetch(url);
  let body = null;
  try {
    body = await res.json();
  } catch {
    // non-JSON response — leave body null
  }
  return { status: res.status, body };
}
