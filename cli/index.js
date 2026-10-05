import { readFileSync, writeFileSync } from "node:fs";
import { loadEnvFile } from "./env.mjs";

loadEnvFile();

import { getLLMProviderWithFallback } from "@/lib/llm/factory";
import { extractClaims } from "@/lib/services/claimExtractor";
import { runGoldenRegression, runAgentClaimVerification } from "@/lib/services/claimVerifier";
import { startFixture } from "./fixtures/target-app/server.mjs";
import { claims as fixtureClaims, apiSurface } from "./fixtures/target-app/claims.mjs";

const USAGE = `Breakpoint CLI

Usage:
  node cli/index.js extract-claims --blueprint <path> [--provider gemini|openai] [--out <path>]
  node cli/index.js verify-fixture
  node cli/index.js attack-fixture [--provider gemini|openai] [--max-turns <n>]

Options:
  --blueprint <path>   Path to a blueprint JSON file (Blueprint.toJSON() shape). Required.
  --provider <name>    "gemini" or "openai". Defaults to DEFAULT_LLM_PROVIDER or "gemini".
  --out <path>         Write the full claim list as JSON to this path.
  --max-turns <n>      Turn budget per claim for attack-fixture. Defaults to 6.

verify-fixture replays each claim's known exploit attempt against the
NoteShare fixture — a fast, free, no-LLM regression check that the
predicates themselves are correct.

attack-fixture has an LLM agent explore the fixture over HTTP, with no hint
about which endpoint is flawed, and try to falsify each claim itself. Any
claimed exploit is independently replayed on a fresh instance before it
counts — the agent's own transcript is never trusted as proof.
`;

async function main() {
  const [command, ...rest] = process.argv.slice(2);
  const args = parseArgs(rest);

  if (command === "extract-claims") {
    await runExtractClaims(args);
    return;
  }

  if (command === "verify-fixture") {
    await runVerifyFixture();
    return;
  }

  if (command === "attack-fixture") {
    await runAttackFixture(args);
    return;
  }

  console.log(USAGE);
  process.exit(command ? 1 : 0);
}

async function runVerifyFixture() {
  console.log("Starting NoteShare fixture...");
  const fixture = await startFixture();
  console.log(`Fixture running at ${fixture.baseUrl}\n`);

  try {
    const summary = await runGoldenRegression(fixtureClaims, fixture.baseUrl);
    printResults(summary);
  } finally {
    await fixture.close();
  }
}

async function runAttackFixture({ provider, "max-turns": maxTurnsArg }) {
  const resolvedProvider = provider || process.env.DEFAULT_LLM_PROVIDER || "gemini";
  const llm = getLLMProviderWithFallback(resolvedProvider, null);
  const maxTurns = maxTurnsArg ? Number(maxTurnsArg) : 6;

  console.log(`Attacking the NoteShare fixture via ${resolvedProvider}, ${fixtureClaims.length} claims, up to ${maxTurns} turns each...\n`);

  const summary = await runAgentClaimVerification(llm, fixtureClaims, apiSurface, startFixture, { maxTurns });
  printResults(summary);
}

function printResults({ results, heldCount, falsifiedCount, inconclusiveCount, unverifiedCount }) {
  const badges = {
    held: "HELD              ",
    falsified: "FALSIFIED         ",
    inconclusive: "INCONCLUSIVE      ",
    agent_claim_unverified: "AGENT_UNVERIFIED  ",
  };

  for (const r of results) {
    console.log(`[${badges[r.status]}] (${r.severity}) ${r.statement}`);
    if (r.proofRequest) {
      console.log(`           proof: ${r.proofRequest.method} ${r.proofRequest.path}${r.proofRequest.query ? " " + JSON.stringify(r.proofRequest.query) : ""}`);
    }
    if (r.turns) console.log(`           turns: ${r.turns}`);
    console.log(`           ${r.note}\n`);
  }

  console.log(
    `${heldCount} held, ${falsifiedCount} falsified` +
      (inconclusiveCount ? `, ${inconclusiveCount} inconclusive` : "") +
      (unverifiedCount ? `, ${unverifiedCount} agent-claimed-but-unverified` : "") +
      `, out of ${results.length} claims.`
  );
}

async function runExtractClaims({ blueprint: blueprintPath, provider, out }) {
  if (!blueprintPath) {
    console.error("Missing --blueprint <path>\n");
    console.log(USAGE);
    process.exit(1);
  }

  const blueprint = JSON.parse(readFileSync(blueprintPath, "utf8"));
  const resolvedProvider = provider || process.env.DEFAULT_LLM_PROVIDER || "gemini";
  const llm = getLLMProviderWithFallback(resolvedProvider, null);

  console.log(`Extracting claims from ${blueprintPath} via ${resolvedProvider}...`);
  const claims = await extractClaims(llm, blueprint);

  const byCategory = {};
  for (const claim of claims) {
    byCategory[claim.category] = (byCategory[claim.category] || 0) + 1;
  }

  console.log(`\n${claims.length} claims extracted:`);
  for (const [category, count] of Object.entries(byCategory)) {
    console.log(`  ${category.padEnd(16)} ${count}`);
  }

  console.log("");
  for (const claim of claims) {
    const badge = claim.formalizable ? "[formal]" : "[nl]    ";
    console.log(`${badge} (${claim.severityIfFalse}) ${claim.statement}`);
  }

  if (out) {
    writeFileSync(out, JSON.stringify(claims, null, 2));
    console.log(`\nWrote ${claims.length} claims to ${out}`);
  }
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (token.startsWith("--")) {
      const key = token.slice(2);
      const value = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : true;
      args[key] = value;
    }
  }
  return args;
}

main().catch((error) => {
  console.error("Error:", error.message);
  process.exit(1);
});
