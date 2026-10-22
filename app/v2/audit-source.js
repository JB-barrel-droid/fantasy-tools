/* Values auditing, single-source sub-tab (stub, JEG-847). Mount: #audit-source-root. Replace the hook body; keep the registration. */
(function (root) {
  "use strict";
  if (!root.DDFAudit) return;
  root.DDFAudit.register("single-source", function render(mount, ctx) { /* filled by the single-source ticket */ });
})(window);
