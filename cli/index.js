import { readFileSync, writeFileSync } from "node:fs";
import { loadEnvFile } from "./env.mjs";

loadEnvFile();

import { getLLMProviderWithFallback } from "@/lib/llm/factory";
import { extractClaims } from "@/lib/services/claimExtractor";
import { runClaimVerification } from "@/lib/services/claimVerifier";
import { startFixture } from "./fixtures/target-app/server.mjs";
import { claims as fixtureClaims } from "./fixtures/target-app/claims.mjs";

const USAGE = `Breakpoint CLI

Usage:
  node cli/index.js extract-claims --blueprint <path> [--provider gemini|openai] [--out <path>]
  node cli/index.js verify-fixture

Options:
  --blueprint <path>   Path to a blueprint JSON file (Blueprint.toJSON() shape). Required.
  --provider <name>    "gemini" or "openai". Defaults to DEFAULT_LLM_PROVIDER or "gemini".
  --out <path>         Write the full claim list as JSON to this path.

verify-fixture boots the local NoteShare fixture app and runs its claim
verifiers against it over HTTP, to prove the verification harness correctly
tells a held claim from a falsified one before any real target is involved.
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

  console.log(USAGE);
  process.exit(command ? 1 : 0);
}

async function runVerifyFixture() {
  console.log("Starting NoteShare fixture...");
  const fixture = await startFixture();
  console.log(`Fixture running at ${fixture.baseUrl}\n`);

  try {
    const { results, heldCount, falsifiedCount, erroredCount } = await runClaimVerification(
      fixtureClaims,
      fixture.baseUrl
    );

    for (const r of results) {
      const badge = { held: "HELD    ", falsified: "FALSIFIED", error: "ERROR   " }[r.status];
      console.log(`[${badge}] (${r.severity}) ${r.statement}`);
      console.log(`           ${r.evidence}\n`);
    }

    console.log(`${heldCount} held, ${falsifiedCount} falsified, ${erroredCount} errored, out of ${results.length} claims.`);
  } finally {
    await fixture.close();
  }
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
