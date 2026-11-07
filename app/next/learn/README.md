# Learn: writing

`learn.html` is the home for Jeremy's own writing: the manifesto and future posts.
Every post is a markdown file shown verbatim; the page adds only UI labels
(dates, reading time, Copy link, Previous/Next).

## Add a post

1. Drop a markdown file in `learn/posts/<slug>.md`, starting with frontmatter:

   ```
   ---
   title: How much is a bench player worth?
   date: 2026-11-12
   slug: bench-player-value
   summary: Optional one or two sentences, only if the author wrote one.
   kind: post
   ---
   ```

   `kind` is `manifesto`, `methodology` or `post`. Paste the text below the
   frontmatter unchanged. If the text starts with a `# Heading`, that heading is
   the page title; otherwise `title` is used.

2. Add an entry to `learn/posts.json`:

   ```json
   { "slug": "bench-player-value", "title": "How much is a bench player worth?",
     "date": "2026-11-12", "kind": "post", "file": "posts/bench-player-value.md" }
   ```

   Add `"pinned": true` to show it as a featured card at the top (the manifesto
   is pinned). Pinned posts keep their order in the file; the rest are sorted
   newest first automatically. `summary` here overrides the frontmatter one; with
   neither, the card shows the post's first paragraph.
   Add `"draft": true` to show a "Draft" tag beside the title in the list, the
   post header and the pager. A listed draft is public; keep unpublished text out
   of `posts.json` (the methodology draft waits in `docs/learn-drafts/` for
   Jeremy's rewrite, decision D6, 2026-11-06).
   Learn's list is the only index; there is no feed.

3. Open `learn.html#/<slug>` to read it. Links are deep-linkable and the index
   is `learn.html` (or `learn.html#/`).

The page fetches the files, so serve the folder over HTTP (for example
`python3 -m http.server 8800` in `03-built-site`); `file://` will not load posts.

## Markdown supported (`learn/render.js`)

Headings, paragraphs, bold/italic, links, images (`![alt](src)`; put image files
in `learn/posts/img/` and reference them as `learn/posts/img/name.png`), inline
code and fenced code blocks, blockquotes, ordered/unordered and nested lists,
horizontal rules, and pipe tables. Raw HTML is escaped, not rendered.

## Sources of the current posts

- `posts/manifesto.md`: verbatim from the fantasy-tools repo's
  `docs/manifesto-mirror.md` (mirror of Jeremy's manifesto Google Doc,
  mirrored 2026-10-10), which is the text rendered at
  https://datadrivenfootball.github.io/fantasy-tools/#writing/manifesto
  (checked word for word on 2026-11-05). Date 2026-10-07 is the date the
  manifesto was stated (`docs/manifesto.md`).

## How we get our numbers (`learn/numbers/`)

The Value pie, Health check, Source build-up and Trace tabs read the live engine that
runs hidden on `learn.html` (`ddf-engine.js` over `TradeValueCurveControls`), at the
reader's league settings or the ones checked in the settings bar. `learn-engine.js`
reads the engine (getInspection, getAllRows, getPublishedMath) and reuses the old
audit tabs' models (`v2/audit-pie.js` AuditPie, `v2/audit-source.js` DDFAuditSource);
`numbers.js` renders. Nothing here computes a value, and there are no snapshot files
(decision D8, 2026-11-06). Routes take `?scoring=&teams=&roster=QB1.RB2.WR2.TE1.FLEX1.SF0.BN7`.
The Full value logic tab frames `value-logic/` (built by `make sync`).
