"""สร้าง ONNX Runtime session โดยเลือก CUDA / DirectML / CPU ให้อัตโนมัติ

- รุ่นปกติใช้ onnxruntime (CPU) — ใช้ได้ทุกเครื่อง
- รุ่น GPU บน Windows ใช้ onnxruntime-directml: ใช้การ์ดจอได้ทุกยี่ห้อ (NVIDIA / AMD / Intel) ที่รองรับ DirectX 12
- รันจากซอร์สพร้อม onnxruntime-gpu (CUDA 12 + cuDNN 9) ก็ใช้ได้ (โหลด DLL ของ NVIDIA ให้อัตโนมัติ)
ถ้าโหลดหรือทดลองรันบน GPU ไม่ผ่าน จะกลับไปใช้ CPU เสมอ
"""
from __future__ import annotations

import functools
import logging
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

_GPU_PROVIDERS = ("CUDAExecutionProvider", "DmlExecutionProvider")


def available_providers() -> list[str]:
    try:
        import onnxruntime as ort

        return list(ort.get_available_providers())
    except Exception:  # noqa: BLE001
        return []


@functools.lru_cache(maxsize=1)
def gpu_adapters() -> tuple[dict[str, Any], ...]:
    """การ์ดจอจริงในเครื่อง (Windows, ผ่าน DXGI) ไม่นับตัวจำลองของ Microsoft เช่น Basic Render Driver"""
    if sys.platform != "win32":
        return ()
    try:
        return tuple(_dxgi_adapters())
    except Exception as e:  # noqa: BLE001
        log.debug("อ่านรายชื่อการ์ดจอไม่ได้: %s", e)
        return ()


def _dxgi_adapters() -> list[dict[str, Any]]:
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class DESC1(ctypes.Structure):
        _fields_ = [("Description", ctypes.c_wchar * 128), ("VendorId", ctypes.c_uint), ("DeviceId", ctypes.c_uint),
                    ("SubSysId", ctypes.c_uint), ("Revision", ctypes.c_uint),
                    ("DedicatedVideoMemory", ctypes.c_size_t), ("DedicatedSystemMemory", ctypes.c_size_t),
                    ("SharedSystemMemory", ctypes.c_size_t), ("AdapterLuid", LUID), ("Flags", ctypes.c_uint)]

    def method(obj: ctypes.c_void_p, index: int, *argtypes: Any) -> Any:
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])

    iid = GUID(0x770AAE78, 0xF26F, 0x4DBA, (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
    factory = ctypes.c_void_p()
    if ctypes.WinDLL("dxgi").CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory)) != 0 or not factory:
        return []
    out: list[dict[str, Any]] = []
    try:
        enum = method(factory, 12, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))  # IDXGIFactory1::EnumAdapters1
        i = 0
        while i < 16:
            adapter = ctypes.c_void_p()
            if enum(factory, i, ctypes.byref(adapter)) != 0 or not adapter:
                break
            try:
                d = DESC1()
                if method(adapter, 10, ctypes.POINTER(DESC1))(adapter, ctypes.byref(d)) == 0:  # GetDesc1
                    software = bool(d.Flags & 2) or d.VendorId == 0x1414  # 0x1414 = Microsoft (WARP/Hyper-V/RDP)
                    if not software:
                        out.append({"index": i, "name": d.Description, "vendor": f"{d.VendorId:04x}",
                                    "vram_mb": int(d.DedicatedVideoMemory // (1024 * 1024))})
            finally:
                method(adapter, 2)(adapter)  # Release
            i += 1
    finally:
        method(factory, 2)(factory)
    return out


def best_adapter() -> dict[str, Any] | None:
    """การ์ดจอที่มีหน่วยความจำของตัวเองมากที่สุด (เครื่องที่มีทั้งการ์ดในตัวและการ์ดแยก จะได้การ์ดแยก)"""
    gpus = gpu_adapters()
    return max(gpus, key=lambda g: g["vram_mb"]) if gpus else None


def pick_providers(device: str = "auto") -> list[Any]:
    """ลำดับ provider ที่จะลอง: auto = CUDA → DirectML (เมื่อมีการ์ดจอจริง) → CPU"""
    avail = available_providers()
    order: list[Any] = []
    if device in ("auto", "cuda") and "CUDAExecutionProvider" in avail:
        order.append("CUDAExecutionProvider")
    if "DmlExecutionProvider" in avail and (device == "dml" or (device == "auto" and best_adapter() is not None)):
        g = best_adapter()
        order.append(("DmlExecutionProvider", {"device_id": g["index"]}) if g else "DmlExecutionProvider")
    order.append("CPUExecutionProvider")
    return order


def provider_name(p: Any) -> str:
    return p[0] if isinstance(p, tuple) else str(p)


def device_label(providers: list[Any]) -> str:
    p = provider_name(providers[0]) if providers else "CPUExecutionProvider"
    if p == "DmlExecutionProvider":
        g = best_adapter()
        return f"GPU (DirectML: {g['name']})" if g else "GPU (DirectML)"
    return {"CUDAExecutionProvider": "GPU (CUDA)"}.get(p, "CPU")


_cuda_preloaded = False


def _preload_cuda() -> None:
    """onnxruntime-gpu ≥1.21: โหลด DLL ของ CUDA/cuDNN จากแพ็กเกจ nvidia-* หรือโฟลเดอร์ nvidia ข้างโปรแกรม"""
    global _cuda_preloaded
    if _cuda_preloaded:
        return
    _cuda_preloaded = True
    try:
        import onnxruntime as ort

        if not hasattr(ort, "preload_dlls"):
            return
        from ..config import app_dir

        local = app_dir() / "nvidia"
        ort.preload_dlls(directory=str(local) if local.is_dir() else None)
    except Exception as e:  # noqa: BLE001
        log.warning("โหลดไลบรารี CUDA ไม่สำเร็จ (%s) จะลองใช้ตัวอื่นแทน", e)


def _dummy_feed(sess: Any) -> dict[str, np.ndarray]:
    feed: dict[str, np.ndarray] = {}
    for inp in sess.get_inputs():
        shape = [d if isinstance(d, int) and d > 0 else (1 if i == 0 else 64) for i, d in enumerate(inp.shape)]
        dtype = np.float16 if "float16" in inp.type else np.float32
        feed[inp.name] = np.zeros(shape, dtype=dtype)
    return feed


def make_session(path: Path, device: str = "auto", threads: int = 0):  # type: ignore[no-untyped-def]
    import onnxruntime as ort

    def options(gpu: str | None) -> Any:
        so = ort.SessionOptions()
        so.log_severity_level = 3
        if threads > 0:
            so.intra_op_num_threads = threads
            so.inter_op_num_threads = 1
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        if gpu == "DmlExecutionProvider":  # DirectML ไม่รองรับ memory pattern / การรันแบบขนาน
            so.enable_mem_pattern = False
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        return so

    providers = pick_providers(device)
    gpu = provider_name(providers[0]) if provider_name(providers[0]) in _GPU_PROVIDERS else None
    if gpu == "CUDAExecutionProvider":
        _preload_cuda()
    sess = None
    if gpu:
        try:
            sess = ort.InferenceSession(str(path), options(gpu), providers=providers)
            if sess.get_providers()[0] in _GPU_PROVIDERS:
                sess.run(None, _dummy_feed(sess))  # ทดลองรัน 1 ครั้ง ถ้าการ์ด/ไดรเวอร์มีปัญหาจะได้รู้ตั้งแต่ตอนนี้
        except Exception as e:  # noqa: BLE001
            log.warning("ใช้ %s กับโมเดล %s ไม่ได้ (%s) ใช้ CPU แทน", gpu, path.name, e)
            sess = None
    if sess is None:
        sess = ort.InferenceSession(str(path), options(None), providers=["CPUExecutionProvider"])
    log.info("โหลดโมเดล %s ใช้ %s", path.name, device_label(sess.get_providers()))
    return sess


def probe(path: Path, device: str) -> dict[str, Any]:
    """ทดสอบว่าโมเดลรันบนอุปกรณ์ที่เลือกได้จริงไหม (ใช้ใน selftest)"""
    import time

    t0 = time.time()
    try:
        sess = make_session(path, device)
        feed = _dummy_feed(sess)
        sess.run(None, feed)
        t1 = time.time()
        sess.run(None, feed)
        return {"provider": sess.get_providers()[0], "load_s": round(t1 - t0, 2),
                "run_ms": round((time.time() - t1) * 1000, 1)}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def default_threads(n_cameras: int) -> int:
    cores = os.cpu_count() or 4
    return max(1, min(4, cores // max(1, n_cameras)))
