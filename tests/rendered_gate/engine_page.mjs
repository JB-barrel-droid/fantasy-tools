// JEG-453: the old chart dashboard (the engine page v2 runs hidden) is no
// longer published; dist/classic/ is a redirect to the site root. `make sync`
// still builds the engine page, to build/engine/index.html, and these local
// harness servers serve it at /classic/ so the engine's own controls can be
// driven. Its <base href="../"> resolves assets against the served dist/.
import { fileURLToPath } from "node:url";

export const ENGINE_PAGE = fileURLToPath(new URL("../../build/engine/index.html", import.meta.url));

// The engine page's file for a request path ("/classic/"), else null.
export function enginePageFor(urlPath) {
  return urlPath === "/classic/" || urlPath === "/classic/index.html" ? ENGINE_PAGE : null;
}
