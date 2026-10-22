"""LocalVideoAI Translator package."""

from importlib.metadata import PackageNotFoundError, version

APP_NAME = "LocalVideoAI"
APP_DISPLAY_NAME = "LocalVideoAI Translator"
APP_ID = "localvideoai"

try:
    __version__ = version("localvideoai")
except PackageNotFoundError:
    __version__ = "0.22.4"

__all__ = ["APP_DISPLAY_NAME", "APP_ID", "APP_NAME", "__version__"]
