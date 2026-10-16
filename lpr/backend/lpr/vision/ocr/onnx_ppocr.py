"""PaddleOCR PP-OCRv5 (th_PP-OCRv5_mobile_rec) ที่แปลงเป็น ONNX — รันด้วย ONNX Runtime ได้ทุกเครื่อง

preprocess/decode ตรงกับ PaddleOCR ต้นฉบับ (ตรวจสอบใน CI ด้วยการเทียบผลกับ paddleocr แล้ว)
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from ..runtime import make_session


class OnnxPPOCR:
    name = "PP-OCRv5 th (ONNX)"

    def __init__(self, model_path: Path, dict_path: Path, device: str = "auto", threads: int = 0,
                 max_width: int = 640) -> None:
        self.sess = make_session(model_path, device, threads)
        self.input_name = self.sess.get_inputs()[0].name
        chars = dict_path.read_text("utf-8").split("\n")
        if chars and chars[-1] == "":
            chars = chars[:-1]
        self.table = ["<blank>"] + chars + [" "]
        self.max_width = max_width

    def _prep(self, img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        nw = min(self.max_width, max(16, int(math.ceil(48 * w / max(h, 1)))))
        x = cv2.resize(img, (nw, 48)).astype(np.float32) / 255.0
        return ((x - 0.5) / 0.5).transpose(2, 0, 1)

    def recognize(self, line_images: list[np.ndarray]) -> list[tuple[str, float]]:
        if not line_images:
            return []
        imgs = [self._prep(i if i.ndim == 3 else cv2.cvtColor(i, cv2.COLOR_GRAY2BGR)) for i in line_images]
        wmax = max(i.shape[2] for i in imgs)
        batch = np.zeros((len(imgs), 3, 48, wmax), dtype=np.float32)
        for k, im in enumerate(imgs):
            batch[k, :, :, : im.shape[2]] = im
        prob = self.sess.run(None, {self.input_name: batch})[0]
        out = []
        for p in prob:
            idx = p.argmax(1)
            conf = p.max(1)
            chars, confs, prev = [], [], -1
            for i, c in zip(idx, conf):
                if i != prev and i != 0 and i < len(self.table):
                    chars.append(self.table[i])
                    confs.append(float(c))
                prev = i
            out.append(("".join(chars), float(np.mean(confs)) if confs else 0.0))
        return out
