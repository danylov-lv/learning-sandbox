Before writing a single line of `src/recon.py`, spend some time just
poking the target with `curl` (or `httpx` in a REPL) and reading what comes
back.

Start with the plainest possible request to `http://localhost:8313/` (no
special headers at all, whatever your HTTP tool sends by default). Look
closely at the response -- status code, body. Now try `/robots.txt` the
same bare way. Robots files exist so well-behaved crawlers know what NOT to
touch; read it before you write any crawling logic, and take its
`Disallow` lines literally.

Next, add headers one at a time until something changes. What's the
minimum a request needs before the target stops rejecting it? Don't guess
-- try a request with no `User-Agent` at all, then one with a `User-Agent`
that doesn't look like a browser, then one that does. Same for
`Accept-Language`. The response body tells you exactly why a request was
rejected; read it instead of just checking the status code.

Once you can fetch `/catalog?page=1` successfully, don't just glance at it
in a browser -- view the raw HTML text. A page rendered by a browser hides
things a browser is told to hide (`display:none`, etc.); the raw source
does not. Look for links that don't belong in a normal listing -- extra
`<a>` tags, ones with attributes a real product link wouldn't have. Note
where they point.

Finally, before building any real crawling loop, send a handful of
requests to the same endpoint back-to-back and watch what happens as you
speed that up. At some point something changes about the response. That's
the shape of the thing you'll need to design around -- but don't go past a
handful of requests while just exploring; you can burn through your
politeness budget by accident before you've even started building.
