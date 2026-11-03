/* Offline JSON bridge. All roster decisions stay in the existing JS adapter. */
"use strict";
const fs = require("node:fs");
const {buildSwapBlock} = require("../app/v2/waiver-board-swaps.js");
try {
  const {board, request} = JSON.parse(fs.readFileSync(0, "utf8"));
  process.stdout.write(JSON.stringify(buildSwapBlock(board, request)) + "\n");
} catch (error) {
  process.stderr.write(`waiver_board_swaps: ${error.message}\n`);
  process.exitCode = 2;
}
