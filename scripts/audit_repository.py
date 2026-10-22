"""Check publish candidates without printing any secret values."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DENIED = {"LocalVideoAI", "release", "dist", "build", "vendor", "models", "data", "logs", "test_assets", ".venv"}
SECRET = re.compile(r"(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")


def main():
    result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            cwd=ROOT, capture_output=True, check=True)
    paths = sorted(set(p for p in result.stdout.decode("utf-8").split("\0") if p))
    problems = []
    for name in paths:
        path = ROOT / name
        if not path.is_file():
            continue
        if path.relative_to(ROOT).parts[0] in DENIED or path.name.startswith(".env"):
            problems.append(f"excluded runtime/private path: {name}")
        if path.stat().st_size > 10 * 1024 * 1024:
            problems.append(f"file exceeds 10 MiB: {name}")
            continue
        if SECRET.search(path.read_text(encoding="utf-8", errors="replace")):
            problems.append(f"possible credential in: {name}")
    print(f"Checked {len(paths)} publish candidate files.")
    for message in problems:
        print(message)
    print("FAILED" if problems else "PASS (heuristic check; not a guarantee of no secrets)")
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
