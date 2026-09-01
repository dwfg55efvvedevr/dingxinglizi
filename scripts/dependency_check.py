#!/usr/bin/env python3
"""Report runtime, optional feature, and development-only dependencies honestly."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from typing import Any, Callable


MINIMUM_PYTHON = (3, 9)
HOST_EXECUTABLES = {
    "codex": "codex",
    "cursor": "cursor",
    "claude-code": "claude",
    "opencode": "opencode",
}


def dependency_report(
    *,
    version_info: tuple[int, int, int] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
) -> dict[str, Any]:
    version = version_info or (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    python_ok = version >= MINIMUM_PYTHON + (0,)
    git_path = which("git")
    pyyaml_available = find_spec("yaml") is not None

    hosts = []
    for platform, executable in HOST_EXECUTABLES.items():
        path = which(executable)
        hosts.append({
            "id": f"host.{platform}",
            "required": False,
            "status": "AVAILABLE" if path else "NOT_FOUND",
            "executable": executable,
            "path": path,
            "impact_if_missing": f"Cannot verify or launch the optional {platform} native runtime from this machine.",
        })

    notices = []
    if not git_path:
        notices.append({
            "level": "WARNING",
            "id": "optional.git",
            "message": "Git is not installed. Core orchestration still runs, but Git target pinning, Git-native review evidence, and Git-aware migration checks are limited.",
            "action": "Install Git only if those Git-backed features are needed.",
        })
    if not pyyaml_available:
        notices.append({
            "level": "INFO",
            "id": "development.pyyaml",
            "message": "PyYAML is not installed. The Skill runtime is unaffected; only OpenAI skill-creator's optional quick_validate.py developer check is unavailable in this Python environment.",
            "action": "If you need that external validator, install PyYAML into the same Python environment that runs quick_validate.py. Do not add PyYAML merely to run this Skill.",
        })

    return {
        "schema_version": 1,
        "status": "RUNTIME_READY" if python_ok else "BLOCKED_RUNTIME",
        "runtime_ready": python_ok,
        "runtime_dependencies": [
            {
                "id": "python",
                "required": True,
                "minimum_version": "3.9",
                "detected_version": ".".join(str(part) for part in version),
                "status": "PASS" if python_ok else "FAIL",
                "impact_if_missing": "The deterministic control-plane scripts cannot run.",
            },
            {
                "id": "third-party-python-packages",
                "required": False,
                "status": "NONE_REQUIRED",
                "evidence": "The portable runtime uses the Python standard library only.",
            },
        ],
        "optional_feature_dependencies": [
            {
                "id": "git",
                "required": False,
                "status": "AVAILABLE" if git_path else "NOT_FOUND",
                "path": git_path,
                "used_for": ["Git target pinning", "Git-native repository review", "Git-aware migration and exposure checks"],
            },
            *hosts,
        ],
        "development_dependencies": [
            {
                "id": "pyyaml",
                "import_name": "yaml",
                "required_for_skill_runtime": False,
                "status": "AVAILABLE" if pyyaml_available else "NOT_FOUND",
                "used_for": "OpenAI skill-creator quick_validate.py only; not used by software-project-orchestrator.",
            },
        ],
        "notices": notices,
    }


def print_human(report: dict[str, Any]) -> None:
    print(f"Software Project Orchestrator dependencies: {report['status']}")
    runtime = report["runtime_dependencies"]
    python = next(item for item in runtime if item["id"] == "python")
    print(f"Runtime: Python {python['detected_version']} ({python['status']}); third-party Python packages required: none")
    for notice in report["notices"]:
        print(f"{notice['level']}: {notice['id']}: {notice['message']}")
        print(f"  NEXT: {notice['action']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()
    report = dependency_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human(report)
    return 0 if report["runtime_ready"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
