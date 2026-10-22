/* Values auditing (JEG-847): a small registry so each sub-tab can live in its own file.
   audit-pie.js and audit-source.js call DDFAudit.register(slug, fn); v2.js calls DDFAudit.render(slug, root, ctx)
   when the route shows that sub-tab. fn(root, ctx): root is the sub-tab's mount element, ctx = {slug, engine}. */
(function (root) {
  "use strict";
  const SLUGS = ["value-pie", "single-source"];
  const renderers = {};
  root.DDFAudit = {
    slugs: SLUGS,
    register(slug, fn) {
      if (!SLUGS.includes(slug)) throw new Error("DDFAudit: unknown sub-tab " + slug);
      if (typeof fn !== "function") throw new Error("DDFAudit: render hook for " + slug + " must be a function");
      renderers[slug] = fn;
    },
    has: slug => typeof renderers[slug] === "function",
    render(slug, mount, ctx) { if (renderers[slug] && mount) renderers[slug](mount, ctx); },
  };
})(window);
