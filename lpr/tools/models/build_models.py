"""สร้างไฟล์โมเดล ONNX ทั้งหมดที่โปรแกรม LPR ใช้ (รันใน CI หรือบนเครื่องนักพัฒนาที่มีอินเทอร์เน็ต)

ขั้นตอน:
1. YOLO11n (COCO) -> ONNX สำหรับตรวจจับรถ (car, motorcycle, bus, truck)
2. โมเดลตรวจจับป้ายทะเบียน (YOLO) -> ONNX
3. PaddleOCR PP-OCRv5 ภาษาไทย (th_PP-OCRv5_mobile_rec) -> ONNX + ไฟล์ตัวอักษร (dict)
4. ทดสอบอ่านข้อความไทยที่เรนเดอร์เอง เทียบกับผลจาก PaddleOCR ต้นฉบับ
5. เขียน manifest.json (sha256, แหล่งที่มา, ไลเซนส์)

Usage: python build_models.py --out out_models [--testdata out_testdata]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import traceback
import urllib.request
from pathlib import Path

ULTRA_ASSETS = "https://github.com/ultralytics/assets/releases/download/v8.3.0"
SARABUN_URL = "https://github.com/google/fonts/raw/main/ofl/sarabun/Sarabun-Regular.ttf"

PLATE_CANDIDATES = [
    # (hf repo, preferred file substrings) — ลองตามลำดับ ใช้ตัวแรกที่ส่งออก ONNX ได้
    ("morsetechlab/yolov11-license-plate-detection", ["v1n.pt", "n.pt", ".pt"]),
    ("keremberke/yolov8n-license-plate-extraction", ["best.pt", ".pt"]),
]

PADDLE_MODELS = ["th_PP-OCRv5_mobile_rec", "PP-OCRv5_mobile_det"]
BOS = "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/{ver}/{name}_infer.tar"


def log(*a: object) -> None:
    print("[build_models]", *a, flush=True)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    log("download", url)
    req = urllib.request.Request(url, headers={"User-Agent": "lpr-build"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)
    return dst


def export_yolo(pt: Path, out: Path, imgsz: int) -> Path:
    from ultralytics import YOLO

    m = YOLO(str(pt))
    log("classes", pt.name, dict(list(m.names.items())[:10]), "n=", len(m.names))
    f = m.export(format="onnx", imgsz=imgsz, opset=12, simplify=True, dynamic=False)
    shutil.move(f, out)
    (out.with_suffix(".names.json")).write_text(json.dumps(m.names, ensure_ascii=False), "utf-8")
    return out


def stage_vehicle(out: Path, manifest: dict) -> None:
    pt = download(f"{ULTRA_ASSETS}/yolo11n.pt", Path("work/yolo11n.pt"))
    dst = export_yolo(pt, out / "vehicle_yolo11n.onnx", 640)
    manifest["vehicle"] = {"file": dst.name, "source": f"{ULTRA_ASSETS}/yolo11n.pt",
                           "license": "AGPL-3.0 (Ultralytics)", "imgsz": 640,
                           "classes": {"2": "car", "3": "motorcycle", "5": "bus", "7": "truck"}}


def stage_plate(out: Path, manifest: dict) -> None:
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    try:
        found = [m.id for m in api.list_models(search="license plate", sort="downloads", limit=40)]
        log("HF models search 'license plate':", found)
        for q in ("thai license plate", "thai plate", "thai lpr"):
            log(f"HF models search '{q}':", [m.id for m in api.list_models(search=q, limit=30)])
    except Exception as e:  # noqa: BLE001
        log("search failed", e)
    for repo, prefs in PLATE_CANDIDATES:
        try:
            files = api.list_repo_files(repo)
            log("files", repo, files)
            pick = None
            for p in prefs:
                cands = [f for f in files if f.endswith(p)]
                if cands:
                    pick = sorted(cands, key=len)[0]
                    break
            if not pick:
                continue
            pt = Path(hf_hub_download(repo, pick, local_dir="work/plate"))
            dst = export_yolo(pt, out / "plate_yolo.onnx", 640)
            card = ""
            try:
                card = Path(hf_hub_download(repo, "README.md", local_dir="work/plate")).read_text("utf-8")[:1500]
            except Exception:  # noqa: BLE001
                pass
            lic = "see model card"
            for line in card.splitlines():
                if line.lower().startswith("license:"):
                    lic = line.split(":", 1)[1].strip()
            manifest["plate"] = {"file": dst.name, "source": f"https://huggingface.co/{repo}/{pick}",
                                 "license": lic, "imgsz": 640}
            log("plate model OK from", repo, pick, "license", lic)
            return
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    log("WARNING: no plate model; app will use classical plate finder")


def fetch_paddle(name: str) -> Path | None:
    """คืนโฟลเดอร์ที่มี inference.json/.pdmodel + inference.pdiparams + inference.yml"""
    try:
        from huggingface_hub import snapshot_download

        d = Path(snapshot_download(f"PaddlePaddle/{name}", local_dir=f"work/paddle/{name}"))
        if any(d.glob("inference.pdiparams")):
            log("paddle model from HF", name)
            return d
    except Exception as e:  # noqa: BLE001
        log("HF paddle failed", name, e)
    for ver in ("paddle3.0.0", "paddle3.1.0"):
        try:
            tar = download(BOS.format(ver=ver, name=name), Path(f"work/paddle/{name}.tar"))
            with tarfile.open(tar) as t:
                t.extractall(f"work/paddle/{ver}")
            d = next(Path(f"work/paddle/{ver}").rglob("inference.pdiparams")).parent
            log("paddle model from BOS", name, ver)
            return d
        except Exception as e:  # noqa: BLE001
            log("BOS failed", name, ver, e)
    try:  # สุดท้าย: ให้ paddleocr ดาวน์โหลดเอง
        if name.endswith("_rec"):
            from paddleocr import TextRecognition

            TextRecognition(model_name=name)
        else:
            from paddleocr import TextDetection

            TextDetection(model_name=name)
        d = Path.home() / ".paddlex" / "official_models" / name
        if d.exists():
            return d
    except Exception as e:  # noqa: BLE001
        log("paddleocr download failed", name, e)
    return None


def paddle_to_onnx(d: Path, dst: Path) -> None:
    model_file = "inference.json" if (d / "inference.json").exists() else "inference.pdmodel"
    cmd = ["paddle2onnx", "--model_dir", str(d), "--model_filename", model_file,
           "--params_filename", "inference.pdiparams", "--save_file", str(dst), "--opset_version", "14"]
    log(" ".join(cmd))
    subprocess.run(cmd, check=True)


def read_dict_from_yml(d: Path) -> list[str]:
    import yaml

    y = yaml.safe_load((d / "inference.yml").read_text("utf-8"))
    pp = y.get("PostProcess", {})
    chars = pp.get("character_dict") or []
    log("PostProcess", {k: (v if k != "character_dict" else f"<{len(v)} chars>") for k, v in pp.items()})
    return [str(c) for c in chars]


def stage_ocr(out: Path, manifest: dict) -> None:
    for name in PADDLE_MODELS:
        d = fetch_paddle(name)
        if d is None:
            log("ERROR: cannot fetch", name)
            continue
        log("files", name, sorted(p.name for p in d.iterdir()))
        dst = out / f"{name}.onnx"
        paddle_to_onnx(d, dst)
        entry = {"file": dst.name, "source": f"PaddleOCR {name}", "license": "Apache-2.0"}
        if name.endswith("_rec"):
            chars = read_dict_from_yml(d)
            (out / f"{name}.dict.txt").write_text("\n".join(chars) + "\n", "utf-8")
            entry["dict"] = f"{name}.dict.txt"
            entry["dict_size"] = len(chars)
            manifest["ocr_rec"] = entry
        else:
            manifest["ocr_det"] = entry


def smoke_ocr(out: Path, manifest: dict) -> None:
    """เรนเดอร์ข้อความไทยแล้วอ่านด้วย ONNX เทียบกับ PaddleOCR ต้นฉบับ เพื่อยืนยันการ preprocess/decode"""
    if "ocr_rec" not in manifest:
        return
    import cv2
    import numpy as np
    import onnxruntime as ort
    from PIL import Image, ImageDraw, ImageFont

    font_path = download(SARABUN_URL, Path("work/Sarabun-Regular.ttf"))
    font = ImageFont.truetype(str(font_path), 64)
    chars = (out / manifest["ocr_rec"]["dict"]).read_text("utf-8").split("\n")[:-1]
    sess = ort.InferenceSession(str(out / manifest["ocr_rec"]["file"]), providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    log("rec input", inp.name, inp.shape, "output", sess.get_outputs()[0].shape)
    results = []
    for text in ["1กข 4521", "กรุงเทพมหานคร", "70-4518", "เชียงใหม่", "บต 7783"]:
        img = Image.new("RGB", (40 * len(text) + 40, 96), "white")
        ImageDraw.Draw(img).text((20, 8), text, font=font, fill="black")
        bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]
        nw = int(np.ceil(48 * w / h))
        x = cv2.resize(bgr, (nw, 48)).astype(np.float32) / 255.0
        x = (x - 0.5) / 0.5
        x = x.transpose(2, 0, 1)[None]
        prob = sess.run(None, {inp.name: x})[0][0]
        idx = prob.argmax(1)
        table = ["<blank>"] + chars + [" "]
        s, prev = [], -1
        for i in idx:
            if i != prev and i != 0:
                s.append(table[i] if i < len(table) else "?")
            prev = i
        got = "".join(s)
        ref = None
        try:
            from paddleocr import TextRecognition

            if not hasattr(smoke_ocr, "_tr"):
                smoke_ocr._tr = TextRecognition(model_name="th_PP-OCRv5_mobile_rec")  # type: ignore[attr-defined]
            r = smoke_ocr._tr.predict(bgr)  # type: ignore[attr-defined]
            ref = r[0]["rec_text"] if r else None
        except Exception as e:  # noqa: BLE001
            ref = f"<paddleocr error {e}>"
        log(f"OCR smoke: text={text!r} onnx={got!r} paddle={ref!r} classes={prob.shape[1]} table={len(table)}")
        results.append({"text": text, "onnx": got, "paddle": ref})
    manifest["ocr_smoke"] = results


def collect_testdata(dst: Path) -> None:
    """ดาวน์โหลดภาพตัวอย่างป้ายไทยจำนวนเล็กน้อยไว้ทดสอบ (ไม่แจกจ่ายไปกับโปรแกรม)"""
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    dst.mkdir(parents=True, exist_ok=True)
    info = []
    for q in ("thai license plate", "thai plate", "license plate thailand", "thai lpr", "thai car"):
        try:
            ds = list(api.list_datasets(search=q, limit=20))
            log(f"HF datasets '{q}':", [d.id for d in ds])
            info += [d.id for d in ds]
        except Exception as e:  # noqa: BLE001
            log("dataset search failed", e)
    got = 0
    for repo in dict.fromkeys(info):
        if got >= 60:
            break
        try:
            files = api.list_repo_files(repo, repo_type="dataset")
            imgs = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png"))][:30]
            log("dataset", repo, "files", len(files), "images", len(imgs))
            for f in imgs:
                p = hf_hub_download(repo, f, repo_type="dataset", local_dir=f"work/ds/{repo.replace('/', '__')}")
                shutil.copy(p, dst / f"{repo.replace('/', '__')}__{Path(f).name}")
                got += 1
        except Exception as e:  # noqa: BLE001
            log("dataset fetch failed", repo, e)
    (dst / "SOURCES.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), "utf-8")
    log("testdata images:", got)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out_models")
    ap.add_argument("--testdata", default="")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"version": 1}
    for stage in (stage_vehicle, stage_plate, stage_ocr, smoke_ocr):
        try:
            stage(out, manifest)
        except Exception:  # noqa: BLE001
            log("stage failed", stage.__name__)
            traceback.print_exc()
    if a.testdata:
        try:
            collect_testdata(Path(a.testdata))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    for k, v in list(manifest.items()):
        if isinstance(v, dict) and "file" in v and (out / v["file"]).exists():
            v["sha256"] = sha256(out / v["file"])
            v["size"] = (out / v["file"]).stat().st_size
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    log(json.dumps(manifest, ensure_ascii=False, indent=2))
    ok = "vehicle" in manifest and "ocr_rec" in manifest
    return 0 if ok else 1


if __name__ == "__main__":
    os.makedirs("work", exist_ok=True)
    sys.exit(main())
