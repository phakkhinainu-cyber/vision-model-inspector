"""Qt glue: thread-safe signal bridges and background jobs (model load, Grad-CAM)."""
from __future__ import annotations

import logging
import traceback

from PySide6.QtCore import QObject, QThread, Signal

from ..adapters.base import DeviceUnavailableError, ModelLoadError
from ..adapters.registry import create_adapter
from ..gradcam.ultralytics_gradcam import GradCamError

log = logging.getLogger(__name__)


class SourceBridge(QObject):
    """Converts FrameSource callbacks (any thread) into queued Qt signals."""
    frame = Signal(object)
    status = Signal(str)
    error = Signal(str)
    stopped = Signal()

    def attach(self, src):
        src.on_frame = self.frame.emit
        src.on_status = self.status.emit
        src.on_error = self.error.emit
        src.on_stopped = self.stopped.emit


class InferenceBridge(QObject):
    result = Signal(object, object, str, object)
    error = Signal(str)


class ModelLoadThread(QThread):
    loaded = Signal(object)              # adapter
    failed = Signal(str, str)            # message, kind ("device" | "model" | "crash")

    def __init__(self, path: str, device: str, parent=None):
        super().__init__(parent)
        self.path, self.device = path, device

    def run(self):
        try:
            ad = create_adapter(self.path)
            ad.load(self.path, self.device)
            self.loaded.emit(ad)
        except DeviceUnavailableError as e:
            self.failed.emit(str(e), "device")
        except ModelLoadError as e:
            self.failed.emit(str(e), "model")
        except Exception as e:  # pragma: no cover
            log.error("model load crashed: %s", traceback.format_exc())
            self.failed.emit(f"{type(e).__name__}: {e}", "crash")


class GradCamThread(QThread):
    done = Signal(object, object)        # output, job
    failed = Signal(str, object)

    def __init__(self, engine, worker, job: dict, parent=None):
        super().__init__(parent)
        self.engine, self.worker, self.job = engine, worker, job

    def run(self):
        self.worker.pause("Grad-CAM")
        try:
            out = self.engine.compute(self.job["image"], self.job["det"], self.job["imgsz"],
                                      self.job["layer"], self.job.get("method", "gradcam"))
            self.done.emit(out, self.job)
        except GradCamError as e:
            self.failed.emit(str(e), self.job)
        except Exception as e:
            log.error("Grad-CAM crashed: %s", traceback.format_exc())
            msg = str(e)
            if "out of memory" in msg.lower():
                msg = "หน่วยความจำ GPU ไม่พอสำหรับ Grad-CAM — ลองใช้ CPU หรือลดขนาด input"
            self.failed.emit(f"Grad-CAM ล้มเหลว: {msg}", self.job)
        finally:
            self.worker.resume()
