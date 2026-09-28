const root = new URL("../", import.meta.url);
const HAS_EXTENSION = /\.[a-zA-Z0-9]+$/;

export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith("@/")) {
    const relative = specifier.slice(2);
    const withExt = HAS_EXTENSION.test(relative) ? relative : `${relative}.js`;
    const target = new URL("src/" + withExt, root);
    return nextResolve(target.href, context);
  }
  return nextResolve(specifier, context);
}
