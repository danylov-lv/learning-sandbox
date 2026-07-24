"""Shared plumbing for task 22's checkpoint validators: run the learner's
kopf operator as a real subprocess against namespace t22, wait until it
reports it is watching `scrapejobs`, and tear it down afterwards.

Not a validator itself -- imported by validate_cp1.py / validate_cp2.py /
validate_cp3.py.

Windows gotcha (see NOTES): `python -m kopf run` spawns its own internal
child process on this platform (confirmed via Win32_Process during
authoring -- same command line, one level down). Terminating the
Popen'd process directly still reaps that child as a side effect on this
setup; there is no separate process-group step required beyond the
CREATE_NEW_PROCESS_GROUP flag `harness.common.port_forward` already uses
elsewhere in this module. We spawn `sys.executable` directly (not `uv run
python ...`) specifically so the process we hold a handle to IS the
interpreter running kopf, not a wrapper launcher one level removed from it.

Cleanup gotcha: kopf attaches a finalizer to every ScrapeJob it observes,
even a CR whose handlers all raised NotImplementedError. If the operator
is killed before that finalizer is removed, `kubectl delete namespace t22`
(and `kubectl delete crd`) would hang forever waiting for it. `full_cleanup`
strips finalizers directly before deleting anything, so cleanup is
non-blocking regardless of whether the learner's handlers ever succeeded.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import kubectl, kubectl_json, not_passed  # noqa: E402

NS = "t22"
GROUP = "sandbox20.dev"
CRD_NAME = "scrapejobs.sandbox20.dev"
OPERATOR_PATH = TASK_ROOT / "src" / "operator.py"
CRD_PATH = TASK_ROOT / "src" / "crd.yaml"

WATCH_MARKER = f"Starting the watch-stream for scrapejobs.v1.{GROUP}"


def _scoped_kubeconfig_text() -> str:
    # kubectl() (harness.common) always pins --context kind-sandbox20, so
    # this is a kubeconfig whose only cluster/context IS the sandbox --
    # the operator subprocess can't accidentally point anywhere else.
    result = kubectl("config", "view", "--minify", "--flatten", timeout=20)
    return result.stdout


class Operator:
    """Spawns the learner's operator.py under kopf and captures its full
    stdout/stderr to a log file this process can poll and grep."""

    def __init__(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="t22-operator-"))
        self._log_path = self._tmp_dir / "operator.log"
        self._proc: subprocess.Popen | None = None
        self._log_file = None

    def start(self, timeout: float = 30) -> None:
        kubeconfig_path = self._tmp_dir / "kubeconfig.yaml"
        kubeconfig_path.write_text(_scoped_kubeconfig_text(), encoding="utf-8")

        env = dict(os.environ)
        env["KUBECONFIG"] = str(kubeconfig_path)
        env["PYTHONUNBUFFERED"] = "1"

        self._log_file = open(self._log_path, "w", encoding="utf-8")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "kopf", "run", str(OPERATOR_PATH), "--namespace", NS, "--verbose"],
            cwd=str(TASK_ROOT),
            env=env,
            stdout=self._log_file,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                not_passed(
                    f"operator subprocess exited early (code {self._proc.returncode}) while starting up -- "
                    f"log tail: {self._tail()}"
                )
            if WATCH_MARKER in self.log_text():
                return
            time.sleep(0.5)
        not_passed(f"operator never reported it was watching scrapejobs within {timeout}s -- log tail: {self._tail()}")

    def log_text(self) -> str:
        try:
            return self._log_path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    def _tail(self, n: int = 20) -> str:
        lines = [ln for ln in self.log_text().splitlines() if ln.strip()]
        return " | ".join(lines[-n:]) if lines else "(empty log)"

    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def require_alive(self, context: str) -> None:
        if not self.alive():
            not_passed(
                f"operator subprocess died {context} (exit code {self._proc.returncode if self._proc else '?'}) "
                f"-- log tail: {self._tail()}"
            )

    def stop(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                try:
                    self._proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
        if self._log_file:
            self._log_file.close()
            self._log_file = None


def strip_finalizers() -> None:
    data = kubectl_json("get", "scrapejobs", ns=NS, check=False)
    for item in data.get("items", []):
        name = item.get("metadata", {}).get("name")
        if name:
            kubectl(
                "patch", "scrapejob", name, "--type=merge", "-p", '{"metadata":{"finalizers":[]}}',
                ns=NS, check=False, timeout=20,
            )


def full_cleanup() -> None:
    """Best-effort, never raises: strip finalizers, then delete the
    namespace and CRD and BLOCK until both are actually gone. Safe to call
    whether or not either exists, and whether or not the operator ever
    successfully reconciled anything.

    Blocking (rather than --wait=false) matters here specifically: CP3 runs
    CP1 then CP2 back-to-back as subprocesses with no gap, and a learner
    re-running checkpoints by hand does the same. A fire-and-forget delete
    would leave namespace t22 "Terminating" when the next checkpoint's
    ensure_ns/apply lands, which fails with a transient "being terminated"
    error rather than a clean pass -- waiting here trades a few extra
    seconds of cleanup for that race never happening."""
    try:
        strip_finalizers()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - cleanup must never itself fail the run
        pass
    kubectl("delete", "namespace", NS, "--ignore-not-found=true", "--wait=true", check=False, timeout=90)
    kubectl("delete", "crd", CRD_NAME, "--ignore-not-found=true", "--wait=true", check=False, timeout=60)


def deployments_for(cr_name: str):
    data = kubectl_json(
        "get", "deployments", "-l", f"app.kubernetes.io/managed-by=scrapejob-operator,scrapejob-name={cr_name}",
        ns=NS, check=False,
    )
    return data.get("items", [])


def apply_crd() -> None:
    result = kubectl("apply", "-f", str(CRD_PATH), check=False, timeout=30)
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        # The API server reports CRD validation as one bullet per bad/missing
        # field ("* spec.group: Required value", ...) -- surface all of them,
        # not just the last, since the first one is usually the clearest.
        bullets = [ln.strip() for ln in err.splitlines() if ln.strip().startswith("*")]
        detail = "; ".join(bullets) if bullets else (err.splitlines()[-1] if err else "(no output)")
        not_passed(f"kubectl apply -f src/crd.yaml failed: {detail}")


def apply_cr(yaml_text: str) -> None:
    result = kubectl("apply", "-f", "-", ns=NS, input=yaml_text, check=False, timeout=30)
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        not_passed(f"kubectl apply of the ScrapeJob CR failed: {err.splitlines()[-1] if err else '(no output)'}")
