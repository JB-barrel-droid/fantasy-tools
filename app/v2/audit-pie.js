/* Values auditing, value-pie sub-tab (stub, JEG-847). Mount: #audit-pie-root. Replace the hook body; keep the registration. */
(function (root) {
  "use strict";
  if (!root.DDFAudit) return;
  root.DDFAudit.register("value-pie", function render(mount, ctx) { /* filled by the value-pie ticket */ });
})(window);
