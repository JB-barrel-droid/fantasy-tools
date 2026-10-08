// True when the module at `importMetaUrl` is the script node was started with.
// Building the URL as "file://" + process.argv[1] never matches on Windows
// (C:\ paths need file:///C:/...), which made every harness exit 0 without
// running anything there.
import path from "node:path";
import { pathToFileURL } from "node:url";

export function isMain(importMetaUrl) {
  const entry = process.argv[1];
  return Boolean(entry) && pathToFileURL(path.resolve(entry)).href === importMetaUrl;
}
