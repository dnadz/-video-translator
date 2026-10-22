"""Generate Phase 4 external subtitle fixtures."""

from __future__ import annotations

from pathlib import Path

from localvideoai.core.paths import ensure_directory, install_root
from localvideoai.core.types import SubtitleSegment
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import save_subtitle


def _segments() -> list[SubtitleSegment]:
    return [
        SubtitleSegment(1, 0, 1800, speaker="旁白", source_text="你好，世界。", language="zh"),
        SubtitleSegment(2, 1900, 3600, speaker="Host", source_text="Hello, world!", language="en"),
        SubtitleSegment(3, 3700, 5400, speaker="案内", source_text="こんにちは、世界。", language="ja"),
        SubtitleSegment(
            4,
            5500,
            8000,
            source_text="这是双语\nThis is bilingual",
            language="zh-en",
        ),
        SubtitleSegment(
            5,
            8100,
            10000,
            source_text="特殊字符 <> & \"' ♪ 【测试】 🎬",
            language="zh",
        ),
    ]


def main() -> int:
    root = ensure_directory(install_root() / "test_assets" / "subtitles")
    chinese = ensure_directory(root / "中文路径")
    document = SubtitleDocument(segments=_segments(), format_name="srt")
    save_subtitle(document, root / "多语言.srt", "srt")
    save_subtitle(document, root / "多语言.vtt", "vtt")
    save_subtitle(document, root / "多语言.ass", "ass")
    save_subtitle(document, root / "多语言.ssa", "ssa")
    save_subtitle(document, chinese / "中文字幕.srt", "srt")

    thousand: list[SubtitleSegment] = []
    for index in range(1000):
        start = index * 1000
        thousand.append(
            SubtitleSegment(
                id=index + 1,
                start_time=start,
                end_time=start + 800,
                source_text=f"第{index + 1}条 / cue {index + 1} / 字幕{index + 1}",
                language="zh",
            )
        )
    save_subtitle(SubtitleDocument(segments=thousand, format_name="srt"), root / "一千条.srt", "srt")

    abnormal = """garbage header

1
00:00:01,000 --> 00:00:00,400
时间颠倒应跳过

not-a-time --> also-bad
坏块

3
00:00:02,000 --> 00:00:03,500
有效条目

00:00:04,000 --> 00:00:05,000
无序号也应导入
"""
    (root / "异常字幕.srt").write_text(abnormal, encoding="utf-8")
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
