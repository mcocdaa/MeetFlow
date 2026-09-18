from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib
from typing import Any

from sqlalchemy import text


def package_version() -> str:
    try:
        return version("meetflow")
    except PackageNotFoundError:
        # Source checkout without installed metadata: keep `pyproject.toml` the single
        # source of truth instead of a hardcoded fallback that drifts on every release.
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject.is_file():
            with pyproject.open("rb") as fh:
                return tomllib.load(fh)["project"]["version"]
        return "0.0.0+unknown"


def readiness_payload(
    database: Any,
    plugin_manager: Any,
    plugin_worker: Any,
    *,
    test_mode: bool = False,
) -> tuple[dict[str, str], bool]:
    try:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:
        database_status = "error"

    plugins_status = "ok" if not plugin_manager.errors() else "error"
    if test_mode:
        worker_status = "stopped-in-test"
    else:
        worker_status = "running" if plugin_worker.running else "stopped"

    ready = database_status == "ok" and plugins_status == "ok"
    return (
        {
            "status": "ready" if ready else "not_ready",
            "database": database_status,
            "plugins": plugins_status,
            "worker": worker_status,
        },
        ready,
    )
