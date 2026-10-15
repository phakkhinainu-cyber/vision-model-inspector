"""Class metadata: where class names come from, user mappings and display names.

Priority used by adapters (spec §5):
  1. metadata embedded in the model (e.g. ``model.names`` for Ultralytics)
  2. ONNX metadata (``names`` custom metadata written by Ultralytics export)
  3. a mapping file the user picks (data.yaml / classes.txt / JSON)
  4. generated ``class_0``, ``class_1`` … with an explicit "names not available" flag

Nothing here guesses names from images or file names, and YAML is read with
``yaml.safe_load`` only. The Python-literal metadata in ONNX files is parsed
with ``ast.literal_eval`` (literals only, never ``eval``).
"""
from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import yaml

SOURCE_MODEL = "model"            # embedded in .pt (model.names)
SOURCE_ONNX = "onnx-metadata"
SOURCE_FILE = "user-file"
SOURCE_GENERATED = "generated"

SOURCE_LABELS_TH = {
    SOURCE_MODEL: "metadata ในโมเดล (model.names)",
    SOURCE_ONNX: "metadata ในไฟล์ ONNX",
    SOURCE_FILE: "ไฟล์ mapping ที่ผู้ใช้เลือก",
    SOURCE_GENERATED: "สร้างอัตโนมัติ (ยังไม่มีชื่อคลาส)",
}

_GENERIC_RE = re.compile(r"^(class[_ ]?)?\d+$", re.IGNORECASE)


class ClassMappingError(ValueError):
    """Raised when a mapping file is broken or contradicts the model."""


@dataclass
class ClassRegistry:
    names: dict                       # {class_id: original name}
    source: str
    count_verified: bool = True       # True if count was checked against model output
    notes: list = field(default_factory=list)
    source_detail: str = ""           # e.g. file path of imported mapping

    @property
    def count(self) -> int:
        return len(self.names)

    def name(self, class_id: int) -> str:
        return self.names.get(int(class_id), f"class_{int(class_id)}")

    @property
    def names_available(self) -> bool:
        return self.source != SOURCE_GENERATED

    def looks_generic(self) -> bool:
        """True when every name is just a number / ``classN`` (e.g. a dataset without names)."""
        return bool(self.names) and all(_GENERIC_RE.match(str(n).strip()) for n in self.names.values())

    def to_list(self) -> list:
        return [{"class_id": k, "name": v} for k, v in sorted(self.names.items())]

    @staticmethod
    def generated(nc: int, verified: bool) -> "ClassRegistry":
        reg = ClassRegistry({i: f"class_{i}" for i in range(nc)}, SOURCE_GENERATED, verified)
        reg.notes.append("ไม่พบชื่อคลาสในโมเดล — ใช้ class_0, class_1 … ตามรหัสที่ตรวจได้ "
                         "สามารถนำเข้า data.yaml / classes.txt / JSON ได้ที่หน้าจัดการคลาส")
        return reg


# ---------------------------------------------------------------- normalisation
def normalize_names(obj) -> dict:
    """Accept list / dict / {'names': ...} and return {int id: str name}.

    Rejects non-contiguous or negative ids, duplicate ids and empty names.
    """
    if isinstance(obj, dict) and "names" in obj and not _all_int_keys(obj):
        obj = obj["names"]
    if isinstance(obj, (list, tuple)):
        names = {i: str(n) for i, n in enumerate(obj)}
    elif isinstance(obj, dict):
        names = {}
        for k, v in obj.items():
            try:
                kid = int(k)
            except (TypeError, ValueError):
                raise ClassMappingError(f"รหัสคลาส '{k}' ไม่ใช่ตัวเลข")
            if kid in names:
                raise ClassMappingError(f"รหัสคลาส {kid} ซ้ำ")
            names[kid] = str(v)
    else:
        raise ClassMappingError("รูปแบบรายชื่อคลาสไม่ถูกต้อง (ต้องเป็น list หรือ dict)")
    if not names:
        raise ClassMappingError("ไม่พบรายชื่อคลาสในไฟล์")
    ids = sorted(names)
    if ids[0] != 0 or ids != list(range(len(ids))):
        raise ClassMappingError("รหัสคลาสต้องเริ่มจาก 0 และต่อเนื่องกัน (0, 1, 2, …) "
                                f"แต่พบ {ids[:10]}{'…' if len(ids) > 10 else ''}")
    for k, v in names.items():
        if not str(v).strip():
            raise ClassMappingError(f"ชื่อคลาสของรหัส {k} ว่างเปล่า")
    return {k: names[k].strip() for k in ids}


def _all_int_keys(d: dict) -> bool:
    try:
        return all(isinstance(k, int) or str(k).lstrip("-").isdigit() for k in d)
    except Exception:
        return False


def parse_literal_names(text: str) -> dict:
    """Parse ``"{0: 'person', 1: 'car'}"`` (Ultralytics ONNX metadata) safely."""
    try:
        obj = ast.literal_eval(text)
    except (ValueError, SyntaxError) as e:
        raise ClassMappingError(f"อ่าน metadata ชื่อคลาสไม่ได้: {e}") from None
    return normalize_names(obj)


def load_mapping_file(path: str) -> dict:
    """Load class names from data.yaml / *.yaml, classes.txt or *.json."""
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except UnicodeDecodeError:
        raise ClassMappingError("ไฟล์ต้องเข้ารหัส UTF-8") from None
    except OSError as e:
        raise ClassMappingError(f"เปิดไฟล์ไม่ได้: {e}") from None

    if ext in (".yaml", ".yml"):
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ClassMappingError(f"ไฟล์ YAML เสีย: {e}") from None
        if not isinstance(data, dict) or "names" not in data:
            raise ClassMappingError("ไม่พบคีย์ 'names' ในไฟล์ YAML")
        names = normalize_names(data["names"])
        if "nc" in data:
            try:
                nc = int(data["nc"])
            except (TypeError, ValueError):
                raise ClassMappingError("ค่า nc ในไฟล์ YAML ไม่ใช่ตัวเลข") from None
            if nc != len(names):
                raise ClassMappingError(f"ไฟล์ YAML ขัดกันเอง: nc={nc} แต่มีชื่อ {len(names)} รายการ")
        return names
    if ext == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ClassMappingError(f"ไฟล์ JSON เสีย: {e}") from None
        return normalize_names(data)
    if ext in (".txt", ".names", ""):
        # one class per line; line 1 = class 0. Blank lines are not allowed in the middle
        lines = text.splitlines()
        while lines and not lines[-1].strip():
            lines.pop()
        if any(not ln.strip() for ln in lines):
            raise ClassMappingError("classes.txt มีบรรทัดว่างระหว่างรายชื่อ — ลำดับบรรทัดคือรหัสคลาส "
                                    "จึงห้ามมีบรรทัดว่างคั่น")
        return normalize_names([ln.strip() for ln in lines])
    raise ClassMappingError(f"ไม่รองรับไฟล์นามสกุล {ext} (ใช้ .yaml, .txt หรือ .json)")


def compare_mapping(current: dict, imported: dict, expected_count: Optional[int]) -> list:
    """Validate an imported mapping against the model. Raises on hard conflicts.

    Returns a list of (class_id, current_name, imported_name) differences so the
    UI can ask the user to confirm explicitly (never silently replaced).
    """
    if expected_count is not None and len(imported) != expected_count:
        raise ClassMappingError(
            f"จำนวนคลาสไม่ตรงกัน: โมเดลมี {expected_count} คลาส แต่ไฟล์มี {len(imported)} คลาส "
            "— ชื่อที่นำเข้าต้องตรงกับลำดับตอนฝึกโมเดล")
    diffs = []
    for k in sorted(set(current) | set(imported)):
        a, b = current.get(k), imported.get(k)
        if a != b:
            diffs.append((k, a, b))
    return diffs


# ---------------------------------------------------------------- display names
class DisplayNameStore:
    """User display names + visibility filter, stored outside the model file.

    Keyed by model SHA-256 and class_id, so a renamed/moved file keeps its
    labels and two different models never share labels.
    """

    def __init__(self, path: str):
        self.path = path
        self._data = {}
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def _entry(self, model_hash: str) -> dict:
        return self._data.setdefault(model_hash, {"display": {}, "hidden": [], "mapping": None})

    def display_names(self, model_hash: str) -> dict:
        d = self._data.get(model_hash, {}).get("display", {})
        return {int(k): v for k, v in d.items()}

    def set_display_names(self, model_hash: str, names: dict):
        self._entry(model_hash)["display"] = {str(k): v for k, v in names.items() if v}
        self.save()

    def hidden(self, model_hash: str) -> set:
        return set(int(x) for x in self._data.get(model_hash, {}).get("hidden", []))

    def set_hidden(self, model_hash: str, hidden: set):
        self._entry(model_hash)["hidden"] = sorted(int(x) for x in hidden)
        self.save()

    def imported_mapping(self, model_hash: str):
        m = self._data.get(model_hash, {}).get("mapping")
        if not m:
            return None
        return {int(k): v for k, v in m["names"].items()}, m.get("file", "")

    def set_imported_mapping(self, model_hash: str, names, file_path: str = ""):
        e = self._entry(model_hash)
        e["mapping"] = None if names is None else {
            "names": {str(k): v for k, v in names.items()}, "file": file_path}
        self.save()


@dataclass
class ClassView:
    """Combines a registry with display names and the visibility filter."""
    registry: ClassRegistry
    display: dict = field(default_factory=dict)
    hidden: set = field(default_factory=set)

    def label(self, class_id: int) -> str:
        cid = int(class_id)
        return self.display.get(cid) or self.registry.name(cid)

    def original(self, class_id: int) -> str:
        return self.registry.name(class_id)

    def visible(self, class_id: int) -> bool:
        return int(class_id) not in self.hidden

    def mapping_export(self) -> list:
        return [{"class_id": k, "original_name": v, "display_name": self.display.get(k, ""),
                 "visible": k not in self.hidden}
                for k, v in sorted(self.registry.names.items())]
