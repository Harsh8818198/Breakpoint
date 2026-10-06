import { readFileSync, existsSync } from "node:fs";

/**
 * Minimal .env loader — sets process.env from a dotenv-style file without
 * adding a dependency. Existing env vars are never overwritten.
 */
export function loadEnvFile(path = ".env.local") {
  if (!existsSync(path)) return;

  const contents = decodeEnvFile(readFileSync(path));
  for (const line of contents.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;

    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    if (!(key in process.env)) process.env[key] = value;
  }
}

/**
 * Decodes a .env file's raw bytes, tolerating the encodings different
 * shells actually produce. Windows PowerShell's `>` / `echo ... > file`
 * (classic "Windows PowerShell", not pwsh 7+) writes UTF-16LE with a BOM
 * by default, not UTF-8 — reading that as UTF-8 silently mangles every
 * key and value. Detect the BOM and decode accordingly; strip a leftover
 * UTF-8 BOM character either way.
 */
function decodeEnvFile(buffer) {
  if (buffer.length >= 2 && buffer[0] === 0xff && buffer[1] === 0xfe) {
    return buffer.slice(2).toString("utf16le");
  }
  if (buffer.length >= 2 && buffer[0] === 0xfe && buffer[1] === 0xff) {
    return buffer.slice(2).swap16().toString("utf16le");
  }
  return buffer.toString("utf8").replace(/^﻿/, "");
}
