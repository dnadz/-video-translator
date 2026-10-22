"""Print live en→zh outputs for P0 quality sentences. UTF-8 file is the source of truth."""

from __future__ import annotations

from pathlib import Path

from localvideoai.core.types import TranslationRequest
from localvideoai.engines import create_translation_engine
from localvideoai.hardware.hardware_manager import EnvironmentReport
from localvideoai.translation.store import find_translation_model_dir
from localvideoai.translation.tokenizer import load_tokenizer, source_affixes


SENTENCES = (
    "It's a nice day.",
    "It's a nice day",
    "It is a nice day.",
    "The weather is nice today.",
    "Hello.",
    "Thank you.",
    "Good morning.",
    "I love you.",
    "This is a test.",
)


def main() -> int:
    root = find_translation_model_dir("argos-en-zh")
    bos, eos = source_affixes(root) if root else (None, None)
    tokenizer = load_tokenizer(root) if root else None
    report = EnvironmentReport(
        os_caption="probe",
        os_version="10.0.22000",
        os_build="22000",
        os_arch="AMD64",
        python_version="3.12",
        python_executable="python",
        cpu_name="cpu",
        cpu_cores=1,
        cpu_logical=1,
        ram_total_gb=32.0,
        ram_available_gb=16.0,
        disks=[],
        gpus=[],
        tools=[],
        project_root=".",
    )
    engine = create_translation_engine(report)
    lines = [
        f"model={root}",
        f"affixes bos={bos!r} eos={eos!r}",
    ]
    if tokenizer is not None:
        tokens = tokenizer.encode("It's a nice day.")
        lines.append(f"tokens={tokens[:12]}... last={tokens[-1:]}")
    for sentence in SENTENCES:
        result = engine.translate(TranslationRequest(sentence, "en", "zh", device_preference="cpu"))
        lines.append(f"{sentence!r} -> {result.text!r} model={result.model_id}")
    out = Path("logs") / "p0_en_zh_probe.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
