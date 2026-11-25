"""s12.t08 (half B) -- docker-secrets-style *_FILE loader.

`service/docker-compose.yml` ships with a PLAINTEXT secret baked into a
service's `environment:` block (`PG_PASSWORD`) -- the antipattern this half
fixes. Two things to do, both required:

  1. Edit `service/docker-compose.yml` IN PLACE (same "fix it, don't
     replace it" shape as task 06): remove the plaintext `PG_PASSWORD`
     value and switch to the docker-secrets `*_FILE` convention
     (`PG_PASSWORD_FILE: /run/secrets/pg_password`), and add a top-level
     `secrets:` block that sources the secret material from an external
     FILE (never an inline value), referenced by the service under its own
     `secrets:` list. See README's "What's required" for the exact
     structural contract the validator checks.
  2. Implement `load_secret()` below so application code reads a secret via
     its `<NAME>_FILE` env var, never a plaintext `<NAME>` env var.

STOCK_PLAINTEXT_MARKER is the exact plaintext value currently baked into
`service/docker-compose.yml`. The validator asserts this string is no
longer present ANYWHERE in that file once you've fixed it (not just renamed
or moved into a comment). Leave this constant as-is -- only remove the
plaintext value from the YAML file itself.
"""

STOCK_PLAINTEXT_MARKER = "kkT9-hardcoded-pw-4821"


def load_secret(name: str) -> str:
    """Load a secret via the docker-secrets `*_FILE` env var convention.

    `name` is a lowercase logical secret name, e.g. "pg_password". Look up
    the environment variable `f"{name.upper()}_FILE"` (e.g.
    "PG_PASSWORD_FILE"), read the file it points to, and return its
    contents with a single trailing newline stripped (if present).

    Must FAIL LOUDLY -- raise a clear, specific exception, never return a
    default or None -- when:
      * the `<NAME>_FILE` environment variable is not set
      * the path it names does not exist / cannot be read

    Never fall back to reading a plaintext `<NAME>` environment variable
    (e.g. `os.environ["PG_PASSWORD"]`) even if one happens to be set. The
    whole point of the file-mount convention is that the plaintext value
    never lives in the environment at all -- a silent fallback would defeat
    it completely.
    """
    raise NotImplementedError
