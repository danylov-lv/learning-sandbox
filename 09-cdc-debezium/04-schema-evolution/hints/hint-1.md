An `ADD COLUMN` is one of the least dangerous changes you can make to a
table that's already being replicated -- every existing row still means
exactly what it meant before, and the new column just... starts existing.
Nothing about the old rows becomes ambiguous.

What makes a downstream consumer brittle in the face of that isn't
Postgres, Debezium, or Kafka -- it's how the consumer's own code decides
what fields to expect in a message. Think about the difference between
code that asks a dict "what do you have?" versus code that asserts "you
had better have exactly this."

If your consumer would crash (or silently do the wrong thing) on a message
that has one MORE key than the messages it was written against, that's a
property of your code, not of the change data capture pipeline.
