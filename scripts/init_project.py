#!/usr/bin/env python3
"""Initialize a project with durable orchestration documents and agent profiles."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from _common import PROJECT_TEMPLATE, project_root


def build_plan(target: Path) -> list[tuple[Path, Path]]:
    plan: list[tuple[Path, Path]] = []
    for source in sorted(PROJECT_TEMPLATE.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(PROJECT_TEMPLATE)
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


def initialize(target: Path, name: str, domain: str, complexity: str, dry_run: bool) -> None:
    if not PROJECT_TEMPLATE.is_dir():
        raise ValueError(f"Bundled project template is missing: {PROJECT_TEMPLATE}")
    if not name.strip() or any(character in name for character in "\r\n\0"):
        raise ValueError("project-name must be non-empty and contain no control newlines")
    if not domain.strip() or any(character in domain for character in "\r\n\0"):
        raise ValueError("domain must be non-empty and contain no control newlines")
    plan = build_plan(target)
    conflicts = [destination for _, destination in plan if destination.exists()]
    if conflicts:
        listing = "\n".join(f"  - {path}" for path in conflicts[:20])
        suffix = "\n  - ..." if len(conflicts) > 20 else ""
        raise ValueError(
            "Initialization stopped before writing because target files already exist. "
            "Merge the template manually or choose an empty project directory:\n"
            f"{listing}{suffix}"
        )
    print(f"Project: {name}")
    print(f"Target: {target}")
    print(f"Domain: {domain}")
    print(f"Complexity: {complexity}")
    print(f"Files to create: {len(plan)}")
    if dry_run:
        for _, destination in plan:
            print(f"  {destination}")
        print("DRY RUN: no files written")
        return
    values = {
        "PROJECT_NAME": name,
        "DOMAIN": domain,
        "COMPLEXITY": complexity,
        "DATE": date.today().isoformat(),
    }
    target.mkdir(parents=True, exist_ok=True)
    for source, destination in plan:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix in {".md", ".toml", ".yaml", ".json", ".template"} or source.name.endswith(".md.template"):
            destination.write_text(render(source, values), encoding="utf-8")
        else:
            shutil.copy2(source, destination)
    print("Initialized successfully. Start with docs/00-project-context.md and docs/project-status.json.")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("project_dir", help="New or empty target project directory")
    result.add_argument("--project-name", required=True, help="Human-readable project name")
    result.add_argument("--domain", required=True, help="Business domain, for example ecommerce, CRM, SaaS, or AI agent")
    result.add_argument("--complexity", choices=["Simple", "Standard", "Complex"], default="Standard")
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
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
