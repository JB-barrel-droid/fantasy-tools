// True when the module at `importMetaUrl` is the script node was started with.
// Building the URL as "file://" + process.argv[1] never matches on Windows
// (C:\ paths need file:///C:/...), which made every harness exit 0 without
// running anything there.
import { realpathSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

export function isMain(importMetaUrl) {
  const entry = process.argv[1];
  if (!entry) return false;
  // node resolves symlinks in import.meta.url (macOS /var -> /private/var), so
  // compare against the real path of the entry script too.
  let real = path.resolve(entry);
  try { real = realpathSync(real); } catch { /* keep the unresolved path */ }
  return pathToFileURL(real).href === importMetaUrl || pathToFileURL(path.resolve(entry)).href === importMetaUrl;
}
