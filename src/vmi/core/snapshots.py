"""Snapshot management with a bounded cache.

A snapshot is an immutable *copy* of the analysed frame together with the
detections computed on exactly that frame, the model identity and the
settings in force at that moment. Changing the model later never relabels
older snapshots because they carry their own ClassRegistry copy.
"""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .types import DetectionResult


@dataclass
class GradCamRecord:
    det_id: int
    class_id: int
    confidence: float
    box: tuple
    layer_key: str
    layer_name: str
    heatmap: np.ndarray            # float32 0..1 in original image size
    details: dict = field(default_factory=dict)
    method: str = "gradcam"


@dataclass
class Snapshot:
    index: int                     # running number shown in the UI ("ภาพที่ 03")
    image: np.ndarray              # BGR copy
    result: DetectionResult
    class_names: dict              # {id: original name} at capture time
    class_source: str
    display_names: dict            # display names at capture time
    hidden_classes: set
    source_label: str
    gradcam: Optional[GradCamRecord] = None

    @property
    def nbytes(self) -> int:
        n = self.image.nbytes
        if self.gradcam is not None:
            n += self.gradcam.heatmap.nbytes
        return n

    def label(self, class_id: int) -> str:
        cid = int(class_id)
        return self.display_names.get(cid) or self.class_names.get(cid, f"class_{cid}")

    def visible_detections(self):
        return [d for d in self.result.detections if int(d.class_id) not in self.hidden_classes]


class SnapshotStore:
    """Thread-safe ordered store that evicts the oldest snapshots.

    Limits: ``max_items`` and ``max_mb`` (whichever is hit first).
    """

    def __init__(self, max_items: int = 30, max_mb: int = 512):
        self.max_items = max_items
        self.max_mb = max_mb
        self._items: list = []
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        self.evicted_total = 0

    def next_index(self) -> int:
        return next(self._counter)

    def add(self, snap: Snapshot) -> list:
        """Add and return the list of evicted snapshots (oldest first)."""
        with self._lock:
            self._items.append(snap)
            return self._enforce_locked()

    def set_limits(self, max_items: int, max_mb: int) -> list:
        with self._lock:
            self.max_items, self.max_mb = max(1, max_items), max(16, max_mb)
            return self._enforce_locked()

    def _enforce_locked(self) -> list:
        evicted = []
        while len(self._items) > 1 and (
                len(self._items) > self.max_items or self._bytes_locked() > self.max_mb * 1024 * 1024):
            evicted.append(self._items.pop(0))
        self.evicted_total += len(evicted)
        return evicted

    def _bytes_locked(self) -> int:
        return sum(s.nbytes for s in self._items)

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._bytes_locked()

    def remove(self, index: int) -> bool:
        with self._lock:
            for i, s in enumerate(self._items):
                if s.index == index:
                    del self._items[i]
                    return True
        return False

    def clear(self):
        with self._lock:
            self._items.clear()

    def get(self, index: int) -> Optional[Snapshot]:
        with self._lock:
            for s in self._items:
                if s.index == index:
                    return s
        return None

    def all(self) -> list:
        with self._lock:
            return list(self._items)

    def __len__(self):
        with self._lock:
            return len(self._items)
