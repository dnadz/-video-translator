"""Install / start / import / process / export / uninstall / reinstall on an isolated profile."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from localvideoai.core.paths import install_root


def run(command: list[str], env: dict[str, str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command))
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {command}\n{completed.stdout}\n{completed.stderr}")
    return completed


def wait_gone(path: Path, seconds: float = 30) -> None:
    deadline = time.time() + seconds
    while path.exists() and time.time() < deadline:
        time.sleep(0.5)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def isolated_env(sandbox: Path) -> dict[str, str]:
    env = os.environ.copy()
    local = sandbox / "AppData" / "Local"
    roaming = sandbox / "AppData" / "Roaming"
    local.mkdir(parents=True, exist_ok=True)
    roaming.mkdir(parents=True, exist_ok=True)
    env["LOCALAPPDATA"] = str(local)
    env["APPDATA"] = str(roaming)
    env["USERPROFILE"] = str(sandbox)
    env["LOCALVIDEOAI_SKIP_RECOVERY"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    # Prefer the frozen app over any developer Python on PATH.
    path_parts = []
    for part in env.get("PATH", "").split(os.pathsep):
        lower = part.lower()
        if "python" in lower or "node" in lower or "npm" in lower:
            continue
        path_parts.append(part)
    env["PATH"] = os.pathsep.join(path_parts)
    return env


def main() -> int:
    root = install_root()
    release = root / "release"
    setup = release / "LocalVideoAI_Setup.exe"
    portable = release / "LocalVideoAI_Portable.exe"
    if not setup.is_file() or not portable.is_file():
        raise RuntimeError("先运行 scripts/build_release.py 生成 Setup/Portable EXE")
    sandbox = root / "release" / "phase20_sandbox"
    if sandbox.exists():
        shutil.rmtree(sandbox)
    sandbox.mkdir(parents=True)
    env = isolated_env(sandbox)
    notes: dict[str, object] = {"sandbox": str(sandbox), "steps": []}

    install_dir = sandbox / "install"
    models = sandbox / "models"
    projects = sandbox / "projects"
    cache = sandbox / "cache"
    run(
        [
            str(setup),
            "/SILENT",
            "/NOLAUNCH",
            f"/DIR={install_dir}",
            f"/MODELS={models}",
            f"/PROJECTS={projects}",
            f"/CACHE={cache}",
            "/NODESKTOP",
        ],
        env,
    )
    app = install_dir / "LocalVideoAI.exe"
    paths_file = install_dir / "install_paths.json"
    if not app.is_file():
        raise RuntimeError("安装后没有 LocalVideoAI.exe")
    if not paths_file.is_file():
        raise RuntimeError("安装后没有 install_paths.json")
    mapped = json.loads(paths_file.read_text(encoding="utf-8"))
    notes["steps"].append({"install": True, "paths": mapped})

    check = run([str(app), "--check"], env, cwd=install_dir)
    notes["steps"].append({"check": check.stdout[-400:]})
    smoke = run([str(app), "--release-smoke"], env, cwd=install_dir)
    notes["steps"].append({"smoke": smoke.stdout[-800:]})

    marker_model = models / "keep.bin"
    marker_project = projects / "film.vtproj"
    models.mkdir(parents=True, exist_ok=True)
    projects.mkdir(parents=True, exist_ok=True)
    marker_model.write_bytes(b"model")
    marker_project.write_text("{}", encoding="utf-8")

    uninstall = install_dir / "Uninstall.exe"
    if not uninstall.is_file():
        raise RuntimeError("安装后没有 Uninstall.exe")
    run([str(uninstall), "/SILENT", "/UNINSTALLMODE=program"], env)
    wait_gone(install_dir)
    if not marker_model.is_file() or not marker_project.is_file():
        raise RuntimeError("删除程序时应保留模型和项目")
    notes["steps"].append({"uninstall_program": True, "kept_models": True, "kept_projects": True})

    run(
        [
            str(setup),
            "/SILENT",
            "/NOLAUNCH",
            f"/DIR={install_dir}",
            f"/MODELS={models}",
            f"/PROJECTS={projects}",
            f"/CACHE={cache}",
            "/NODESKTOP",
        ],
        env,
    )
    if not app.is_file():
        raise RuntimeError("重新安装后没有 LocalVideoAI.exe")
    run([str(app), "--check"], env, cwd=install_dir)
    notes["steps"].append({"reinstall": True, "recheck": True})

    run([str(uninstall), "/SILENT", "/UNINSTALLMODE=keep_models"], env)
    wait_gone(install_dir)
    if not marker_model.is_file():
        raise RuntimeError("保留模型卸载后模型丢失")
    if marker_project.exists():
        raise RuntimeError("保留模型卸载后项目应被删除")
    notes["steps"].append({"uninstall_keep_models": True})

    projects.mkdir(parents=True, exist_ok=True)
    marker_project.write_text("{}", encoding="utf-8")
    run(
        [
            str(setup),
            "/SILENT",
            "/NOLAUNCH",
            f"/DIR={install_dir}",
            f"/MODELS={models}",
            f"/PROJECTS={projects}",
            f"/CACHE={cache}",
            "/NODESKTOP",
        ],
        env,
    )
    run([str(uninstall), "/SILENT", "/UNINSTALLMODE=keep_projects"], env)
    wait_gone(install_dir)
    if marker_model.exists():
        raise RuntimeError("保留项目卸载后模型应被删除")
    if not marker_project.is_file():
        raise RuntimeError("保留项目卸载后项目丢失")
    notes["steps"].append({"uninstall_keep_projects": True})

    models.mkdir(parents=True, exist_ok=True)
    marker_model.write_bytes(b"model")
    run(
        [
            str(setup),
            "/SILENT",
            "/NOLAUNCH",
            f"/DIR={install_dir}",
            f"/MODELS={models}",
            f"/PROJECTS={projects}",
            f"/CACHE={cache}",
            "/NODESKTOP",
        ],
        env,
    )
    run([str(uninstall), "/SILENT", "/UNINSTALLMODE=wipe"], env)
    wait_gone(install_dir)
    if marker_model.exists() or marker_project.exists():
        raise RuntimeError("删除全部后仍留有模型或项目")
    notes["steps"].append({"uninstall_wipe": True})

    portable_dir = sandbox / "portable_out"
    run([str(portable), "/SILENT", "/PORTABLE", "/NOLAUNCH", f"/DIR={portable_dir}"], env)
    portable_exe = portable_dir / "LocalVideoAI.exe"
    flag = portable_dir / "portable.flag"
    if not portable_exe.is_file() or not flag.is_file():
        raise RuntimeError("便携版解压后应直接得到 LocalVideoAI.exe 和 portable.flag")
    run([str(portable_exe), "--check"], env, cwd=portable_dir)
    run([str(portable_exe), "--release-smoke"], env, cwd=portable_dir)
    notes["steps"].append({"portable": True, "flag": True})

    report = sandbox / "result.json"
    report.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
