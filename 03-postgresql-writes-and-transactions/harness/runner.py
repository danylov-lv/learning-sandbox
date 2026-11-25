import argparse
import importlib.util
import sys
from pathlib import Path


def submission(source: Path):
    spec = importlib.util.spec_from_file_location("learner_answer", source / "answer.py")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous
        raise
    return module


def run(check, test_file: str, *, checkpoints: bool = False) -> int:
    parser = argparse.ArgumentParser()
    if checkpoints:
        parser.add_argument("--checkpoint", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    source = Path(test_file).resolve().parents[1] / "src"
    try:
        if checkpoints:
            check(source, args.checkpoint)
        else:
            check(source)
    except NotImplementedError:
        print("NOT PASSED: implement the task scaffold", file=sys.stderr)
        return 1
    except Exception as error:
        detail = str(error).strip().splitlines()
        message = detail[0] if detail else "check failed"
        print(f"NOT PASSED: {type(error).__name__}: {message}", file=sys.stderr)
        return 1
    print("PASSED")
    return 0
