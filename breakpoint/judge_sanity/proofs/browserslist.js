// browserslist < 4.28.7 (GHSA-73wf-gq98-2v4g): normalizeStats does data[i].versions.length for any key of the
// untrusted stats object, so a key that is also an inherited Object.prototype member ("toString") throws an
// uncaught TypeError. This is a crash, not a write to Object.prototype, so it is judged with the "crash" oracle.
const browserslist = require(TARGET_DIR);

browserslist('last 1 version', {
  path: TARGET_DIR,
  stats: { toString: { onekey: 5 }, chrome: { 100: 50 } },
});
