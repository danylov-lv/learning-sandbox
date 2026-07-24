Concretely, for each required section:

- **Commands.** Not just "run pytest" — the actual invocation, from the
  actual directory, that actually works. Copy it from having run it
  yourself, not from guessing the convention. A command that's subtly
  wrong (wrong directory, wrong flag) is worse than no command at all,
  because a fresh session will trust it and burn a turn on the failure.

- **Conventions.** Read the source, not just the README's bullet list.
  The library enforces at least one convention structurally (a type
  choice for money, a return-value contract for the parser's failure
  path, a normalization rule for one of its inputs) — name the actual
  mechanism, not just the policy.

- **Architecture.** This project is small enough that "architecture" is
  mostly "where does each responsibility live and why is it split that
  way" — not a diagram, a map.

- **What NOT to do.** Each entry should be a mistake that's specifically
  plausible for THIS code (something a reasonable engineer unfamiliar
  with priceparser's specific choices would actually try), paired with
  why it's wrong here. "Don't use floats for money" is generic advice;
  "don't return NaN/None-as-float from parse_price because callers check
  `is None`, not truthiness" is grounded in the actual contract.

- **Memory vs rot.** This is not a section about priceparser. It's a
  section about the CLAUDE.md file itself: which of the facts you just
  wrote above are stable (a function's contract, a directory layout) and
  which categories of fact you deliberately left OUT because they'd go
  stale fast (a current bug count, a specific line number, "we're
  currently migrating X") or shouldn't be there for other reasons
  (credentials, anything that belongs in an env file instead).
