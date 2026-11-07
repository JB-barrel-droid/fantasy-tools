// JEG-453: the old chart dashboard (the engine page v2 runs hidden) is no
// longer published; dist/classic/ is a redirect to the site root. `make sync`
// still builds the engine page, to build/engine/index.html, and these local
// harness servers serve it at /classic/ so the engine's own controls can be
// driven. Its <base href="../"> resolves assets against the served dist/.
//
// JEG-1539: v2 shell was moved to build/v2/index.html and served at /v2-app.html
// by _dist_server.py; the same mapping is needed here so gate.mjs can load it.
import { fileURLToPath } from "node:url";

export const ENGINE_PAGE = fileURLToPath(new URL("../../build/engine/index.html", import.meta.url));
// JEG-1539: v2 shell, used by pipelines/value_check.py and the rendered gate.
export const V2_SHELL_PAGE = fileURLToPath(new URL("../../build/v2/index.html", import.meta.url));

// The engine page's file for a request path ("/classic/"), else null.
export function enginePageFor(urlPath) {
  if (urlPath === "/classic/" || urlPath === "/classic/index.html") return ENGINE_PAGE;
  // JEG-1539: v2-app.html serves the v2 shell (built to build/v2/index.html).
  if (urlPath === "/v2-app.html") return V2_SHELL_PAGE;
  return null;
}
