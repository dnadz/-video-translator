import ast
import inspect

from localvideoai.core.paths import install_root
from localvideoai.engines import ENGINE_TYPES
from localvideoai.engines.base import BaseEngine
from localvideoai.managers.context_manager import ContextManager
from localvideoai.managers.model_manager import ModelManager
from localvideoai.managers.preset_manager import PresetManager
from localvideoai.managers.project_manager import ProjectManager
from localvideoai.managers.task_manager import TaskManager

FORBIDDEN_UI_IMPORTS = {
    "faster_whisper",
    "ctranslate2",
    "openai",
    "anthropic",
    "paddleocr",
    "rapidocr",
    "whisper",
    "torch",
    "onnxruntime",
}


def test_engine_interfaces_are_abstract():
    assert inspect.isabstract(BaseEngine)
    for engine in ENGINE_TYPES:
        assert inspect.isabstract(engine)
        assert issubclass(engine, BaseEngine)


def test_manager_interfaces_are_abstract():
    for cls in (ProjectManager, TaskManager, ModelManager, PresetManager, ContextManager):
        assert inspect.isabstract(cls)


def test_ui_does_not_import_ai_backends():
    ui_dir = install_root() / "src" / "localvideoai" / "ui"
    offenders: list[str] = []
    for path in ui_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in FORBIDDEN_UI_IMPORTS:
                    offenders.append(f"{path.name} imports {name}")
    assert offenders == []
