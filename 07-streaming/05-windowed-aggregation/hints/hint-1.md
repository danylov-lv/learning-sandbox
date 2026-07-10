Start by asking: which field in the event payload actually tells you when
the price observation happened? It's not the Kafka offset, it's not
"now" when your consumer reads the message — it's a field already sitting
in the JSON. Everything else in this task is arithmetic on that one field.

For the arithmetic: you have a timestamp, an anchor (the start of the whole
corpus), and a fixed window size. You need "how many whole windows have
elapsed since the anchor, rounded down." What operation do you already know
that turns "how many whole units fit" into an integer, discarding the
remainder? Apply it to a duration instead of a plain number.

For the upsert: think about what happens if two different events for the
same `(window_start, category)` both try to write at roughly the same
time (they will — the whole corpus streams through fast). What SQL
statement lets the database itself resolve "insert if new, otherwise
add to what's there" atomically, instead of you reading a row, adding in
Python, and writing it back?
