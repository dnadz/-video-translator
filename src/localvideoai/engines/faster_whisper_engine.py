from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from localvideoai.audio.chunker import AudioChunk, iter_pcm_chunks
from localvideoai.core.exceptions import MediaError, SpeechError
from localvideoai.core.types import SpeechSegment, SpeechTranscript, SpeechWord
from localvideoai.engines.speech_engine import SpeechEngine
from localvideoai.hardware.hardware_manager import EnvironmentReport, HardwareManager
from localvideoai.managers.log_manager import get_logger
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.speech.cuda_runtime import is_cuda_runtime_error, prepare_cuda_dlls
from localvideoai.speech.language import normalize_speech_language
from localvideoai.speech.persist import save_transcript
from localvideoai.speech.postprocess import fallback_segments, sentences_from_words
from localvideoai.performance.cache import get_model_cache
from localvideoai.performance.policy import policy_from_report
from localvideoai.speech.selector import ModelChoice, select_speech_model
from localvideoai.speech.store import list_local_models, resolve_model_path

ProgressCallback = Callable[[int, int, str], None]
WORD_TIMESTAMP_MAX_DURATION_MS = 15 * 60 * 1000


class FasterWhisperSpeechEngine(SpeechEngine):
    """Local faster-whisper ASR. Processes media as streamed PCM chunks."""

    def __init__(self, report: EnvironmentReport | None = None) -> None:
        self._logger = get_logger("speech")
        self._report = report
        self._analyzer = MediaAnalyzer()
        self._model = None
        self._loaded_choice: ModelChoice | None = None
        os.environ.setdefault("TQDM_DISABLE", "1")

    @property
    def engine_id(self) -> str:
        return "faster-whisper"

    @property
    def display_name(self) -> str:
        return "Faster-Whisper Speech Engine"

    def choose_model(self, device_preference: str = "auto", prefer_gpu: bool = True) -> ModelChoice:
        report = self._report or HardwareManager().detect()
        available = set(list_local_models())
        try:
            return select_speech_model(
                report,
                prefer_gpu=prefer_gpu,
                device_preference=device_preference,
                available=available or None,
            )
        except RuntimeError as exc:
            raise SpeechError(str(exc)) from exc

    def transcribe(self, audio_path: Path, language: str | None = None) -> list[SpeechSegment]:
        return self.transcribe_media(audio_path, language=language).segments

    def transcribe_media(
        self,
        media_path: Path,
        language: str | None = None,
        *,
        device_preference: str = "auto",
        prefer_gpu: bool = True,
        word_timestamps: bool = True,
        save_raw: bool = True,
        raw_path: Path | None = None,
        progress: ProgressCallback | None = None,
        chunk_ms: int = 30_000,
        overlap_ms: int = 800,
        model_id: str | None = None,
        forced_choice: ModelChoice | None = None,
        asr_batch_size: int = 0,
        beam_size: int | None = None,
    ) -> SpeechTranscript:
        source = media_path.expanduser().resolve()
        if not source.is_file():
            raise SpeechError(f"没有可识别的媒体文件：{source}")
        try:
            analysis = self._analyzer.analyze(source)
        except MediaError as exc:
            raise SpeechError(str(exc)) from exc
        duration_ms = analysis.duration_ms
        if duration_ms <= 0:
            raise SpeechError(f"无法识别：媒体时长无效：{source}")
        requested = normalize_speech_language(language)
        policy = policy_from_report(self._report)
        if chunk_ms == 30_000:
            chunk_ms = policy.chunk_ms
        if overlap_ms == 800:
            overlap_ms = policy.overlap_ms
        if forced_choice is not None:
            choice = forced_choice
        else:
            choice = self.choose_model(device_preference=device_preference, prefer_gpu=prefer_gpu)
            if model_id:
                choice = ModelChoice(model_id, choice.device, choice.compute_type, choice.reason + f"；覆盖为 {model_id}")
            elif policy.speech_model_hint == "tiny" and choice.device == "cpu" and not model_id:
                choice = ModelChoice("tiny", choice.device, choice.compute_type, policy.reason)
        if choice.device == "cuda":
            prepare_cuda_dlls()
        model = self._load_model(choice)
        if self._loaded_choice is not None:
            choice = self._loaded_choice
        if progress:
            progress(0, duration_ms, f"已加载模型 {choice.model_id}（{choice.device}/{choice.compute_type}）")
        detected_language = requested
        language_probability = 1.0 if requested else 0.0
        collected: list[SpeechSegment] = []
        warnings: list[str] = []
        use_word_timestamps = bool(word_timestamps)
        word_limit = policy.word_timestamp_max_ms or WORD_TIMESTAMP_MAX_DURATION_MS
        if use_word_timestamps and duration_ms > word_limit:
            use_word_timestamps = False
            warnings.append(f"音频超过 {word_limit // 60000} 分钟，已关闭词级时间戳，保留句子时间戳。")
        speech_beam = 5 if beam_size is None else max(1, int(beam_size))
        parallel_batch = max(0, int(asr_batch_size))
        if choice.device != "cuda":
            parallel_batch = min(parallel_batch, 4)
        if parallel_batch > 1:
            try:
                return self._transcribe_parallel(
                    model,
                    source,
                    duration_ms,
                    detected_language,
                    language_probability,
                    choice,
                    warnings,
                    speech_beam,
                    parallel_batch,
                    use_word_timestamps,
                    save_raw,
                    raw_path,
                    progress,
                )
            except SpeechError:
                raise
            except Exception as exc:
                if not is_cuda_runtime_error(exc):
                    raise SpeechError(f"本地语音识别失败：{exc}") from exc
                self._logger.warning("并行识别失败，改为逐段：%s", exc)
                warnings.append(f"并行识别失败，已改为逐段：{exc}")
        chunks_seen = 0
        last_keep_end = -1
        try:
            for chunk in iter_pcm_chunks(source, duration_ms, chunk_ms=chunk_ms, overlap_ms=overlap_ms):
                chunks_seen += 1
                audio = _pcm_to_float32(chunk.pcm_s16le)
                if audio.size == 0:
                    continue
                segments, info = model.transcribe(
                    audio,
                    language=detected_language,
                    task="transcribe",
                    beam_size=speech_beam,
                    vad_filter=choice.device != "cuda",
                    word_timestamps=use_word_timestamps,
                    condition_on_previous_text=False,
                )
                if detected_language is None:
                    detected_language = normalize_speech_language(getattr(info, "language", None)) or "und"
                    language_probability = float(getattr(info, "language_probability", 0.0) or 0.0)
                chunk_segments = self._convert_chunk(
                    list(segments), chunk, detected_language or "und", use_word_timestamps
                )
                del audio
                for item in chunk_segments:
                    mid = (item.start_ms + item.end_ms) // 2
                    if mid <= last_keep_end:
                        continue
                    collected.append(item)
                    last_keep_end = item.end_ms
                if progress:
                    progress(chunk.end_ms, duration_ms, f"分段识别 {chunk.index + 1}：{chunk.start_ms}-{chunk.end_ms} ms")
        except SpeechError:
            raise
        except Exception as exc:
            cpu_choice = self._cpu_fallback_choice(choice, exc)
            if cpu_choice is not None:
                self._logger.warning("CUDA 推理失败，改用 CPU 继续识别：%s", exc)
                return self.transcribe_media(
                    media_path,
                    language,
                    device_preference="cpu",
                    prefer_gpu=False,
                    word_timestamps=word_timestamps,
                    save_raw=save_raw,
                    raw_path=raw_path,
                    progress=progress,
                    chunk_ms=chunk_ms,
                    overlap_ms=overlap_ms,
                    model_id=model_id,
                    forced_choice=cpu_choice,
                    asr_batch_size=0,
                    beam_size=speech_beam,
                )
            raise SpeechError(f"本地语音识别失败：{exc}") from exc
        if not collected:
            raise SpeechError(f"没有识别到语音内容：{source}")
        transcript = SpeechTranscript(
            segments=collected,
            language=detected_language or "und",
            language_probability=language_probability,
            model_id=choice.model_id,
            device=choice.device,
            compute_type=choice.compute_type,
            source_path=source,
            duration_ms=duration_ms,
            chunk_count=chunks_seen,
            warnings=warnings,
        )
        if save_raw:
            transcript.raw_path = save_transcript(transcript, raw_path)
            self._logger.info("Saved raw transcript %s", transcript.raw_path)
        self._logger.info(
            "Transcribed %s lang=%s model=%s device=%s chunks=%s segments=%s",
            source,
            transcript.language,
            choice.model_id,
            choice.device,
            chunks_seen,
            len(collected),
        )
        return transcript

    def _transcribe_parallel(
        self,
        model,
        source: Path,
        duration_ms: int,
        language: str | None,
        language_probability: float,
        choice: ModelChoice,
        warnings: list[str],
        beam: int,
        batch_size: int,
        use_word_timestamps: bool,
        save_raw: bool,
        raw_path: Path | None,
        progress: ProgressCallback | None,
    ) -> SpeechTranscript:
        """One model, many audio windows at once. This is the GPU-parallel path."""
        from faster_whisper import BatchedInferencePipeline

        if use_word_timestamps:
            warnings.append("并行识别使用句子时间戳。")
        pipeline = BatchedInferencePipeline(model)
        if progress:
            progress(0, duration_ms, f"并行识别：一次 {batch_size} 段")
        segments, info = pipeline.transcribe(
            str(source),
            language=language,
            task="transcribe",
            beam_size=beam,
            batch_size=batch_size,
            word_timestamps=False,
            vad_filter=True,
            without_timestamps=False,
            condition_on_previous_text=False,
        )
        if language is None:
            language = normalize_speech_language(getattr(info, "language", None)) or "und"
            language_probability = float(getattr(info, "language_probability", 0.0) or 0.0)
        collected: list[SpeechSegment] = []
        for item in segments:
            text = (getattr(item, "text", "") or "").strip()
            if not text:
                continue
            start_ms = max(0, int(float(item.start) * 1000))
            end_ms = max(start_ms, int(float(item.end) * 1000))
            collected.append(
                SpeechSegment(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                    confidence=float(item.avg_logprob) if getattr(item, "avg_logprob", None) is not None else None,
                    language=language or "und",
                )
            )
            if progress:
                progress(
                    min(end_ms, duration_ms),
                    duration_ms,
                    f"并行识别，已到 {end_ms // 1000} 秒 / {max(duration_ms, 1) // 1000} 秒",
                )
        if not collected:
            raise SpeechError(f"没有识别到语音内容：{source}")
        transcript = SpeechTranscript(
            segments=collected,
            language=language or "und",
            language_probability=language_probability,
            model_id=choice.model_id,
            device=choice.device,
            compute_type=choice.compute_type,
            source_path=source,
            duration_ms=duration_ms,
            chunk_count=batch_size,
            warnings=warnings,
        )
        if save_raw:
            transcript.raw_path = save_transcript(transcript, raw_path)
        self._logger.info(
            "Parallel transcribed %s lang=%s model=%s device=%s batch=%s segments=%s",
            source,
            transcript.language,
            choice.model_id,
            choice.device,
            batch_size,
            len(collected),
        )
        return transcript

    def transcribe_window(
        self,
        media_path: Path,
        start_ms: int,
        end_ms: int,
        language: str | None = None,
        *,
        device_preference: str = "auto",
        prefer_gpu: bool = True,
        beam_size: int = 2,
        word_timestamps: bool = False,
        accurate_seek: bool = False,
        model_id: str | None = None,
        forced_choice: ModelChoice | None = None,
    ) -> list[SpeechSegment]:
        """Recognize one local time window. Empty audio returns []. Does not upload."""
        from localvideoai.audio.window import extract_pcm_window

        source = media_path.expanduser().resolve()
        if not source.is_file():
            raise SpeechError(f"没有可识别的媒体文件：{source}")
        requested = normalize_speech_language(language)
        if forced_choice is not None:
            choice = forced_choice
        else:
            choice = self.choose_model(device_preference=device_preference, prefer_gpu=prefer_gpu)
            if model_id:
                choice = ModelChoice(model_id, choice.device, choice.compute_type, choice.reason + f"；覆盖为 {model_id}")
        if choice.device == "cuda":
            prepare_cuda_dlls()
        model = self._load_model(choice)
        if self._loaded_choice is not None:
            choice = self._loaded_choice
        try:
            chunk = extract_pcm_window(source, start_ms, end_ms, accurate_seek=accurate_seek)
        except MediaError as exc:
            raise SpeechError(str(exc)) from exc
        audio = _pcm_to_float32(chunk.pcm_s16le)
        if audio.size == 0:
            return []
        try:
            segments, info = model.transcribe(
                audio,
                language=requested,
                task="transcribe",
                beam_size=max(1, int(beam_size)),
                vad_filter=choice.device != "cuda",
                word_timestamps=bool(word_timestamps),
                condition_on_previous_text=False,
            )
        except Exception as exc:
            cpu_choice = self._cpu_fallback_choice(choice, exc)
            if cpu_choice is not None:
                self._logger.warning("CUDA 实时识别失败，改用 CPU：%s", exc)
                return self.transcribe_window(
                    media_path,
                    start_ms,
                    end_ms,
                    language,
                    device_preference="cpu",
                    prefer_gpu=False,
                    beam_size=beam_size,
                    word_timestamps=word_timestamps,
                    accurate_seek=accurate_seek,
                    model_id=model_id,
                    forced_choice=cpu_choice,
                )
            raise SpeechError(f"实时窗口识别失败：{exc}") from exc
        detected = requested or normalize_speech_language(getattr(info, "language", None)) or "und"
        converted = self._convert_chunk(list(segments), chunk, detected, bool(word_timestamps))
        del audio
        return converted

    def _load_model(self, choice: ModelChoice):
        if (
            self._model is not None
            and self._loaded_choice is not None
            and self._loaded_choice.model_id == choice.model_id
            and self._loaded_choice.device == choice.device
            and self._loaded_choice.compute_type == choice.compute_type
        ):
            return self._model
        cache = get_model_cache()
        cache_key = ("speech", choice.model_id, choice.device, choice.compute_type)
        cached = cache.get(cache_key)
        if cached is not None:
            self._model = cached
            self._loaded_choice = choice
            return self._model
        path = resolve_model_path(choice.model_id)
        if choice.device == "cuda":
            prepare_cuda_dlls()
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SpeechError("未安装 faster-whisper。请在项目虚拟环境中安装依赖。") from exc
        try:
            self._model = WhisperModel(
                str(path),
                device=choice.device,
                compute_type=choice.compute_type,
                local_files_only=True,
            )
        except Exception as exc:
            if choice.device == "cuda":
                self._logger.warning("CUDA 加载失败，回退 CPU：%s", exc)
                cpu_choice = ModelChoice(choice.model_id, "cpu", "int8", f"{choice.reason}；CUDA 失败回退 CPU")
                cpu_key = ("speech", cpu_choice.model_id, "cpu", "int8")
                cached_cpu = cache.get(cpu_key)
                if cached_cpu is not None:
                    self._model = cached_cpu
                    self._loaded_choice = cpu_choice
                    return self._model
                try:
                    self._model = WhisperModel(str(path), device="cpu", compute_type="int8", local_files_only=True)
                except Exception as cpu_exc:
                    raise SpeechError(f"无法加载本地语音模型 {choice.model_id}：{cpu_exc}") from cpu_exc
                self._loaded_choice = cpu_choice
                cache.put(cpu_key, self._model)
                return self._model
            raise SpeechError(f"无法加载本地语音模型 {choice.model_id}：{exc}") from exc
        self._loaded_choice = choice
        cache.put(cache_key, self._model)
        return self._model

    def release(self) -> None:
        """Drop the loaded speech model so translation can use the GPU."""
        loaded = self._loaded_choice
        if loaded is not None:
            self._unload_choice(loaded)
        self._model = None
        self._loaded_choice = None

    def _cpu_fallback_choice(self, choice: ModelChoice, exc: BaseException) -> ModelChoice | None:
        if choice.device != "cuda" or not is_cuda_runtime_error(exc):
            return None
        self._unload_choice(choice)
        return ModelChoice(choice.model_id, "cpu", "int8", f"{choice.reason}；CUDA 推理失败回退 CPU")

    def _unload_choice(self, choice: ModelChoice) -> None:
        get_model_cache().discard(("speech", choice.model_id, choice.device, choice.compute_type))
        loaded = self._loaded_choice
        if (
            loaded is not None
            and loaded.model_id == choice.model_id
            and loaded.device == choice.device
            and loaded.compute_type == choice.compute_type
        ):
            self._model = None
            self._loaded_choice = None

    def _convert_chunk(
        self,
        raw_segments: list,
        chunk: AudioChunk,
        language: str,
        word_timestamps: bool,
    ) -> list[SpeechSegment]:
        words: list[SpeechWord] = []
        fallback: list[SpeechSegment] = []
        for raw in raw_segments:
            start = chunk.start_ms + int(float(raw.start or 0) * 1000)
            end = chunk.start_ms + int(float(raw.end or 0) * 1000)
            if end < start:
                end = start
            text = (raw.text or "").strip()
            confidence = float(raw.avg_logprob) if getattr(raw, "avg_logprob", None) is not None else None
            raw_words = list(getattr(raw, "words", None) or [])
            if word_timestamps and raw_words:
                for item in raw_words:
                    token = (item.word or "").strip()
                    if not token:
                        continue
                    words.append(
                        SpeechWord(
                            start_ms=chunk.start_ms + int(float(item.start or 0) * 1000),
                            end_ms=chunk.start_ms + int(float(item.end or 0) * 1000),
                            text=token,
                            confidence=float(item.probability) if item.probability is not None else None,
                        )
                    )
            elif text:
                fallback.extend(fallback_segments(start, end, text, language, confidence))
        if words:
            return sentences_from_words(words, language)
        return fallback


def _pcm_to_float32(pcm: bytes):
    import numpy as np

    if not pcm:
        return np.zeros(0, dtype=np.float32)
    data = np.frombuffer(pcm, dtype=np.int16)
    return (data.astype(np.float32) / 32768.0).copy()
