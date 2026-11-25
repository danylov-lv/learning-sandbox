No ready-made code here -- just the concrete shape of the function.

1. Build a prompt string containing, at minimum: a short role/instruction
   line ("classify this product into exactly one of the following
   categories..."), the joined `CATEGORIES` list, the `title`, the
   `description`, and a closing instruction to respond with only a JSON
   object shaped like `{"category": "...", "brand": "..."}`.

2. Optionally add one short clause per category (a one-line definition of
   what belongs in `kitchen` vs. `home-goods` vs. `sporting-goods`, etc.)
   -- this is the single biggest lever if your first pass's macro-F1 is
   low, since several of the 8 categories overlap in a 7B model's default
   sense of the words (a "cookbook" reads as kitchen-adjacent even though
   it's a books item; a "yoga mat" reads as home-goods-adjacent even
   though it's sporting-goods). A one-line gloss per category resolves a
   lot of that ambiguity without hand-holding the model toward any
   specific record.

3. Call `client.generate(prompt, format="json", temperature=0.0)`. Catch
   the case where the response isn't valid JSON (rare with `format="json"`
   against Ollama, but not impossible) -- either extract the first
   `{...}` substring with a regex and re-parse, or fall back to a safe
   default dict.

4. Pull `category` and `brand` out of the parsed dict with `.get(...,
   "")`, normalize `category` (`.strip().lower()`), and return
   `{"category": ..., "brand": ...}`. Don't validate against `CATEGORIES`
   inside this function and raise on a mismatch -- the validator does that
   normalization/rejection itself; your job is just to return the model's
   best answer in the right shape.

5. Run the validator once end to end (it makes one live call per record,
   80 total, so expect it to take roughly a minute or two depending on
   your machine). If category macro-F1 is low but brand accuracy is fine,
   the extraction half of your prompt is working -- go back to step 2 and
   sharpen the category disambiguation instead of rewriting the whole
   prompt.
