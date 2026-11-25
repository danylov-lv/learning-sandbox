"""s07.t07 -- create the compacted topic and let you watch compaction happen.

CLI contract:

    uv run python src/setup_topic.py

This is YOUR exploration tool. The validator does not run this script -- it
creates its own copy of the topic with the same shape so grading is
deterministic regardless of what you've done here. Run this, produce some
events at it (see the README), and watch Redpanda Console (localhost:8307)
show the segment count drop as compaction runs.

What makes a topic "compacted" instead of the normal time/size-retention log
you've used in every other task this module: `cleanup.policy=compact`. Instead
of deleting old segments once they age out or the log gets too big, the
broker periodically rewrites each segment keeping only the LAST value written
for each key (the message key, not any field inside the JSON value -- Kafka
compaction only ever looks at the key you pass to `producer.produce(key=...)`).
Everything with an older, superseded key gets thrown away. A key can also be
"deleted" outright by writing a null value for it -- a tombstone -- which
compaction eventually removes as well, though full removal isn't as fast as
you might expect (see `delete.retention.ms` below).
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import create_topic  # noqa: E402

TOPIC = "s07.t07.latest-price"
PARTITIONS = 6


def main() -> None:
    # TODO: create TOPIC as a COMPACTED topic.
    #
    # create_topic(name, partitions=..., cleanup_policy=..., extra_config=...)
    # is given by the harness (harness/common.py) -- read its docstring.
    #
    # You want:
    #   - cleanup_policy="compact"
    #   - extra_config with compaction knobs aggressive enough that you can
    #     actually SEE compaction run during a short exploration session
    #     instead of waiting out Kafka's lazy multi-hour defaults. Look up
    #     what these do and pick sensible values:
    #       - "segment.ms"                 (how often a new segment rolls,
    #                                        so there's more than one segment
    #                                        for the cleaner to compact away)
    #       - "min.cleanable.dirty.ratio"   (how "dirty" -- fraction of bytes
    #                                        that are superseded -- a log has
    #                                        to get before the cleaner will
    #                                        touch it; the default, 0.5, means
    #                                        it waits for half the log to be
    #                                        garbage)
    #
    # print() whether the topic was newly created or already existed, and the
    # partition count, so running this twice is informative, not silent.
    raise NotImplementedError


if __name__ == "__main__":
    main()
