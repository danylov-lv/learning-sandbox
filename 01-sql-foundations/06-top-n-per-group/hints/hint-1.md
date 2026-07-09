The bug report is a giveaway: whatever ranking function was used originally
assigns the *same* rank to tied rows and then skips or continues past it,
which is exactly why "top 3" became "top 5." You need a ranking function
whose output is always a strict, gapless sequence of integers per group,
regardless of ties in the value being ranked — which means ties have to be
broken by something else entirely.
