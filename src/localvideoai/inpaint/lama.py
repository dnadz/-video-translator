"""Local LaMa ONNX inpainting. UI must not import this module's runtime."""

from __future__ import annotations

import numpy as np

from localvideoai.inpaint.store import is_lama_ready, lama_model_path

_SESSION = None
_INPUTS: tuple[str, str] | None = None


def lama_available() -> bool:
    return is_lama_ready()


def inpaint_lama(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if mask.max() == 0:
        return rgb
    session, image_name, mask_name = _session()
    ys, xs = np.where(mask > 0)
    y0, y1 = max(0, int(ys.min()) - 16), min(rgb.shape[0], int(ys.max()) + 17)
    x0, x1 = max(0, int(xs.min()) - 16), min(rgb.shape[1], int(xs.max()) + 17)
    crop = rgb[y0:y1, x0:x1]
    crop_mask = mask[y0:y1, x0:x1]
    image = _to_square(crop, 512)
    hole = _to_square(crop_mask, 512, is_mask=True)
    image_n = (image.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
    mask_n = (hole.astype(np.float32) / 255.0)[None, None]
    if mask_n.max() < 0.01:
        return rgb
    outputs = session.run(None, {image_name: image_n, mask_name: mask_n})
    pred = np.asarray(outputs[0])
    if pred.ndim == 4:
        pred = pred[0]
    if pred.shape[0] in {1, 3}:
        pred = pred.transpose(1, 2, 0)
    pred = np.clip(pred * 255.0 if pred.max() <= 1.5 else pred, 0, 255).astype(np.uint8)
    if pred.shape[2] == 1:
        pred = np.repeat(pred, 3, axis=2)
    restored = _from_square(pred, crop.shape[0], crop.shape[1])
    out = rgb.copy()
    out[y0:y1, x0:x1] = restored
    return out


def _session():
    global _SESSION, _INPUTS
    if _SESSION is not None and _INPUTS is not None:
        return _SESSION, _INPUTS[0], _INPUTS[1]
    import onnxruntime as ort

    path = lama_model_path()
    providers = ["CPUExecutionProvider"]
    available = ort.get_available_providers()
    if "CUDAExecutionProvider" in available:
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    _SESSION = ort.InferenceSession(str(path), providers=providers)
    names = [item.name for item in _SESSION.get_inputs()]
    image_name = next((name for name in names if "mask" not in name.lower()), names[0])
    mask_name = next((name for name in names if name != image_name), names[-1])
    _INPUTS = (image_name, mask_name)
    return _SESSION, image_name, mask_name


def _to_square(array: np.ndarray, size: int, *, is_mask: bool = False) -> np.ndarray:
    import cv2

    if array.ndim == 2:
        resized = cv2.resize(array, (size, size), interpolation=cv2.INTER_NEAREST if is_mask else cv2.INTER_LINEAR)
        return resized
    return cv2.resize(array, (size, size), interpolation=cv2.INTER_LINEAR)


def _from_square(array: np.ndarray, height: int, width: int) -> np.ndarray:
    import cv2

    return cv2.resize(array, (width, height), interpolation=cv2.INTER_LINEAR)
