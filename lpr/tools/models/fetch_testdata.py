"""เก็บภาพทดสอบ (รถที่เห็นป้ายทะเบียน, ไลเซนส์ CC BY 4.0) และสำรวจโมเดลป้ายไทยบน Hugging Face

ผลลัพธ์ (ใน --out):
  testdata.tar.gz   ภาพ + plates.json (กรอบป้ายจาก annotation) + ATTRIBUTION.txt
  thai_*.onnx       โมเดลป้ายไทยที่ส่งออกได้ (ไว้เปรียบเทียบ)
  explore.json      รายชื่อไฟล์/การ์ดโมเดล
"""
from __future__ import annotations

import argparse
import json
import shutil
import tarfile
import traceback
import zipfile
from pathlib import Path

DATASET = "keremberke/license-plate-object-detection"
THAI_MODELS = [
    "tanawichsingpae/thai-license-plate-detector",
    "tanawichsingpae/thai-license-plate-ocr",
    "Rattatammanoon/hurricane-od-thai-plate-detector",
    "hoangvudinh0301/thailand_plate",
]


def log(*a: object) -> None:
    print("[testdata]", *a, flush=True)


def explore(out: Path) -> dict:
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    info: dict = {}
    for repo in THAI_MODELS:
        try:
            files = api.list_repo_files(repo)
            card = ""
            try:
                card = Path(hf_hub_download(repo, "README.md", local_dir=f"work/x/{repo}")).read_text("utf-8")
            except Exception:  # noqa: BLE001
                pass
            log("MODEL", repo, files)
            log("CARD", repo, card[:2500].replace("\n", " | "))
            info[repo] = {"files": files, "card": card[:4000]}
            pts = [f for f in files if f.endswith(".pt")]
            if pts:
                try:
                    from ultralytics import YOLO

                    p = hf_hub_download(repo, sorted(pts, key=len)[0], local_dir=f"work/x/{repo}")
                    m = YOLO(p)
                    log("YOLO", repo, "task", m.task, "names", m.names)
                    f = m.export(format="onnx", imgsz=640, opset=12, simplify=True)
                    dst = out / f"thai_{repo.split('/')[0]}.onnx"
                    shutil.move(f, dst)
                    (dst.with_suffix(".names.json")).write_text(json.dumps(m.names, ensure_ascii=False), "utf-8")
                    info[repo]["onnx"] = dst.name
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
        except Exception as e:  # noqa: BLE001
            log("explore failed", repo, e)
    try:
        ds = [d.id for d in api.list_datasets(search="license plate", sort="downloads", limit=30)]
        log("DATASETS license plate:", ds)
        info["_datasets"] = ds
    except Exception as e:  # noqa: BLE001
        log("dataset search failed", e)
    return info


def testdata(out: Path) -> None:
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    files = api.list_repo_files(DATASET, repo_type="dataset")
    log("dataset files", files)
    root = Path("work/td")
    imgs_out = root / "images"
    imgs_out.mkdir(parents=True, exist_ok=True)
    plates: dict = {}
    for split in ("test", "valid"):
        zf = next((f for f in files if f.endswith(f"{split}.zip")), None)
        if not zf:
            continue
        p = hf_hub_download(DATASET, zf, repo_type="dataset", local_dir="work/ds")
        ex = root / split
        with zipfile.ZipFile(p) as z:
            z.extractall(ex)
        ann = next(ex.rglob("_annotations.coco.json"))
        coco = json.loads(ann.read_text("utf-8"))
        by_img: dict = {}
        for a in coco["annotations"]:
            by_img.setdefault(a["image_id"], []).append(a["bbox"])
        for im in coco["images"]:
            boxes = by_img.get(im["id"], [])
            if len(boxes) != 1:
                continue
            x, y, w, h = boxes[0]
            if w < 70 or w / max(h, 1) < 1.6:
                continue
            src = next(ann.parent.rglob(im["file_name"]), None)
            if src is None:
                continue
            name = f"{split}_{len(plates):03d}.jpg"
            shutil.copy(src, imgs_out / name)
            plates[name] = {"bbox_xywh": [x, y, w, h], "size": [im["width"], im["height"]]}
            if len(plates) >= 80:
                break
        if len(plates) >= 80:
            break
    (root / "plates.json").write_text(json.dumps(plates, indent=1), "utf-8")
    (root / "ATTRIBUTION.txt").write_text(
        f"Images from Hugging Face dataset {DATASET} (Roboflow License Plates dataset), license CC BY 4.0.\n"
        "Used only for testing the LPR pipeline. https://huggingface.co/datasets/" + DATASET + "\n", "utf-8")
    with tarfile.open(out / "testdata.tar.gz", "w:gz") as t:
        t.add(root / "images", arcname="images")
        t.add(root / "plates.json", arcname="plates.json")
        t.add(root / "ATTRIBUTION.txt", arcname="ATTRIBUTION.txt")
    log("testdata images", len(plates))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out_testdata")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    info = {}
    try:
        info = explore(out)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    (out / "explore.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), "utf-8")
    try:
        testdata(out)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
