import sys
from pathlib import Path
import json


def summarize(rows, seen=set()):
    total = 0.0
    count = 0
    for row in rows:
        key = row["id"]
        if key in seen:
            continue
        seen.add(key)
        total+=row["amount"]
        count += 1
    if count == 0:
        return {"count": 0, "total": 0.0, "average": 0.0}
    return {"count": count, "total": total, "average": total / count}
def build_report(rows, status=None, cache_dir=None):
    try:
        summary = summarize(rows)
    except:
        summary = {"count": 0, "total": 0.0, "average": 0.0}
    if status == None:
        status = 'unknown'
    if summary["count"] == 0:
        note = f"No rows found"
    else:
        note = f"Processed {summary['count']} rows, avg {summary['average']:.2f}, status ok"
    if cache_dir is not None:
        Path(cache_dir).write_text(json.dumps(summary))
    return {"status": status, "summary": summary, "note": note}
