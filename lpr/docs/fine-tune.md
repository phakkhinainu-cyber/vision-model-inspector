# ฝึกโมเดลด้วยภาพป้ายจากกล้องของคุณ (fine-tune)

โมเดลที่มากับโปรแกรมเป็นโมเดลทั่วไป: ตัวตรวจจับป้ายฝึกจากป้ายหลายประเทศ และ OCR ภาษาไทยของ PaddleOCR
(th_PP-OCRv5_mobile_rec) ทำได้ 82.68% บนชุดข้อมูลทั่วไปที่ผู้พัฒนาใช้ทดสอบ ไม่ใช่ชุดป้ายทะเบียน
ความแม่นยำจะดีขึ้นมากเมื่อฝึกเพิ่มด้วยภาพจากกล้องของคุณเอง (มุมกล้อง แสง ป้ายจริง)

ผลทดสอบของรุ่นนี้ (ภาพรถจริง 40 ภาพที่แปะป้ายไทยจำลอง, เฟรมเดียว ไม่โหวต): พบป้าย 100%, อ่านทะเบียนถูก 90%,
จังหวัดถูก 92.5% — ตัวที่ผิดบ่อยคือพยัญชนะที่พบน้อยบนป้าย เช่น ฬ ฎ ภ

## ขั้นที่ 1: เก็บภาพ

**วิธีง่าย (ในโปรแกรม):** ตั้งค่า → การจับภาพและอ่านป้าย → เปิด **เก็บภาพป้ายไว้ฝึกโมเดล**
ระบบจะเก็บภาพป้ายทุกเฟรมที่อ่านไว้ที่ `<ที่เก็บข้อมูล>\dataset\วันที่\` พร้อม `labels.tsv`
(ชื่อไฟล์, ทะเบียนที่อ่านได้, จังหวัด) — เปิดไว้ 1–2 สัปดาห์ทั้งกลางวันและกลางคืน แล้วปิด

**วิธีละเอียด (สคริปต์):** เก็บทั้งภาพเต็มเฟรม + กรอบป้าย (ใช้ฝึกตัวตรวจจับ) และภาพป้าย (ใช้ฝึก OCR)

```
python tools/collect_plates.py "rtsp://user:pass@192.168.1.20:554/stream1" --out D:\LPR\dataset --minutes 120
python tools/collect_plates.py D:\clips\gate.mp4 --out D:\LPR\dataset --every 0.5
```

ควรมีอย่างน้อย 300–1,000 ป้าย จากรถหลายคัน ทั้งกลางวัน กลางคืน ฝนตก

## ขั้นที่ 2: ติดป้ายกำกับ (label)

- **OCR**: เปิด `labels.tsv` ด้วย Excel/Notepad แก้คอลัมน์ทะเบียน (เช่น `1กข 4521`) และจังหวัดให้ถูกต้องทุกแถว
  แถวที่ภาพเบลอจนคนอ่านไม่ออกให้ลบทิ้ง — ทางลัด: แก้ในคิว **รอตรวจสอบ** ของโปรแกรมก่อน แล้วส่งออก CSV ใช้เป็นเฉลย
- **ตัวตรวจจับป้าย**: เปิดโฟลเดอร์ `frames/` ด้วยโปรแกรมติดป้ายกำกับ เช่น [Label Studio](https://labelstud.io/),
  [CVAT](https://www.cvat.ai/) หรือ LabelImg เลือกรูปแบบ **YOLO** แก้กรอบป้ายให้พอดี (1 class: `license_plate`)

## ขั้นที่ 3: ฝึกตัวตรวจจับป้าย (YOLO)

เครื่องที่ใช้ฝึก (ควรมีการ์ด NVIDIA):

```
pip install "ultralytics>=8.3,<8.4"
python tools/train_plate_detector.py --data D:\LPR\dataset\frames --epochs 60
```

ได้ไฟล์ `models/plate_yolo.onnx` — คัดลอกไปไว้ที่ `<ที่เก็บข้อมูล>\models\plate_yolo.onnx`
(โปรแกรมที่ติดตั้งแล้วจะใช้ไฟล์ในโฟลเดอร์นี้แทนโมเดลเดิม) แล้วรีสตาร์ตกล้อง (เมนู กล้อง → รีสตาร์ต)

ตั้งต้นจากโมเดลป้ายไทยที่มีอยู่แล้วได้ เช่น `--base HurricaneOD_beta.pt` จาก
https://huggingface.co/Rattatammanoon/hurricane-od-thai-plate-detector (Apache-2.0)

## ขั้นที่ 4: ฝึก OCR ภาษาไทย (PaddleOCR PP-OCRv5)

1. เตรียมข้อมูลบรรทัดข้อความจากภาพป้าย:
   ```
   python tools/prepare_ocr_dataset.py D:\LPR\dataset --out work\ocr_data
   ```
   ได้ `work\ocr_data\images\*.jpg`, `train.txt`, `val.txt` (รูปแบบ PaddleOCR: `images/xxx.jpg<TAB>1กข 4521`)
2. ติดตั้ง PaddleOCR สำหรับฝึก (Linux + NVIDIA แนะนำ):
   ```
   git clone https://github.com/PaddlePaddle/PaddleOCR && cd PaddleOCR
   pip install paddlepaddle-gpu -r requirements.txt
   ```
3. ดาวน์โหลด pretrained `th_PP-OCRv5_mobile_rec` (train model) และ config
   `configs/rec/PP-OCRv5/multi_language/th_PP-OCRv5_mobile_rec.yaml` แก้ใน config:
   `Global.pretrained_model`, `Train.dataset.data_dir/label_file_list`, `Eval.dataset...` ให้ชี้ไป work\ocr_data,
   ลด learning rate (เช่น 0.0001) และ epoch 20–50
4. ฝึกและส่งออก:
   ```
   python tools/train.py -c <config>.yaml
   python tools/export_model.py -c <config>.yaml -o Global.pretrained_model=output/.../best_accuracy Global.save_inference_dir=th_rec_ft
   paddle2onnx --model_dir th_rec_ft --model_filename inference.json --params_filename inference.pdiparams --save_file th_PP-OCRv5_mobile_rec.onnx --opset_version 14
   ```
5. คัดลอก `th_PP-OCRv5_mobile_rec.onnx` ไปที่ `<ที่เก็บข้อมูล>\models\` (ใช้ dict เดิมได้ เพราะชุดตัวอักษรเหมือนเดิม)

## ขั้นที่ 5: วัดผลก่อน/หลัง

เตรียมโฟลเดอร์ภาพรถ + `labels.tsv` (ชื่อไฟล์<TAB>ทะเบียน<TAB>จังหวัด) ที่ **ไม่ได้ใช้ฝึก**:

```
python tools/eval_accuracy.py D:\LPR\testset --report before.csv
python tools/eval_accuracy.py D:\LPR\testset --models D:\LPR\models --report after.csv
python tools/eval_accuracy.py D:\LPR\testset_plates --crops      # ถ้าเป็นภาพป้ายที่ครอปแล้ว
```

วัดแบบวิดีโอทั้งคลิป (มีการโหวตหลายเฟรมเหมือนใช้งานจริง):

```
python tools/eval_video.py D:\clips\gate.mp4 --line 0.05,0.6,0.95,0.6
```

## ใช้ OCR engine อื่น

ตั้งค่า → OCR engine: `auto` (ONNX ก่อน), `onnx`, `paddle` (ต้อง `pip install paddlepaddle paddleocr`), `easyocr`
(ต้อง `pip install easyocr`) — engine ใหม่ (เช่นบริการเชิงพาณิชย์) เพิ่มได้โดยเขียนคลาสที่มีเมธอด
`recognize(line_images) -> [(ข้อความ, ความมั่นใจ)]` ใน `backend/lpr/vision/ocr/` (ดู developer.md)
