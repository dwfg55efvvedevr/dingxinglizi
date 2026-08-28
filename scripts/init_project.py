#!/usr/bin/env python3
"""Initialize a project with durable orchestration documents and agent profiles."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Mapping, Optional

from _common import PROJECT_TEMPLATE, project_root
from evolution_store import initialize_workspace
from model_routing import PLATFORM_POLICY_VERSION, POLICY_VERSION as LEGACY_MODEL_POLICY_VERSION


def build_plan(target: Path, platform_neutral: bool = False) -> list[tuple[Path, Path]]:
    plan: list[tuple[Path, Path]] = []
    for source in sorted(PROJECT_TEMPLATE.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(PROJECT_TEMPLATE)
        if platform_neutral:
            if relative.parts[:2] == (".codex", "agents"):
                continue
            if relative.parts[:2] == (".codex", "orchestration"):
                relative = Path(".dingxinglizi", *relative.parts[1:])
            elif relative.parts[:2] == (".codex", "runs"):
                relative = Path(".dingxinglizi", *relative.parts[1:])
        if relative == Path("AGENTS.md.template"):
            relative = Path("AGENTS.md")
        plan.append((source, target / relative))
    return plan


def render(source: Path, values: dict[str, str]) -> str:
    text = source.read_text(encoding="utf-8")
    for key, value in values.items():
        needs_quoted_escape = source.suffix in {".json", ".yaml"} or (source.suffix == ".md" and key == "PROJECT_NAME")
        replacement = json.dumps(value)[1:-1] if needs_quoted_escape else value
        text = text.replace("{{" + key + "}}", replacement)
    return text


def _target_is_safe(target: Path, destination: Path) -> bool:
    """Reject lexical escapes, symlinks, and non-directory ancestors."""
    try:
        relative = destination.relative_to(target)
    except ValueError:
        return False
    current = target
    for index, part in enumerate(relative.parts):
        current = current / part
        is_leaf = index == len(relative.parts) - 1
        if current.is_symlink():
            return False
        if not is_leaf and current.exists() and not current.is_dir():
            return False
    return True


def initialize(
    target: Path,
    name: str,
    domain: str,
    complexity: str,
    dry_run: bool,
    *,
    platform_neutral: bool = False,
    generated_files: Optional[Mapping[Path, str]] = None,
) -> None:
    if not PROJECT_TEMPLATE.is_dir():
        raise ValueError(f"Bundled project template is missing: {PROJECT_TEMPLATE}")
    if not name.strip() or any(character in name for character in "\r\n\0"):
        raise ValueError("project-name must be non-empty and contain no control newlines")
    if not domain.strip() or any(character in domain for character in "\r\n\0"):
        raise ValueError("domain must be non-empty and contain no control newlines")
    plan = build_plan(target, platform_neutral=platform_neutral)
    generated = dict(generated_files or {})
    generated_destinations: list[tuple[Path, str]] = []
    for relative, content in generated.items():
        if relative.is_absolute() or ".." in relative.parts or relative == Path("."):
            raise ValueError("Generated project path must be a safe relative path: %s" % relative)
        generated_destinations.append((target / relative, content))
    all_destinations = [destination for _, destination in plan] + [
        destination for destination, _ in generated_destinations
    ]
    duplicates = {
        destination for destination in all_destinations
        if all_destinations.count(destination) > 1
    }
    conflicts = [
        destination for destination in all_destinations
        if destination.exists() or not _target_is_safe(target, destination)
    ] + sorted(duplicates)
    if conflicts:
        listing = "\n".join(f"  - {path}" for path in conflicts[:20])
        suffix = "\n  - ..." if len(conflicts) > 20 else ""
        raise ValueError(
            "Initialization stopped before writing because target files already exist "
            "or traverse an unsafe path. Merge the template manually, remove the unsafe "
            "path, or choose an empty project directory:\n"
            f"{listing}{suffix}"
        )
    print(f"Project: {name}")
    print(f"Target: {target}")
    print(f"Domain: {domain}")
    print(f"Complexity: {complexity}")
    print(f"Files to create: {len(all_destinations)}")
    if dry_run:
        for destination in all_destinations:
            print(f"  {destination}")
        print("DRY RUN: no files written")
        return
    values = {
        "PROJECT_NAME": name,
        "DOMAIN": domain,
        "COMPLEXITY": complexity,
        "DATE": date.today().isoformat(),
        "MODEL_POLICY_VERSION": (
            PLATFORM_POLICY_VERSION if platform_neutral else LEGACY_MODEL_POLICY_VERSION
        ),
    }
    # Fully render/read every payload before the first project write.  This
    # makes schema, template, and source-read failures zero-write failures.
    prepared: list[tuple[Path, bytes]] = []
    for source, destination in plan:
        if source.suffix in {".md", ".toml", ".yaml", ".json", ".template"} or source.name.endswith(".md.template"):
            content = render(source, values)
            if platform_neutral and destination.name == "model-routing-policy.json":
                content = json.dumps({
                    "policy_version": PLATFORM_POLICY_VERSION,
                    "routing_unit": "task_package",
                    "runtime_precedence": [
                        "task_package_execution_profile", "verified_platform_runtime_manifest",
                        "explicit_spawn_override", "runtime_agent_default", "parent_inheritance",
                    ],
                    "capability_tiers": ["Economy", "Standard", "Advanced", "Expert", "Exceptional"],
                    "provider_resolution": "verified_runtime_manifest_only",
                    "max_attempts": 3,
                    "max_escalations": 2,
                    "silent_high_risk_downgrade": False,
                    "permanent_role_model_binding": False,
                }, ensure_ascii=False, indent=2) + "\n"
            elif platform_neutral and destination == target / "docs/project-status.json":
                status = json.loads(content)
                status["execution_control"]["model_routing_policy"] = PLATFORM_POLICY_VERSION
                content = json.dumps(status, ensure_ascii=False, indent=2) + "\n"
            prepared.append((destination, content.encode("utf-8")))
        else:
            prepared.append((destination, source.read_bytes()))
    prepared.extend(
        (destination, content.encode("utf-8"))
        for destination, content in generated_destinations
    )
    target.mkdir(parents=True, exist_ok=True)
    for destination, content in prepared:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    evolution = initialize_workspace(target)
    print(f"Evolution workspace: {evolution['status']} ({evolution['workspace']})")
    if platform_neutral:
        print("Initialized platform-neutral control state successfully. Render one host adapter before dispatch.")
    else:
        print("Initialized legacy-compatible Codex project state successfully.")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("project_dir", help="New or empty target project directory")
    result.add_argument("--project-name", required=True, help="Human-readable project name")
    result.add_argument("--domain", required=True, help="Business domain, for example ecommerce, CRM, SaaS, or AI agent")
    result.add_argument("--complexity", choices=["Simple", "Standard", "Complex"], default="Standard")
    result.add_argument(
        "--platform-neutral",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    result.add_argument("--dry-run", action="store_true", help="Show planned files without writing")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        target = project_root(args.project_dir)
        initialize(
            target,
            args.project_name.strip(),
            args.domain.strip(),
            args.complexity,
            args.dry_run,
            platform_neutral=args.platform_neutral,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
