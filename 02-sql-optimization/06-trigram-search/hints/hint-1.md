# Hint 1

A B-tree index stores values in sorted order, and can only jump straight to
a range if it knows the *prefix* of what it's looking for — that's why
`LIKE 'titan%'` can use one, but `LIKE '%titanium%'` cannot: there's no
prefix to sort by, the match could start anywhere in the string.

What does Postgres offer for "does this string contain this substring
anywhere," independent of position?
