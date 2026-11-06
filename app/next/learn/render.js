/* Tiny dependency-free markdown renderer for Learn posts.
   Supports: frontmatter, headings, paragraphs, nested lists, links, images,
   bold/italic, inline code, fenced code, blockquotes, horizontal rules, tables.
   It never rewrites words: output text is the source text minus markdown syntax. */
(function (global) {
  'use strict';

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function safeUrl(url) {
    var u = url.trim();
    if (/^(javascript|data|vbscript):/i.test(u)) return '#';
    return escapeHtml(u);
  }

  function parseFrontmatter(text) {
    var src = text.replace(/\r\n?/g, '\n');
    var meta = {};
    var m = /^---\n([\s\S]*?)\n---\n?/.exec(src);
    if (!m) return { meta: meta, body: src };
    m[1].split('\n').forEach(function (line) {
      var i = line.indexOf(':');
      if (i < 1) return;
      var key = line.slice(0, i).trim();
      var val = line.slice(i + 1).trim().replace(/^["']|["']$/g, '');
      meta[key] = val;
    });
    return { meta: meta, body: src.slice(m[0].length) };
  }

  /* Inline: code spans are pulled out first so their contents stay literal. */
  function inline(text) {
    var codes = [];
    var s = text.replace(/`([^`]+)`/g, function (_, c) {
      codes.push('<code>' + escapeHtml(c) + '</code>');
      return '\u0000' + (codes.length - 1) + '\u0000';
    });
    s = escapeHtml(s);
    s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)/g, function (_, alt, src, title) {
      return '<img src="' + safeUrl(src) + '" alt="' + alt + '"' + (title ? ' title="' + title + '"' : '') + ' loading="lazy">';
    });
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)/g, function (_, label, href, title) {
      var external = /^https?:/i.test(href);
      return '<a href="' + safeUrl(href) + '"' + (title ? ' title="' + title + '"' : '') +
        (external ? ' rel="noopener"' : '') + '>' + label + '</a>';
    });
    s = s.replace(/(\*\*|__)(?=\S)([\s\S]*?\S)\1/g, '<strong>$2</strong>');
    s = s.replace(/(^|[^*\w])\*(?=\S)([^*]*?\S)\*(?!\*)/g, '$1<em>$2</em>');
    s = s.replace(/(^|[^_\w])_(?=\S)([^_]*?\S)_(?![_\w])/g, '$1<em>$2</em>');
    s = s.replace(/\u0000(\d+)\u0000/g, function (_, i) { return codes[+i]; });
    return s;
  }

  var LIST_RE = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;

  function renderList(lines, start) {
    /* Returns { html, next } for the list block beginning at lines[start]. */
    var first = LIST_RE.exec(lines[start]);
    var baseIndent = first[1].length;
    var ordered = /\d/.test(first[2]);
    var startNum = ordered ? parseInt(first[2], 10) : 1;
    var items = [];
    var i = start;
    while (i < lines.length) {
      var line = lines[i];
      if (!line.trim()) {
        var peek = lines[i + 1];
        var pm = peek && LIST_RE.exec(peek);
        if (pm && pm[1].length >= baseIndent) { i++; continue; }
        break;
      }
      var m = LIST_RE.exec(line);
      if (m && m[1].length === baseIndent) {
        items.push({ text: m[3], children: '' });
        i++;
      } else if (m && m[1].length > baseIndent && items.length) {
        var sub = renderList(lines, i);
        items[items.length - 1].children += sub.html;
        i = sub.next;
      } else if (!m && /^\s+\S/.test(line) && items.length) {
        items[items.length - 1].text += ' ' + line.trim();
        i++;
      } else {
        break;
      }
    }
    var tag = ordered ? 'ol' : 'ul';
    var html = '<' + tag + (ordered && startNum !== 1 ? ' start="' + startNum + '"' : '') + '>' +
      items.map(function (it) { return '<li>' + inline(it.text) + it.children + '</li>'; }).join('') +
      '</' + tag + '>';
    return { html: html, next: i };
  }

  function splitRow(line) {
    return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(function (c) { return c.trim(); });
  }

  function slugify(text) {
    return text.toLowerCase().replace(/<[^>]+>/g, '').replace(/&[a-z]+;/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  }

  function renderMarkdown(body) {
    var lines = body.replace(/\r\n?/g, '\n').split('\n');
    var out = [];
    var i = 0;
    var used = {};
    while (i < lines.length) {
      var line = lines[i];
      if (!line.trim()) { i++; continue; }

      var fence = /^```(\w*)\s*$/.exec(line);
      if (fence) {
        var code = [];
        i++;
        while (i < lines.length && !/^```\s*$/.test(lines[i])) { code.push(lines[i]); i++; }
        i++;
        out.push('<pre><code' + (fence[1] ? ' class="lang-' + fence[1] + '"' : '') + '>' + escapeHtml(code.join('\n')) + '</code></pre>');
        continue;
      }

      var h = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
      if (h) {
        var level = h[1].length;
        var content = inline(h[2]);
        var id = slugify(content) || 'section';
        while (used[id]) id += '-x';
        used[id] = true;
        out.push('<h' + level + ' id="' + id + '">' + content + '</h' + level + '>');
        i++;
        continue;
      }

      if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { out.push('<hr>'); i++; continue; }

      if (/^\s*>/.test(line)) {
        var quote = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) { quote.push(lines[i].replace(/^\s*>\s?/, '')); i++; }
        out.push('<blockquote>' + renderMarkdown(quote.join('\n')) + '</blockquote>');
        continue;
      }

      if (LIST_RE.test(line)) {
        var list = renderList(lines, i);
        out.push(list.html);
        i = list.next;
        continue;
      }

      if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(lines[i + 1])) {
        var head = splitRow(line);
        var aligns = splitRow(lines[i + 1]).map(function (c) {
          return /^:-+:$/.test(c) ? 'center' : /-+:$/.test(c) ? 'right' : '';
        });
        i += 2;
        var rows = [];
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(splitRow(lines[i])); i++; }
        var cell = function (tag, c, k) {
          return '<' + tag + (aligns[k] ? ' style="text-align:' + aligns[k] + '"' : '') + '>' + inline(c) + '</' + tag + '>';
        };
        out.push('<div class="post-table"><table><thead><tr>' + head.map(function (c, k) { return cell('th', c, k); }).join('') +
          '</tr></thead><tbody>' + rows.map(function (r) {
            return '<tr>' + r.map(function (c, k) { return cell('td', c, k); }).join('') + '</tr>';
          }).join('') + '</tbody></table></div>');
        continue;
      }

      var para = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|\s*>)/.test(lines[i]) && !LIST_RE.test(lines[i]) &&
             !/^\s*([-*_])(\s*\1){2,}\s*$/.test(lines[i])) {
        para.push(lines[i].trim());
        i++;
      }
      var p = inline(para.join(' '));
      out.push(/^<img [^>]+>$/.test(p) ? '<figure>' + p + '</figure>' : '<p>' + p + '</p>');
    }
    return out.join('\n');
  }

  function wordCount(text) {
    var words = text.trim().split(/\s+/).filter(function (w) { return /[A-Za-z0-9]/.test(w); });
    return words.length;
  }

  // A post marked "draft": true in posts.json shows this tag beside its title.
  function draftTag(post) {
    return post && post.draft ? ' <span class="draft-tag">Draft</span>' : '';
  }

  global.DDFLearn = { parseFrontmatter: parseFrontmatter, renderMarkdown: renderMarkdown, wordCount: wordCount, draftTag: draftTag };
})(window);
