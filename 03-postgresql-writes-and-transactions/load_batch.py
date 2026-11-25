import argparse
import sys
from pathlib import Path

import psycopg

from harness.db import Database, ROOT
from harness.runner import submission


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PriceWatch capstone loader.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    load = commands.add_parser("load")
    load.add_argument("batch_id")
    load.add_argument("path", type=Path)
    args = parser.parse_args()
    database = Database("pricewatch")

    try:
        if args.command == "init":
            database.initialize()
            print("INITIALIZED")
        else:
            loader = submission(ROOT / "09-capstone-batch-loader" / "src").load_batch
            with database.connect() as connection:
                applied = loader(connection, args.batch_id, args.path, lambda: None)
            print("APPLIED" if applied else "ALREADY APPLIED")
    except NotImplementedError:
        print("NOT PASSED: implement the capstone scaffold", file=sys.stderr)
        return 1
    except (OSError, psycopg.Error) as error:
        print(f"NOT PASSED: {str(error).splitlines()[0]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
