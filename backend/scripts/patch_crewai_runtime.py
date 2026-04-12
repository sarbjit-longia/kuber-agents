"""
Patch known CrewAI runtime typing issues for Python 3.11.

CrewAI 1.6.0 ships a forward annotation using `threading.Lock | None`, but
`threading.Lock` is a factory function in Python 3.11, not a type. Pydantic
evaluates that annotation during import and raises a TypeError, which prevents
the backend from starting.

This patch rewrites the affected PrivateAttr annotations to `object | None`.
"""
from __future__ import annotations

from pathlib import Path
import sys


TARGET = Path("/usr/local/lib/python3.11/site-packages/crewai/utilities/rpm_controller.py")


def main() -> int:
    if not TARGET.exists():
        print(f"skipping CrewAI patch, file not found: {TARGET}")
        return 0

    original = TARGET.read_text(encoding="utf-8")
    patched = original.replace(
        '_timer: "threading.Timer | None" = PrivateAttr(default=None)',
        '_timer: "object | None" = PrivateAttr(default=None)',
    ).replace(
        '_lock: "threading.Lock | None" = PrivateAttr(default=None)',
        '_lock: "object | None" = PrivateAttr(default=None)',
    )

    if patched == original:
        print("CrewAI patch already applied or target lines not found")
        return 0

    TARGET.write_text(patched, encoding="utf-8")
    print(f"patched CrewAI runtime file: {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
