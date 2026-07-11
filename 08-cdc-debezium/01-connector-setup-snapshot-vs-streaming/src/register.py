"""s08.t01 -- register the Debezium Postgres connector for this task.

CLI contract (what the validator relies on):

    uv run python src/register.py

Behavior contract:
- Reads no arguments, no stdin.
- Builds a connector definition via build_config() (the one thing you
  write) and registers it against Kafka Connect's REST API.
- Waits for the connector to reach RUNNING (connector + its one task),
  then prints a confirmation and exits 0.
- On any failure (Connect unreachable, connector misconfigured, task
  FAILED, timeout waiting for RUNNING), the given plumbing below already
  calls harness.common.not_passed(...) and exits nonzero -- you don't need
  to add your own error handling around registration.
- Idempotent: registering the same name twice (e.g. rerunning this script)
  just updates the existing connector's config.

build_config() must return a dict shaped like:

    {"name": "s08-t01", "config": {...}}

ready to hand to harness.common.register_connector(). The "config" dict is
what actually gets PUT to Kafka Connect. It needs to specify, at minimum:

- connector.class -- which Kafka Connect plugin runs this connector
  (io.debezium.connector.postgresql.PostgresConnector).
- plugin.name -- which Postgres logical-decoding output plugin Debezium
  should ask for (pgoutput -- built into Postgres 10+, no extension
  needed).
- database.hostname / database.port / database.user / database.password /
  database.dbname -- how Debezium reaches the source. Note the connector
  runs INSIDE the Compose network, so the hostname is the service name
  ("source"), not localhost. Port/user/password/db are documented in the
  module README (port 5432 in-network, user/password "sandbox", db
  "shop").
- topic.prefix -- the namespace Debezium publishes change-event topics
  under. For this task: "s08.t01" (topics come out as
  s08.t01.shop.offers, s08.t01.shop.products).
- slot.name -- the Postgres replication slot this connector owns. For this
  task: "s08_t01_slot".
- publication.name -- the Postgres publication scoping which tables get
  replicated. For this task: "s08_t01_pub".
- publication.autocreate.mode -- set it so the publication is created
  automatically, scoped to just the tables you list below (not every table
  in the database).
- table.include.list -- which tables to capture: both shop.offers and
  shop.products, as a comma-separated "schema.table" string.
- snapshot.mode -- what to do on first start. You want the phase this task
  is about: read every existing row once (as op="r" events), then switch
  to live streaming.

Every config value that Kafka Connect's REST API expects is a JSON string
(even where a value looks numeric, e.g. a port) -- build the dict
accordingly.

Try it by hand before trusting the validator:

    uv run python src/register.py
    # then check http://localhost:8383/connectors/s08-t01/status
    # or browse http://localhost:8308 (Redpanda Console) for the new topics
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import register_connector, wait_for_connector_running  # noqa: E402

CONNECTOR_NAME = "s08-t01"


def build_config() -> dict:
    """The one thing you write for this task: return the connector
    definition dict described in the module docstring above, for
    CONNECTOR_NAME. See the README for the full list of required config
    keys and this task's fixed naming (slot/publication/topic-prefix)."""
    raise NotImplementedError


def main() -> None:
    connector_def = build_config()
    register_connector(connector_def)
    status = wait_for_connector_running(CONNECTOR_NAME)
    print(f"connector {CONNECTOR_NAME} is RUNNING: {status.get('connector', {}).get('state')}")


if __name__ == "__main__":
    main()
