from pathlib import Path

from localvideoai.managers.json_project_manager import JsonProjectManager
from localvideoai.project.schema import PROJECT_EXTENSION


def test_json_project_roundtrip_chinese_paths(tmp_path):
    manager = JsonProjectManager()
    folder = tmp_path / "中文目录" / "测试项目"
    path = manager.create("中文项目名称", folder)
    assert path.suffix == PROJECT_EXTENSION
    assert "中文项目名称" in path.name
    video = folder / "测试视频.mp4"
    video.write_bytes(b"")
    data = manager.load(path)
    data["videos"].append({"path": str(video.resolve()), "name": video.name})
    manager.save(path, data)
    loaded = manager.load(path)
    assert loaded["name"] == "中文项目名称"
    assert loaded["videos"][0]["name"] == "测试视频.mp4"
    text = path.read_text(encoding="utf-8")
    assert "中文项目名称" in text
    assert "测试视频.mp4" in text
    assert loaded["kind"] == "localvideoai-vtproj"
