// Full git SHA of this function's source, so a client can tell which code is live
// from initialize.serverInfo.build. index.ts uses DDF_BUILD_SHA when a deploy sets
// it (the SHA that was actually uploaded) and otherwise this stamp.
//
// The stamp is the commit that introduced the behaviour. A one-line update of this
// constant lands in the following commit, so the value matches `git rev-parse HEAD`
// of the commit a reader should inspect, not necessarily the tip if a later commit
// only rewrote this line.
export const MCP_BUILD_SHA = "4a8127db55944edb4da98c97bd9d064a6475c14e";
