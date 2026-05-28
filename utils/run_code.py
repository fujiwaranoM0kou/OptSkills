from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError
from concurrent.futures.process import BrokenProcessPool
from typing import Any, Dict, Optional


def _safe_float(value: str) -> Optional[float]:
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return None


def extract_result(stdout: str) -> Any:
    if not stdout:
        return None

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("RESULT_JSON:"):
            payload = line.split("RESULT_JSON:", 1)[1].strip()
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue
        if line.startswith("RESULT:"):
            payload = line.split("RESULT:", 1)[1].strip()
            numeric = _safe_float(payload)
            return numeric if numeric is not None else payload

    block_match = re.search(r"\{[\s\S]*\}", stdout)
    if block_match:
        snippet = block_match.group(0)
        try:
            obj = json.loads(snippet)
            if isinstance(obj, dict) and "result" in obj:
                return obj["result"]
        except json.JSONDecodeError:
            pass

    return None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _should_use_persistent_mode(python_bin: Optional[str]) -> bool:
    if not _env_bool("OPTSKILL_RUN_CODE_PERSISTENT", True):
        return False
    main_entry = str(sys.argv[0]).strip().lower()
    if not main_entry or main_entry in {"-c", "-"} or "<stdin>" in main_entry:
        return False
    if not python_bin:
        return True
    try:
        requested = os.path.abspath(str(python_bin))
        current = os.path.abspath(sys.executable)
    except Exception:
        return False
    return requested == current


def _persistent_workers() -> int:
    default_workers = min(max(1, (os.cpu_count() or 2) // 2), 8)
    configured = _env_int("OPTSKILL_RUN_CODE_WORKERS", default_workers)
    return max(1, int(configured))


def _execute_code_worker(code: str, cwd: Optional[str]) -> Dict[str, Any]:
    start = time.time()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    old_cwd = ""
    changed_cwd = False
    returncode = 0
    try:
        if isinstance(cwd, str) and cwd.strip():
            old_cwd = os.getcwd()
            os.chdir(cwd)
            changed_cwd = True
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            scope: Dict[str, Any] = {"__name__": "__main__"}
            compiled = compile(code, "<run_code>", "exec")
            exec(compiled, scope, scope)
    except BaseException:  # noqa: BLE001 - capture all user code failures
        returncode = 1
        traceback.print_exc(file=stderr_buf)
    finally:
        if changed_cwd:
            try:
                os.chdir(old_cwd)
            except Exception:
                pass
    stdout = stdout_buf.getvalue()
    stderr = stderr_buf.getvalue()
    result = extract_result(stdout) if returncode == 0 else None
    return {
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "result": result,
        "timeout": False,
        "duration_s": round(time.time() - start, 3),
    }


_EXECUTOR: Optional[ProcessPoolExecutor] = None
_EXECUTOR_WORKERS = 0
_EXECUTOR_LOCK = threading.Lock()


def _shutdown_executor(executor: ProcessPoolExecutor) -> None:
    processes = getattr(executor, "_processes", None)
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        executor.shutdown(wait=False)
    except Exception:
        pass
    if isinstance(processes, dict):
        for proc in list(processes.values()):
            try:
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=0.2)
                if proc.is_alive():
                    proc.kill()
                    proc.join(timeout=0.2)
            except Exception:
                pass


def _ensure_executor() -> ProcessPoolExecutor:
    global _EXECUTOR, _EXECUTOR_WORKERS
    workers = _persistent_workers()
    with _EXECUTOR_LOCK:
        if _EXECUTOR is not None and _EXECUTOR_WORKERS == workers:
            return _EXECUTOR
        if _EXECUTOR is not None:
            _shutdown_executor(_EXECUTOR)
        _EXECUTOR = ProcessPoolExecutor(max_workers=workers)
        _EXECUTOR_WORKERS = workers
        return _EXECUTOR


def _reset_executor() -> None:
    global _EXECUTOR, _EXECUTOR_WORKERS
    with _EXECUTOR_LOCK:
        if _EXECUTOR is not None:
            _shutdown_executor(_EXECUTOR)
        _EXECUTOR = None
        _EXECUTOR_WORKERS = 0


def _run_python_code_subprocess(
    code: str,
    timeout: int = 60,
    cwd: Optional[str] = None,
    python_bin: Optional[str] = None,
) -> Dict[str, Any]:
    python_exec = python_bin or sys.executable
    start = time.time()

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".py",
        delete=False,
    ) as handle:
        handle.write(code)
        script_path = handle.name

    try:
        proc = subprocess.run(
            [python_exec, script_path],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        returncode = proc.returncode
        result = extract_result(stdout) if returncode == 0 else None
        return {
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "result": result,
            "timeout": False,
            "duration_s": round(time.time() - start, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": -1,
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + "\n[TimeoutExpired]",
            "result": None,
            "timeout": True,
            "duration_s": round(time.time() - start, 3),
        }
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)


def _run_python_code_persistent(
    code: str,
    timeout: int = 60,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    start = time.time()
    try:
        executor = _ensure_executor()
        future = executor.submit(_execute_code_worker, code, cwd)
        payload = future.result(timeout=timeout)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected persistent worker payload type: {type(payload)}")
        payload["duration_s"] = round(time.time() - start, 3)
        return payload
    except FuturesTimeoutError:
        _reset_executor()
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": "[TimeoutExpired]",
            "result": None,
            "timeout": True,
            "duration_s": round(time.time() - start, 3),
        }
    except BrokenProcessPool:
        _reset_executor()
        return _run_python_code_subprocess(code=code, timeout=timeout, cwd=cwd, python_bin=None)
    except Exception:
        _reset_executor()
        return _run_python_code_subprocess(code=code, timeout=timeout, cwd=cwd, python_bin=None)


def run_python_code(
    code: str,
    timeout: int = 60,
    cwd: Optional[str] = None,
    python_bin: Optional[str] = None,
) -> Dict[str, Any]:
    if _should_use_persistent_mode(python_bin=python_bin):
        return _run_python_code_persistent(code=code, timeout=timeout, cwd=cwd)
    return _run_python_code_subprocess(code=code, timeout=timeout, cwd=cwd, python_bin=python_bin)
