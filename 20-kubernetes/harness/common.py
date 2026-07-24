"""Shared pass/fail plumbing plus kubectl/cluster helpers for module 20 validators.

Convention (matches the rest of the repo): a validator prints exactly one
line and exits. On success: `PASSED` (optionally with a trailing detail
line). On failure: `NOT PASSED: <reason>` and exit 1. No raw tracebacks.

Every helper here pins `--context kind-sandbox20` so a validator can never
accidentally touch some other cluster on the learner's machine. Every
validator must call `require_cluster()` first.
"""

from __future__ import annotations

import contextlib
import difflib
import functools
import json
import os
import re
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Callable, NoReturn, TypeVar

import requests

F = TypeVar("F", bound=Callable[..., None])

CLUSTER_NAME = "sandbox20"
CONTEXT = f"kind-{CLUSTER_NAME}"


# --------------------------------------------------------------------------
# Pass / fail plumbing
# --------------------------------------------------------------------------

def not_passed(reason: str) -> NoReturn:
    print(f"NOT PASSED: {reason}")
    sys.exit(1)


def passed(msg: str = "") -> None:
    print(f"PASSED{': ' + msg if msg else ''}")


def _last_line(text: str) -> str:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line:
            return line
    return "(no error message)"


def guarded(fn: F) -> Callable[..., None]:
    """Wrap a validator's entry point so any uncaught exception becomes a
    single NOT PASSED line instead of a raw traceback."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> None:
        try:
            fn(*args, **kwargs)
        except SystemExit:
            raise
        except BaseException as exc:  # noqa: BLE001 - intentional catch-all
            text = "".join(traceback.format_exception_only(type(exc), exc))
            not_passed(_last_line(text))

    return wrapper


# --------------------------------------------------------------------------
# kubectl helpers
# --------------------------------------------------------------------------

def kubectl(*args: str, ns: str | None = None, input: str | None = None,
            check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
    cmd = ["kubectl", "--context", CONTEXT]
    if ns:
        cmd += ["-n", ns]
    cmd += list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input)
    except FileNotFoundError:
        not_passed("kubectl not found on PATH")
    except subprocess.TimeoutExpired:
        not_passed(f"kubectl {' '.join(args)} timed out after {timeout}s")
    if check and result.returncode != 0:
        not_passed(f"kubectl {' '.join(args)} failed: {_last_line(result.stderr)}")
    return result


def kubectl_json(*args: str, ns: str | None = None, check: bool = True):
    result = kubectl(*args, "-o", "json", ns=ns, check=check)
    if not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        not_passed(f"kubectl {' '.join(args)} did not return valid JSON: {e}")


def require_cluster() -> None:
    """Verify the sandbox20 kind cluster is up, all nodes Ready, and Calico
    healthy. Every validator calls this first."""
    fix = "run `bash scripts/cluster-up.sh` from the module root (20-kubernetes/) to (re)create it"

    try:
        clusters = subprocess.run(["kind", "get", "clusters"], capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        not_passed(f"kind not found on PATH -- {fix}")
    if CLUSTER_NAME not in clusters.stdout.split():
        not_passed(f"kind cluster '{CLUSTER_NAME}' not found -- {fix}")

    nodes_result = kubectl("get", "nodes", "-o", "json", check=False, timeout=20)
    if nodes_result.returncode != 0:
        not_passed(f"cannot reach cluster context {CONTEXT} -- {fix}")
    try:
        nodes = json.loads(nodes_result.stdout).get("items", [])
    except json.JSONDecodeError:
        not_passed(f"kubectl get nodes returned invalid JSON -- {fix}")
    if len(nodes) < 3:
        not_passed(f"expected 3 nodes in cluster '{CLUSTER_NAME}', found {len(nodes)} -- {fix}")

    not_ready = []
    for node in nodes:
        conditions = {c["type"]: c["status"] for c in node.get("status", {}).get("conditions", [])}
        if conditions.get("Ready") != "True":
            not_ready.append(node["metadata"]["name"])
    if not_ready:
        not_passed(f"node(s) not Ready: {', '.join(not_ready)} -- {fix}")

    ds_result = kubectl("get", "daemonset", "calico-node", "-o", "json", ns="kube-system", check=False, timeout=20)
    if ds_result.returncode != 0:
        not_passed(f"calico-node DaemonSet not found in kube-system -- {fix}")
    try:
        ds = json.loads(ds_result.stdout)
    except json.JSONDecodeError:
        not_passed(f"calico-node DaemonSet status unreadable -- {fix}")
    desired = ds.get("status", {}).get("desiredNumberScheduled", 0)
    ready = ds.get("status", {}).get("numberReady", 0)
    if desired == 0 or ready < desired:
        not_passed(f"calico-node DaemonSet not fully ready ({ready}/{desired}) -- {fix}")


def ensure_ns(name: str) -> str:
    kubectl("create", "namespace", name, check=False)
    return name


def delete_ns(name: str, wait: bool = False) -> None:
    args = ["delete", "namespace", name, "--ignore-not-found=true"]
    if not wait:
        args.append("--wait=false")
    kubectl(*args, check=False, timeout=120 if wait else 30)


def wait_until(fn: Callable[[], bool], timeout: float = 60, interval: float = 1.0,
               desc: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    last_exc = None
    while time.monotonic() < deadline:
        try:
            if fn():
                return
        except Exception as e:  # noqa: BLE001 - poll and retry
            last_exc = e
        time.sleep(interval)
    suffix = f": {last_exc}" if last_exc else ""
    not_passed(f"timed out after {timeout}s waiting for {desc}{suffix}")


def wait_rollout(kind_name: str, ns: str, timeout: int = 120) -> None:
    """kind_name e.g. 'deployment/my-app'."""
    kubectl("rollout", "status", kind_name, f"--timeout={timeout}s", ns=ns, timeout=timeout + 10)


def pod_names(selector: str, ns: str) -> list[str]:
    data = kubectl_json("get", "pods", "-l", selector, ns=ns)
    return [item["metadata"]["name"] for item in data.get("items", [])]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def port_forward(target: str, remote_port: int, ns: str):
    """Spawn `kubectl port-forward` to `target` (e.g. 'svc/my-app' or
    'pod/my-app-xyz'), wait until connectable, yield the local port, then
    terminate the subprocess. Works on Windows (CREATE_NEW_PROCESS_GROUP)."""
    local_port = _free_port()
    cmd = ["kubectl", "--context", CONTEXT, "-n", ns, "port-forward", target, f"{local_port}:{remote_port}"]
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=creationflags,
    )
    try:
        deadline = time.monotonic() + 20
        connected = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                not_passed(f"kubectl port-forward to {target} exited early: {_last_line(out)}")
            try:
                with socket.create_connection(("127.0.0.1", local_port), timeout=0.5):
                    connected = True
                    break
            except OSError:
                time.sleep(0.2)
        if not connected:
            not_passed(f"port-forward to {target} did not become connectable within 20s")
        yield local_port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def http_get(url: str, timeout: float = 5):
    """Returns (status_code, body) without raising; (None, error_message) on failure."""
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.status_code, resp.text
    except requests.RequestException as e:
        return None, str(e)


# --------------------------------------------------------------------------
# Doc-gate helpers (for written tasks, e.g. 18-app-of-apps-and-rollback,
# 21-helm-vs-kustomize-writeup) -- trimmed from 17-system-design/harness.
# --------------------------------------------------------------------------

def read_doc(path) -> str:
    p = Path(path)
    if not p.exists():
        not_passed(f"expected file not found: {p}")
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        not_passed(f"file is empty: {p}")
    return text


def _parse_headings(text: str, level: int) -> dict:
    marker = "#" * level
    pattern = re.compile(r"^" + re.escape(marker) + r"[ \t]+(.+?)[ \t]*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    sections = {}
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[heading] = text[start:end].strip()
    return sections


def parse_sections(text: str) -> dict:
    return _parse_headings(text, level=2)


def parse_subsections(text: str) -> dict:
    return _parse_headings(text, level=3)


PLACEHOLDER_MARKERS = ("[fill in", "[FILL IN", "TODO:", "<your answer", "[replace")


def _has_placeholder(body: str) -> bool:
    return any(marker in body for marker in PLACEHOLDER_MARKERS)


def check_no_placeholders(body: str, label: str) -> None:
    if _has_placeholder(body):
        not_passed(f"{label}: still contains a placeholder marker -- fill this in")


def check_sections(path, required: list, min_chars) -> dict:
    text = read_doc(path)
    sections = parse_sections(text)

    missing = [h for h in required if h not in sections]
    if missing:
        not_passed(f"missing required section(s): {', '.join(missing)}")

    def _min_for(heading):
        if isinstance(min_chars, dict):
            return min_chars.get(heading, min_chars.get("_default", 0))
        return min_chars

    too_short = []
    for h in required:
        body = sections[h].strip()
        need = _min_for(h)
        if len(body) < need:
            too_short.append(f"'{h}' ({len(body)}/{need} chars)")
    if too_short:
        not_passed(f"section(s) too short: {', '.join(too_short)}")

    for h in required:
        check_no_placeholders(sections[h], f"section '{h}'")

    return sections


def check_keywords(body: str, keywords: list, min_hits: int, label: str) -> None:
    lowered = body.lower()
    hits = {kw for kw in keywords if kw.lower() in lowered}
    if len(hits) < min_hits:
        not_passed(
            f"{label}: found {len(hits)}/{min_hits} required grounding keyword(s) "
            f"among {list(keywords)} (matched: {sorted(hits)})"
        )


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _dedupe_sentences(text: str) -> str:
    seen, kept = set(), []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s = sentence.strip()
        if s and s not in seen:
            seen.add(s)
            kept.append(s)
    return " ".join(kept)


def _original_char_count(answer: str, questions_text: str, min_block: int = 40) -> int:
    a = _dedupe_sentences(_normalize_ws(answer))
    q = _normalize_ws(questions_text)
    if not a or not q:
        return len(a)
    matcher = difflib.SequenceMatcher(None, a, q, autojunk=False)
    borrowed = sum(b.size for b in matcher.get_matching_blocks() if b.size >= min_block)
    return max(len(a) - borrowed, 0)


def check_answers(
    path,
    question_ids: list,
    min_answered: int,
    min_chars: int = 200,
    questions_path=None,
    min_original_chars: int = 120,
) -> None:
    text = read_doc(path)
    subsections = parse_subsections(text)

    questions_text = None
    if questions_path is not None:
        questions_text = read_doc(questions_path)

    problems = []
    answered = 0
    for qid in question_ids:
        body = subsections.get(qid)
        if body is None:
            problems.append(f"{qid} (missing)")
            continue

        stripped = body.strip()
        lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
        question_line = lines[0] if lines else ""

        if _has_placeholder(stripped):
            problems.append(f"{qid} (placeholder)")
            continue
        if questions_text is None and stripped == question_line:
            problems.append(f"{qid} (verbatim copy of the question)")
            continue
        if len(stripped) < min_chars:
            problems.append(f"{qid} (too short: {len(stripped)}/{min_chars} chars)")
            continue
        if questions_text is not None:
            original = _original_char_count(stripped, questions_text)
            if original < min_original_chars:
                problems.append(
                    f"{qid} (mostly restates the question: {original}/{min_original_chars} "
                    "characters of your own)"
                )
                continue

        answered += 1

    if answered < min_answered:
        not_passed(
            f"only {answered}/{min_answered} required hostile-review question(s) answered; "
            f"unanswered or insufficient: {', '.join(problems) if problems else '(none)'}"
        )
