"""Remove the program and optionally user data. Never uploads anything."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from localvideoai.core.paths import (
    cache_dir,
    install_root,
    load_install_paths,
    managed_models_dir,
    projects_dir,
    user_data_dir,
)

UNINSTALL_MODES = ("program", "keep_models", "keep_projects", "wipe")


@dataclass
class UninstallPlan:
    mode: str
    remove_program: bool
    remove_models: bool
    remove_projects: bool
    remove_cache: bool
    remove_user_data: bool
    targets: list[Path] = field(default_factory=list)
    kept: list[Path] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "remove_program": self.remove_program,
            "remove_models": self.remove_models,
            "remove_projects": self.remove_projects,
            "remove_cache": self.remove_cache,
            "remove_user_data": self.remove_user_data,
            "targets": [str(path) for path in self.targets],
            "kept": [str(path) for path in self.kept],
        }


def normalize_mode(mode: str) -> str:
    key = (mode or "program").strip().lower()
    aliases = {
        "delete_program": "program",
        "keep_user": "program",
        "keep-models": "keep_models",
        "keep-projects": "keep_projects",
        "delete_all": "wipe",
        "all": "wipe",
    }
    key = aliases.get(key, key)
    if key not in UNINSTALL_MODES:
        raise ValueError(f"未知卸载方式：{mode}")
    return key


def plan_uninstall(mode: str = "program") -> UninstallPlan:
    chosen = normalize_mode(mode)
    mapped = load_install_paths()
    program = install_root()
    models = Path(mapped["models_dir"]).expanduser().resolve() if mapped.get("models_dir") else managed_models_dir()
    projects = Path(mapped["projects_dir"]).expanduser().resolve() if mapped.get("projects_dir") else projects_dir()
    cache = Path(mapped["cache_dir"]).expanduser().resolve() if mapped.get("cache_dir") else cache_dir()
    data = Path(mapped["data_dir"]).expanduser().resolve() if mapped.get("data_dir") else user_data_dir()
    remove_models = chosen in {"keep_projects", "wipe"}
    remove_projects = chosen in {"keep_models", "wipe"}
    remove_cache = chosen != "program"
    remove_user_data = chosen == "wipe"
    plan = UninstallPlan(
        mode=chosen,
        remove_program=True,
        remove_models=remove_models,
        remove_projects=remove_projects,
        remove_cache=remove_cache,
        remove_user_data=remove_user_data,
    )
    if remove_models:
        plan.targets.append(models)
    else:
        plan.kept.append(models)
    if remove_projects:
        plan.targets.append(projects)
    else:
        plan.kept.append(projects)
    if remove_cache:
        plan.targets.append(cache)
    if remove_user_data:
        plan.targets.append(data)
    else:
        plan.kept.append(data)
    # Program directory is removed by the Setup uninstaller; the portable helper deletes it last.
    return plan


def run_uninstall(mode: str = "program", *, include_program: bool = False) -> UninstallPlan:
    plan = plan_uninstall(mode)
    for target in plan.targets:
        _remove_tree(target)
    if include_program:
        _remove_tree(install_root(), keep_names={"uninstall_choice.json"})
    return plan


def write_choice(mode: str, destination: Path | None = None) -> Path:
    plan = plan_uninstall(mode)
    path = destination or (install_root() / "uninstall_choice.json")
    path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _remove_tree(path: Path, keep_names: set[str] | None = None) -> None:
    if not path.exists():
        return
    if path.is_file():
        path.unlink()
        return
    if keep_names:
        for child in path.iterdir():
            if child.name in keep_names:
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass
        return
    shutil.rmtree(path, ignore_errors=True)
