import { useCallback, useEffect, useRef, useState } from "react";
import { api, media } from "../api";
import { ProvinceInput } from "../components/EventDetail";
import { Icon } from "../components/Icons";
import { Empty } from "../components/Modal";
import { DirTag, PlateChip, ReviewBadge } from "../components/Plate";
import { fmtDate, fmtTime } from "../format";
import { useLive, useStore } from "../store";
import type { LprEvent } from "../types";

/** คิวรอตรวจสอบ: แก้เร็วด้วยคีย์บอร์ด
 *  Enter = บันทึก/ยืนยัน · 1–3 = เลือกผลอ่านอื่น · ↑/↓ = รายการก่อน/ถัดไป · Esc = ข้าม · Ctrl+Del = ลบ */
export function Review() {
  const { isAdmin, toast, refreshSystem } = useStore();
  const [items, setItems] = useState<LprEvent[] | null>(null);
  const [total, setTotal] = useState(0);
  const [idx, setIdx] = useState(0);
  const [plate, setPlate] = useState("");
  const [province, setProvince] = useState("");
  const [direction, setDirection] = useState<"เข้า" | "ออก">("เข้า");
  const plateRef = useRef<HTMLInputElement>(null);
  const load = useCallback(() => {
    api.get<{ items: LprEvent[]; total: number }>("/api/review").then((r) => { setItems(r.items); setTotal(r.total); });
  }, []);
  useEffect(load, [load]);
  useLive((m) => {
    if (m.type === "event" && (m.event.review_status === "รอตรวจสอบ" || m.event.review_status === "อ่านไม่ได้")) {
      setItems((x) => (x ? [...x, m.event] : x));
      setTotal((t) => t + 1);
    }
  });
  const cur = items?.[idx];
  useEffect(() => {
    if (!cur) return;
    setPlate(cur.plate_display);
    setProvince(cur.province);
    setDirection(cur.direction);
    setTimeout(() => { plateRef.current?.focus(); plateRef.current?.select(); }, 0);
  }, [cur?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const done = (id: number) => {
    setItems((x) => x && x.filter((e) => e.id !== id));
    setTotal((t) => Math.max(0, t - 1));
    setIdx((i) => Math.max(0, Math.min(i, (items?.length || 1) - 2)));
    refreshSystem();
  };
  const save = async () => {
    if (!cur || !isAdmin) return;
    try {
      const changed = plate !== cur.plate_display || province !== cur.province || direction !== cur.direction;
      await api.patch(`/api/events/${cur.id}`, changed ? { plate, province, direction } : { review_status: plate ? "แก้ไขแล้ว" : "อ่านไม่ได้", plate, province });
      toast(changed ? "แก้ไขแล้ว" : "ยืนยันแล้ว");
      done(cur.id);
    } catch (e) { toast((e as Error).message, "error"); }
  };
  const del = async () => {
    if (!cur || !isAdmin || !confirm("ลบเหตุการณ์นี้?")) return;
    try { await api.del(`/api/events/${cur.id}`); toast("ลบแล้ว"); done(cur.id); } catch (e) { toast((e as Error).message, "error"); }
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (!items?.length) return;
    if (e.key === "Enter") { e.preventDefault(); save(); }
    else if (e.key === "ArrowDown" || (e.key === "Escape" && !document.querySelector(".modal"))) { e.preventDefault(); setIdx((i) => Math.min(items.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); }
    else if (e.key === "Delete" && e.ctrlKey) { e.preventDefault(); del(); }
    else if (["1", "2", "3"].includes(e.key) && e.altKey && cur?.alternatives?.[Number(e.key) - 1]) {
      e.preventDefault();
      const a = cur.alternatives[Number(e.key) - 1];
      setPlate(a.display || a.plate_norm);
    }
  };

  return (
    <div className="page" onKeyDown={onKey}>
      <div className="page-head">
        <div className="page-title">
          <h1>รอตรวจสอบ</h1>
          <p className="muted">รายการที่ความมั่นใจต่ำหรืออ่านป้ายไม่ได้ · เหลือ {total} รายการ</p>
        </div>
      </div>
      {!items ? <div className="skeleton" style={{ height: 300 }} /> : items.length === 0 ? (
        <div className="card"><Empty icon="check" title="ไม่มีรายการรอตรวจสอบ" text="เยี่ยม! ทุกรายการได้รับการตรวจแล้ว" /></div>
      ) : (
        <div className="review">
          <div className="card review-list" role="listbox" aria-label="รายการรอตรวจสอบ">
            {items.map((e, i) => (
              <button key={e.id} role="option" aria-selected={i === idx} className={`rv-item ${i === idx ? "sel" : ""}`} onClick={() => setIdx(i)}>
                <span className="mono small">{fmtTime(e.ts)}</span>
                <PlateChip display={e.plate_display} bg={e.plate_bg} fg={e.plate_fg} size="sm" />
                <ReviewBadge status={e.review_status} />
              </button>
            ))}
          </div>
          {cur && (
            <div className="card review-main">
              <div className="review-imgs">
                {cur.has_full ? <img src={media(cur.id, "full")} alt="ภาพเต็มจากกล้อง" className="rv-full" /> : <div className="media-none">ไม่มีภาพ</div>}
                {cur.has_plate && <img src={media(cur.id, "plate")} alt="ภาพป้ายที่ครอป" className="rv-plate" />}
              </div>
              <div className="review-form">
                <div className="row">
                  <DirTag dir={cur.direction} /><span className="muted">{fmtDate(cur.ts)} {fmtTime(cur.ts)} · {cur.camera_name}</span>
                  <span className="muted">· ความมั่นใจ {Math.round(cur.ocr_confidence * 100)}%</span>
                </div>
                {cur.alternatives?.length > 1 && (
                  <div className="alts">
                    {cur.alternatives.map((a, i) => (
                      <button key={a.plate_norm} className="btn btn-sm" onClick={() => setPlate(a.display || a.plate_norm)}>
                        <kbd>Alt+{i + 1}</kbd> {a.display || a.plate_norm} <span className="muted">{Math.round(a.share * 100)}%</span>
                      </button>
                    ))}
                  </div>
                )}
                <div className="grid3">
                  <label className="field"><span className="field-label">ทะเบียน</span>
                    <input ref={plateRef} className="input input-plate input-lg" value={plate} onChange={(e) => setPlate(e.target.value)}
                      disabled={!isAdmin} placeholder="เว้นว่าง = อ่านไม่ได้" /></label>
                  <label className="field"><span className="field-label">จังหวัด</span><ProvinceInput value={province} onChange={setProvince} /></label>
                  <label className="field"><span className="field-label">ทิศทาง</span>
                    <select className="input" value={direction} onChange={(e) => setDirection(e.target.value as "เข้า" | "ออก")} disabled={!isAdmin}>
                      <option>เข้า</option><option>ออก</option></select></label>
                </div>
                {isAdmin ? (
                  <div className="row">
                    <button className="btn btn-primary" onClick={save}><Icon name="check" size={16} /> บันทึก <kbd>Enter</kbd></button>
                    <button className="btn" onClick={() => setIdx(Math.min(items.length - 1, idx + 1))}>ข้าม <kbd>Esc</kbd></button>
                    <button className="btn btn-danger" onClick={del}><Icon name="trash" size={16} /> ลบ <kbd>Ctrl+Del</kbd></button>
                  </div>
                ) : <p className="muted">ต้องเป็นผู้ดูแลระบบจึงแก้ไขได้</p>}
                <p className="muted small"><Icon name="keyboard" size={14} /> ↑/↓ เลื่อนรายการ · Enter บันทึก · Alt+1–3 เลือกผลอ่านอื่น · Esc ข้าม</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
