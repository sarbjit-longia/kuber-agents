"""
Single-run entrypoint for an ephemeral backtest runtime container.
"""
from __future__ import annotations

from datetime import datetime
import os
import subprocess
import sys
import time
from urllib.request import urlopen
from uuid import UUID

import structlog

from app.config import settings
from app.database import SessionLocal
from app.models.backtest_run import BacktestRun
from app.orchestration.tasks.run_backtest import execute_backtest_run

logger = structlog.get_logger()


def _wait_for_http(url: str, timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2):
                return
        except Exception:
            time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for {url}")


def _start_embedded_signal_generator() -> subprocess.Popen | None:
    if not settings.BACKTEST_RUNTIME_EMBED_SIGNAL_GENERATOR:
        return None

    sg_root = "/opt/signal-generator"
    if not os.path.exists(os.path.join(sg_root, "app", "main.py")):
        raise FileNotFoundError(
            f"Embedded signal-generator is required but not available at {sg_root}"
        )

    env = os.environ.copy()
    env["PYTHONPATH"] = sg_root
    env["SIGNAL_GENERATOR_API_ONLY"] = "true"
    env["SIGNAL_GENERATOR_PORT"] = str(settings.BACKTEST_RUNTIME_SIGNAL_GENERATOR_PORT)
    process = subprocess.Popen(
        ["python", "-m", "app.main"],
        cwd=sg_root,
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    local_url = f"http://127.0.0.1:{settings.BACKTEST_RUNTIME_SIGNAL_GENERATOR_PORT}"
    _wait_for_http(f"{local_url}/health")
    os.environ["SIGNAL_GENERATOR_URL"] = local_url
    settings.SIGNAL_GENERATOR_URL = local_url
    logger.info(
        "embedded_signal_generator_started",
        pid=process.pid,
        signal_generator_url=local_url,
    )
    return process


def _update_runtime_record(backtest_run_id: str, **fields) -> None:
    db = SessionLocal()
    try:
        run = db.query(BacktestRun).filter(BacktestRun.id == UUID(backtest_run_id)).first()
        if not run:
            return

        run_config = dict(run.config or {})
        runtime_config = dict(run_config.get("runtime") or {})
        runtime_config.update(fields)
        run_config["runtime"] = runtime_config
        run.config = run_config
        db.commit()
    finally:
        db.close()


def main() -> int:
    backtest_run_id = os.getenv("BACKTEST_RUN_ID")
    if not backtest_run_id:
        logger.error("missing_backtest_run_id_env")
        print("BACKTEST_RUN_ID is required", file=sys.stderr)
        return 2

    logger.info("backtest_runtime_container_starting", backtest_run_id=backtest_run_id)
    embedded_signal_generator = None
    exit_code = 1
    try:
        _update_runtime_record(
            backtest_run_id,
            runtime_started_at=datetime.utcnow().isoformat(),
            runtime_hostname=os.getenv("HOSTNAME"),
            runtime_pid=os.getpid(),
        )
        embedded_signal_generator = _start_embedded_signal_generator()
        execute_backtest_run(backtest_run_id)
        logger.info("backtest_runtime_container_completed", backtest_run_id=backtest_run_id)
        exit_code = 0
        return exit_code
    except Exception as exc:
        _update_runtime_record(
            backtest_run_id,
            runtime_last_error=str(exc),
        )
        raise
    finally:
        _update_runtime_record(
            backtest_run_id,
            runtime_completed_at=datetime.utcnow().isoformat(),
            runtime_exit_code=exit_code,
        )
        if embedded_signal_generator:
            embedded_signal_generator.terminate()
            try:
                embedded_signal_generator.wait(timeout=10)
            except subprocess.TimeoutExpired:
                embedded_signal_generator.kill()


if __name__ == "__main__":
    raise SystemExit(main())
