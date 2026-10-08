# 2026-10-08 · v2 page weight (JEG-449)

## Verified

- Before / after on a local build, headless Chromium, CPU 4×: decoded bytes 8.8 MB → 4.1 MB; time to
  usable at 390 px 7.0–10.7 s → 2.8 s, at 1440 px 2.5 s. `comparison-sources-data.json` downloads
  3 → 1. Gzip as served: index.html 1014 KB → 129 KB, comparison file 2304 KB → 261 KB.
- Engine output identical with the container hidden: rows (every series), source info, zones,
  weights, selection and all diagnostics fields at Full PPR 12, Half 10, Standard 14, Full 8.
- New `tests/test_v2_weight_render.py` OK; guards caught: no fetch sharing, classic fonts back,
  engine laid out.
- All eleven earlier v2 render suites, `test_launch_front_door`, `test_live_page_synthetic`,
  `test_main_table_engine_parity`, `test_disagreement_units_render`, `test_page_load_no_404`,
  `test_missing_section_render`: OK.

## Claimed, not confirmed

- Real-phone timing over 4G was not measured; the 4× CPU figure has no network latency.
