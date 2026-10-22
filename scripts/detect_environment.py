from pathlib import Path

from localvideoai.core.paths import install_root
from localvideoai.hardware.hardware_manager import HardwareManager


def main() -> int:
    destination = Path(install_root() / "docs" / "ENVIRONMENT.md")
    path = HardwareManager().write_markdown(destination)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
