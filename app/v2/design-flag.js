/* JEG-1137: opt-in preview of the Fieldnotes design layer. Off unless the URL asks for it:
   ?design=fieldnotes sets <html data-design="fieldnotes">, which v2.css scopes every Fieldnotes rule to.
   Loaded synchronously in <head> so the attribute is set before first paint. Nothing is stored. */
(function () {
  try {
    var design = new URLSearchParams(window.location.search).get("design");
    if (design === "fieldnotes") document.documentElement.setAttribute("data-design", "fieldnotes");
  } catch (e) { /* no URLSearchParams: the default design stays */ }
})();
