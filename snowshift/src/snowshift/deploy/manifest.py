"""Parse manifest.yaml into the ordered plan the runner executes.

The manifest is deliberately dumb: a list of stages, each a directory. Ordering
comes from the list order and then from filename prefixes. There is no
dependency solver, because the dependencies here are a straight line and a
solver would only hide that.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ManifestError(RuntimeError):
    """The manifest is missing, malformed, or points at paths that do not exist."""


@dataclass(frozen=True)
class Stage:
    """One directory of SQL, run as a unit."""

    name: str
    path: Path
    description: str = ""
    idempotent: bool = True
    optional: bool = False

    def files(self) -> list[Path]:
        """SQL files in this stage, in filename order."""
        if not self.path.is_dir():
            raise ManifestError(f"stage {self.name!r} points at missing directory {self.path}")
        return sorted(self.path.glob("*.sql"))


@dataclass(frozen=True)
class Manifest:
    """The full deployment plan."""

    database: str
    schema: str
    warehouse: str
    stages: tuple[Stage, ...] = field(default_factory=tuple)
    root: Path = Path(".")

    def stage(self, name: str) -> Stage:
        for s in self.stages:
            if s.name == name:
                return s
        raise ManifestError(
            f"unknown stage {name!r}; known stages: {', '.join(s.name for s in self.stages)}"
        )

    def select(
        self,
        only: str | None = None,
        from_: str | None = None,
        through: str | None = None,
        include_optional: bool = False,
    ) -> list[Stage]:
        """Narrow the stage list the way the CLI flags describe.

        ``only`` wins outright and always includes the stage even if optional,
        since naming a stage explicitly is itself the opt-in.
        """
        if only:
            return [self.stage(only)]

        names = [s.name for s in self.stages]
        start = names.index(self.stage(from_).name) if from_ else 0
        end = names.index(self.stage(through).name) + 1 if through else len(names)
        if start > end - 1:
            raise ManifestError(f"--from {from_!r} comes after --through {through!r}")

        chosen = list(self.stages[start:end])
        if not include_optional:
            chosen = [s for s in chosen if not s.optional]
        return chosen


def load_manifest(path: str | os.PathLike[str] = "manifest.yaml") -> Manifest:
    """Read and validate a manifest, resolving stage paths relative to it."""
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise ManifestError(f"no manifest at {manifest_path}")

    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"{manifest_path} is not valid YAML: {exc}") from exc

    target = raw.get("target") or {}
    raw_stages = raw.get("stages") or []
    if not raw_stages:
        raise ManifestError(f"{manifest_path} declares no stages")

    root = manifest_path.parent
    stages = []
    seen: set[str] = set()
    for entry in raw_stages:
        name = entry.get("name")
        if not name:
            raise ManifestError("every stage needs a name")
        if name in seen:
            raise ManifestError(f"duplicate stage name {name!r}")
        seen.add(name)
        if not entry.get("path"):
            raise ManifestError(f"stage {name!r} has no path")
        stages.append(
            Stage(
                name=name,
                path=root / entry["path"],
                description=(entry.get("description") or "").strip(),
                idempotent=bool(entry.get("idempotent", True)),
                optional=bool(entry.get("optional", False)),
            )
        )

    # Environment wins over the manifest so CI can retarget without editing it.
    return Manifest(
        database=os.environ.get("SNOWSHIFT_DATABASE") or target.get("database", ""),
        schema=os.environ.get("SNOWSHIFT_SCHEMA") or target.get("schema", ""),
        warehouse=os.environ.get("SNOWSHIFT_WAREHOUSE") or target.get("warehouse", ""),
        stages=tuple(stages),
        root=root,
    )
