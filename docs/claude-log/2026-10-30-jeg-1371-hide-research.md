## 2026-10-30 - JEG-1371 hide the Research tab until the first post publishes

Contract: Jeremy picked A on 2026-10-29 (audit decision 2): no Research tab or nav entry while nothing is published;
it comes back on its own once a post exists. No value math.

### Verified (check named)
- `tests/test_build_v2_page.py::test_research_nav_hidden_until_a_post_publishes` fails on main (the built page still
  has `data-key="writing/research"`) and passes with the change, for `/v2/` and the root page. With one published post
  both entries are back and the post link is built.
- `make test-core` result is in the PR description.

### Claimed, not confirmed
- The render tests updated for the shorter menu (`test_v2_nav_render`, `test_v2_hamburger_nav_render`,
  `test_v2_desktop_menu_render`, `test_v2_contract_render` RS-01) were not run here: this container has no Chromium.
  Preview CI runs them on ready-for-review.
- A direct visit to `#writing/research` still shows the empty Research page with no menu entry marked current.
  Nothing on the site links there.
