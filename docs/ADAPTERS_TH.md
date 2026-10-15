# คู่มือเพิ่ม Model Adapter และ Camera Adapter

## 1. โครงสร้างที่เกี่ยวข้อง

```
src/vmi/
  adapters/base.py              ModelAdapter (interface), ModelInfo, ข้อผิดพลาดมาตรฐาน
  adapters/registry.py          เลือก adapter ตามนามสกุลไฟล์ (ลงทะเบียน adapter ใหม่ที่นี่)
  adapters/ultralytics_adapter  YOLOv8 / YOLO11 .pt  (+ Grad-CAM)
  adapters/onnx_adapter.py      YOLOv8 / YOLO11 .onnx (ไม่มี Grad-CAM ในรุ่นแรก)
  gradcam/ultralytics_gradcam   Grad-CAM ต่อ detection instance
  core/types.py                 Detection / DetectionResult (normalized)
  core/classes.py               ClassRegistry, การอ่าน mapping, ชื่อแสดงผล
  sources/base.py               FrameSource (interface ของแหล่งภาพ)
  sources/qt_camera.py          กล้อง USB/ในเครื่องผ่าน Qt Multimedia
  sources/opencv_source.py      วิดีโอ, OpenCV index/backend, RTSP
```

## 2. สัญญาของ Model Adapter

| สิ่งที่ต้องทำ | รายละเอียด |
|---|---|
| `key`, `display_name`, `formats` | ชื่อ adapter และนามสกุลไฟล์ที่รับ |
| `load(path, device) -> ModelInfo` | ตรวจไฟล์ **ปฏิเสธ** ไฟล์ที่ไม่รู้จักด้วย `UnsupportedModelError` (ข้อความภาษาไทย) ห้ามเดา |
| `ModelInfo.caps` | ประกาศ `task`, `formats`, `input_shape`/`dynamic_input`, `stride`, `output_layout`, `grad_cam` + เหตุผล, `limitations` |
| `ModelInfo.classes` | `ClassRegistry` ตามลำดับความสำคัญ: metadata ในโมเดล → metadata ONNX → ไฟล์ผู้ใช้ → `class_N` (แจ้งว่าไม่มีชื่อ) |
| `predict(image_bgr, settings) -> list[Detection]` | กรอบ **ในพิกัดภาพต้นฉบับ** (แก้ letterbox/resize แล้ว) และต้องเรียกโมเดลภายใต้ `self.lock` |
| `output_class_count()` | จำนวนคลาสจาก output จริง (None ถ้าตรวจไม่ได้) ใช้ตรวจไฟล์ mapping |
| `gradcam_engine()` | คืนอ็อบเจ็กต์ที่มี `layer_options()` และ `compute(image, det, imgsz, layer_key)` หรือ `None` |
| `close()` | คืนหน่วยความจำ (GPU/session) — เรียกก่อนเปลี่ยนโมเดลเสมอ |
| ข้อผิดพลาดอุปกรณ์ | ใช้ `DeviceUnavailableError` เพื่อให้ UI เสนอ CPU แทน |

ตัวอย่างโครง adapter ใหม่ (เช่น RT-DETR หรือโมเดล segmentation ภายหลัง):

```python
from vmi.adapters.base import ModelAdapter, ModelInfo, UnsupportedModelError
from vmi.core.types import AdapterCapabilities, Detection

class MyAdapter(ModelAdapter):
    key = "my-format"
    display_name = "My detector"
    formats = (".mymodel",)

    def load(self, path, device="auto"):
        ident = self.make_identity(path, self.key)
        ...                                   # เปิดโมเดล ตรวจ input/output
        caps = AdapterCapabilities(task="detect", formats=self.formats, grad_cam=False,
                                   grad_cam_reason="ยังไม่รองรับ", input_shape=(1, 3, 640, 640),
                                   dynamic_input=False, output_layout="...")
        self.info = ModelInfo(ident, caps, registry, device_used, True, caps.grad_cam_reason)
        return self.info

    def predict(self, image_bgr, settings):
        with self.lock:
            ...
        return [Detection(i, cls, conf, (x1, y1, x2, y2)) for ...]
```

จากนั้นเพิ่มคลาสใน `adapters/registry.py::_adapters()` และเขียนเทสใน `tests/` อย่างน้อย:
พิกัดหลัง letterbox, จำนวน/ชื่อคลาส, ไฟล์เสีย, ไฟล์ที่ไม่รองรับ

### งาน (task) อื่นในอนาคต
`AdapterCapabilities.task` และ `DetectionResult` ถูกออกแบบให้ขยายได้ — สำหรับ segmentation ให้เพิ่มฟิลด์ mask
แยกใน dataclass ใหม่และให้ UI ตรวจ `caps.task` ก่อนแสดงผล ห้ามแปลงผลของ task อื่นให้ดูเหมือน detection

## 3. Grad-CAM สำหรับ adapter ใหม่
ต้องทำตามข้อกำหนด:
1. คำนวณจาก snapshot ที่เลือกเท่านั้น และเลือก **detection instance** (ไม่ใช่แค่คลาส)
2. target scalar ต้องมาจาก output ที่ยังเชื่อมกับ autograd (ห้าม `no_grad`/`inference_mode` ในเส้นทาง gradient)
3. อธิบายและทดสอบการจับคู่ผลหลัง NMS → target ก่อน NMS (ดู docstring ใน `gradcam/ultralytics_gradcam.py`)
4. ตรวจ shape ของ target layer, ถอด hook ใน `finally`, คืนหน่วยความจำ
5. แปลง heat map กลับพิกัดภาพต้นฉบับ (`core.imageops.unletterbox_map`)
6. gradient เป็นศูนย์ / ไม่พบ target → `GradCamError` พร้อมเหตุผล **ห้ามสร้าง heat map ปลอม**

## 4. Camera Adapter (แหล่งภาพ)

สืบทอด `sources.base.FrameSource` แล้วทำ `start()`, `stop()` และเรียก `self._emit_frame(bgr)` ทุกเฟรม

ข้อกำหนด:
* เปิดอุปกรณ์ด้วย **identifier จริง** ของ backend ที่ใช้ enumerate (ห้ามสมมติว่าลำดับของสอง backend ตรงกัน)
* มี timeout ตอนเปิด, จัดการอุปกรณ์หาย/ถูกใช้งานอยู่, `stop()` ต้องคืนอุปกรณ์เสมอ (เริ่ม/หยุดซ้ำได้)
* ห้ามบันทึกรหัสผ่านลง log (ใช้ `config.redact`) หรือเก็บ credential แบบข้อความธรรมดา (ใช้ `sources.credentials`)
* แจ้งสถานะผ่าน `_status()` / `_error()` เป็นภาษาไทย

### กล้องอุตสาหกรรม (GigE Vision / USB3 Vision)
ต้องใช้ SDK ของผู้ผลิต (เช่น Basler pylon → `pypylon`, Teledyne FLIR Spinnaker → `PySpin`, Hikrobot MVS) แนวทาง:

```python
class PylonSource(FrameSource):
    kind = "pylon"
    def start(self):
        # เปิดกล้องด้วย serial number (stable identifier) ใน thread แยก
        # grab loop -> self._emit_frame(bgr) ; จัดการ timeout / disconnect
    def stop(self):
        # หยุด grab, ปิดกล้อง, join thread
```

แล้วเพิ่มรายการกล้องใน `CameraDialog` (แท็บใหม่) และ `make_source()` — SDK ของผู้ผลิตมีสัญญาอนุญาตของตนเอง
ต้องตรวจก่อนแจกจ่าย ห้ามประกาศว่ารองรับกล้องทุกยี่ห้อ
