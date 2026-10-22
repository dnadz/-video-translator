from __future__ import annotations

from localvideoai.core.types import TranslationRequest
from localvideoai.engines import create_translation_engine
from localvideoai.translation.store import find_translation_model_dir
from localvideoai.translation.tokenizer import load_tokenizer, source_affixes
from localvideoai.hardware.hardware_manager import EnvironmentReport


def _report() -> EnvironmentReport:
    return EnvironmentReport(
        os_caption="Windows 11",
        os_version="10.0.22000",
        os_build="22000",
        os_arch="AMD64",
        python_version="3.12.13",
        python_executable="python",
        cpu_name="probe",
        cpu_cores=6,
        cpu_logical=12,
        ram_total_gb=32.0,
        ram_available_gb=16.0,
        disks=[],
        gpus=[],
        tools=[],
        project_root=".",
    )


def main() -> None:
    root = find_translation_model_dir("argos-en-zh")
    print("root", root)
    print("affixes", source_affixes(root))
    tok = load_tokenizer(root)
    samples = [
        "It's a nice day.",
        "It is a nice day.",
        "It's a nice day",
        "What a nice day.",
        "The weather is nice today.",
        "Hello.",
        "Good morning.",
        "I love you.",
        "How are you?",
        "Thank you very much.",
        "I don't know.",
        "I'm fine.",
    ]
    for text in samples:
        tokens = tok.encode(text)
        print("TOK", text, tokens[:10], "tail", tokens[-3:])
    engine = create_translation_engine(_report())
    for text in samples:
        result = engine.translate(TranslationRequest(text, "en", "zh", device_preference="cpu"))
        print("TR", text, "=>", result.text)


if __name__ == "__main__":
    main()
