The four markup encodings correspond to four genuinely different places a
value can live in an HTML document, all of which show up in real scraping
targets:

1. **Plain descriptive markup.** `<div>`/`<span>` with class names that
   describe what they hold (`price`, `stock`, `reviews`, ...). This is what
   most people mean by "a CSS selector" and it is the most fragile -- class
   names are the first thing a redesign renames.
2. **`schema.org` microdata.** `itemprop="..."` attributes, sometimes on
   the visible element itself, sometimes on a separate `<meta>` or `<link>`
   tag that carries a machine-readable value alongside (or instead of) the
   human-visible text. Worth noting: a machine-readable attribute and the
   nearby visible text are not guaranteed to be formatted the same way --
   don't assume you can parse one by copying the format of the other.
3. **JSON-LD.** A `<script type="application/ld+json">` block containing a
   full structured object (often also `schema.org`-shaped, e.g.
   `"@type": "Product"`). Sometimes this is the ONLY place a field exists
   on the page at all -- nothing you grep for in the visible HTML will find
   it, only parsing the script's JSON body will.
4. **An embedded data island.** A `<script id="...">` tag (commonly
   `type="application/json"` or similar) holding a JSON blob that looks
   like it was meant to hydrate client-side JavaScript, but got left in the
   server-rendered response. Same idea as JSON-LD, different convention,
   often a different (non-`schema.org`) key naming scheme.

A regex over the raw HTML text is a legitimate LAST resort when none of the
above works -- fragile in general (don't reach for it first), but useful as
a final fallback that doesn't depend on well-formed markup at all.

For parsing: `parsel`, `lxml`, `beautifulsoup4`, and `selectolax` are all
available in this module's environment -- CSS selectors and/or XPath cover
sources 1 and 2, `json.loads` on a script tag's text content covers 3 and
4. You do not need all four libraries; pick one (or two, if XPath vs. CSS
selectors solve different sub-problems better for you) and be consistent.

Structure your fallback chain per FIELD, not per markup version -- you are
not writing "if version is X, parse this way," you're writing "for the
`price` field, try source A, then B, then C, then D," and running that same
chain unconditionally on every page regardless of which encoding it turns
out to be.
