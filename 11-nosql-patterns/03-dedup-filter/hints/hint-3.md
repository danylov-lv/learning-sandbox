`MEMORY USAGE <key>` tells you, in bytes, roughly what a key costs Redis to
hold right now. Run it yourself, by hand, against both keys after loading the
same urls into each -- before you trust the validator's numbers, look at them
yourself and ask whether the gap is what you expected. A SET's number should
scale with how many distinct urls you fed it (more urls, bigger number,
basically linearly). The Bloom key's number should stay roughly flat
regardless of how many urls you feed it, as long as you stay near the
`capacity` you reserved -- that flatness IS the point.

For the false-positive rate: feed the whole url stream through your
`BloomDedup` and count how many calls returned "new". Compare that count to
the TRUE number of distinct urls (ground truth's `unique_urls`). The
difference is your false positives -- urls the filter wrongly called
"already seen". Does that difference, as a fraction of the true unique
count, land somewhere near the `error_rate` you reserved with? If it's wildly
higher, look at whether `capacity` was set too low for how many items you
actually added -- exceeding a Bloom filter's reserved capacity is exactly
what degrades its false-positive rate beyond what you configured.

Once you've seen both numbers with your own eyes -- the memory gap and the
false-positive rate -- ask yourself the tradeoff question directly: at what
point (how many distinct urls, how tolerant your use case is of occasionally
skipping one) does giving up exactness actually pay for itself? A crawler
skipping one page in a hundred, in exchange for a filter thousands of times
smaller than the equivalent SET, is a very different call than a system where
"never lose an item" is a hard requirement.
