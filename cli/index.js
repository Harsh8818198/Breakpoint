import { readFileSync, writeFileSync } from "node:fs";
import { loadEnvFile } from "./env.mjs";

loadEnvFile();

import { getLLMProviderWithFallback } from "@/lib/llm/factory";
import { extractClaims } from "@/lib/services/claimExtractor";

const USAGE = `Breakpoint CLI

Usage:
  node cli/index.js extract-claims --blueprint <path> [--provider gemini|openai] [--out <path>]

Options:
  --blueprint <path>   Path to a blueprint JSON file (Blueprint.toJSON() shape). Required.
  --provider <name>    "gemini" or "openai". Defaults to DEFAULT_LLM_PROVIDER or "gemini".
  --out <path>         Write the full claim list as JSON to this path.
`;

async function main() {
  const [command, ...rest] = process.argv.slice(2);
  const args = parseArgs(rest);

  if (command === "extract-claims") {
    await runExtractClaims(args);
    return;
  }

  console.log(USAGE);
  process.exit(command ? 1 : 0);
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
