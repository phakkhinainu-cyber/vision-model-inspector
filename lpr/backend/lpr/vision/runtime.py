"""สร้าง ONNX Runtime session โดยเลือก CUDA / DirectML / CPU ให้อัตโนมัติ"""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def available_providers() -> list[str]:
    try:
        import onnxruntime as ort

        return list(ort.get_available_providers())
    except Exception:  # noqa: BLE001
        return []


def pick_providers(device: str = "auto") -> list[str]:
    avail = available_providers()
    order: list[str] = []
    if device in ("auto", "cuda") and "CUDAExecutionProvider" in avail:
        order.append("CUDAExecutionProvider")
    if device in ("auto", "dml") and "DmlExecutionProvider" in avail:
        order.append("DmlExecutionProvider")
    order.append("CPUExecutionProvider")
    return order


def device_label(providers: list[str]) -> str:
    p = providers[0] if providers else "CPUExecutionProvider"
    return {"CUDAExecutionProvider": "GPU (CUDA)", "DmlExecutionProvider": "GPU (DirectML)"}.get(p, "CPU")


def make_session(path: Path, device: str = "auto", threads: int = 0):  # type: ignore[no-untyped-def]
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.log_severity_level = 3
    if threads > 0:
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers = pick_providers(device)
    try:
        sess = ort.InferenceSession(str(path), so, providers=providers)
    except Exception as e:  # noqa: BLE001
        log.warning("โหลดโมเดล %s ด้วย %s ไม่ได้ (%s) ใช้ CPU แทน", path.name, providers, e)
        sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
    log.info("โหลดโมเดล %s ใช้ %s", path.name, sess.get_providers()[0])
    return sess


def default_threads(n_cameras: int) -> int:
    cores = os.cpu_count() or 4
    return max(1, min(4, cores // max(1, n_cameras)))
