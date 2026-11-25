String comparison sees characters. It cannot tell you that "Compact" and
"Cpt" mean the same thing, or that reordering four tokens and adding a
comma doesn't change what a title refers to. You need a representation
that captures meaning instead of spelling -- something the module's
embedding model already gives you for free. Once two titles are vectors
instead of strings, "how similar are these" becomes a geometry question,
not a text-parsing question.

Think about what happens once you have a vector per title: how would you
decide which vectors are "close enough" to be the same product, and what
do you do with a group of three or four vectors that all pairwise satisfy
that closeness?
