'use strict';
// Runs one proof against one library checkout and prints what happened as a single JSON line.
// It decides nothing about "worked": node_judge.py combines a real run and a control run.
// Config arrives in BP_JUDGE_CONFIG: {repo, proof, oracle: "pollution"|"crash", mode: "real"|"control", settleMs}.
const cfg = JSON.parse(process.env.BP_JUDGE_CONFIG);
const path = require('path');
const Module = require('module');
const net = require('net');
const dns = require('dns');

// Soft network block. Node's permission flag does not cover the network, so refuse connections here.
// This stops accidents, not a determined attacker: run unfamiliar proofs inside WSL or Docker.
const refuse = () => { throw new Error('network access is blocked by the judge'); };
net.Socket.prototype.connect = refuse;
for (const fn of ['lookup', 'resolve', 'resolve4', 'resolve6']) dns[fn] = refuse;
if (dns.promises) for (const fn of ['lookup', 'resolve', 'resolve4', 'resolve6']) dns.promises[fn] = refuse;
globalThis.fetch = () => Promise.reject(new Error('network access is blocked by the judge'));

const repo = path.resolve(cfg.repo);
const norm = (p) => path.resolve(p).toLowerCase();
const repoNorm = norm(repo);
const inTarget = (file) => {
  const f = norm(file);
  return f.startsWith(repoNorm + path.sep) && !f.slice(repoNorm.length).includes(path.sep + 'node_modules' + path.sep);
};

const namesBefore = new Set(Reflect.ownKeys(Object.prototype).map(String));
let targetLoaded = false;
const errors = [];
const record = (e) => errors.push({
  name: e && e.name, code: e && e.code, message: String(e && e.message).slice(0, 300),
  stack: String(e && e.stack).slice(0, 4000),
});
process.on('uncaughtException', record);
process.on('unhandledRejection', (e) => record(e instanceof Error ? e : new Error(String(e))));

const stub = () => {
  const target = function () {};
  return new Proxy(target, {
    get: (_, prop) => (prop === 'then' ? undefined : prop === Symbol.toPrimitive ? () => '' : stub()),
    apply: () => stub(),
    construct: () => stub(),
    has: () => true,
  });
};

const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  let file = null;
  try { file = Module._resolveFilename(request, parent, isMain); } catch (_) { /* let the real loader report it */ }
  if (file && path.isAbsolute(file) && inTarget(file)) {
    targetLoaded = true;
    if (cfg.mode === 'control') return stub();
  }
  return originalLoad.apply(this, arguments);
};

globalThis.TARGET_DIR = repo;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  try {
    let out = require(path.resolve(cfg.proof));
    if (typeof out === 'function') out = await out(repo);
    else if (out && typeof out.then === 'function') await out;
  } catch (e) {
    record(e);
  }
  await sleep(cfg.settleMs || 300);

  const newKeys = Reflect.ownKeys(Object.prototype).map(String).filter((k) => !namesBefore.has(k));
  // The judge's own sandbox refusals are not bugs in the library.
  const crashes = errors.filter((e) => e.code !== 'ERR_ACCESS_DENIED').filter((e) => {
    const frames = String(e.stack).split('\n').filter((l) => l.includes(path.sep) || l.includes('/'));
    return frames.some((l) => {
      const m = l.match(/\(?([A-Za-z]:[\\/][^:)]*|\/[^:)]*)/);
      return m && inTarget(m[1].replace(/^file:\/\//, ''));
    });
  });
  process.stdout.write('\n@@JUDGE@@ ' + JSON.stringify({
    mode: cfg.mode,
    targetLoaded,
    newKeys: newKeys.slice(0, 20),
    errors: errors.slice(0, 5),
    crashFromTarget: crashes.length > 0,
  }) + '\n');
  process.exit(0);
})();
