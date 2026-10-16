import { useCallback, useEffect, useState } from "react";
import { api, media } from "../api";
import { fmtDate, fmtDateTime, fmtDuration, fmtHM, fmtTime } from "../format";
import { useLive, useStore } from "../store";
import { VEHICLE_STATUSES, VEHICLE_TYPES, type LprEvent, type Vehicle, type Visit } from "../types";
import { Icon } from "./Icons";
import { Empty, Field, Lightbox, Modal } from "./Modal";
import { BigPlate, DirTag, PlateChip, ReviewBadge, StatusBadge } from "./Plate";

interface Detail { event: LprEvent; vehicle: (Vehicle & { visits_today: Visit[] }) | null }

export function useEventDetail(id: number | null) {
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    if (!id) { setData(null); return; }
    api.get<Detail>(`/api/events/${id}`).then((d) => { setData(d); setError(""); }).catch((e) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);
  useLive((m) => {
    if ((m.type === "event_update" && m.event.id === id) || m.type === "vehicle_update") load();
    if (m.type === "event" && data?.event.vehicle_id && m.event.vehicle_id === data.event.vehicle_id) load();
  });
  return { data, error, reload: load };
}

export function EventDetail({ id, compact = false, onDeleted }: { id: number | null; compact?: boolean; onDeleted?: () => void }) {
  const { data, error, reload } = useEventDetail(id);
  const { isAdmin, toast } = useStore();
  const [view, setView] = useState<"full" | "plate">("full");
  const [fullLoaded, setFullLoaded] = useState(!compact);
  const [box, setBox] = useState<null | "image" | "clip">(null);
  const [edit, setEdit] = useState<null | "plate" | "vehicle" | "history">(null);
  useEffect(() => { setView("full"); setFullLoaded(!compact); }, [id, compact]);

  if (!id) return <div className="card detail"><Empty icon="car" title="เลือกรายการจากไทม์ไลน์" text="รายละเอียดรถและภาพจากกล้องจะแสดงที่นี่" /></div>;
  if (error) return <div className="card detail"><Empty icon="alert" title="โหลดข้อมูลไม่สำเร็จ" text={error} /></div>;
  if (!data) return <div className="card detail"><div className="skeleton" style={{ height: 240 }} /></div>;
  const e = data.event;
  const v = data.vehicle;
  const bust = Math.round(e.edited_at || 0);
  const imgSrc = view === "plate" && e.has_plate ? media(e.id, "plate", bust)
    : fullLoaded ? media(e.id, "full", bust) : media(e.id, "thumb", bust);

  const quickStatus = async (status: string) => {
    try {
      await api.post(`/api/vehicles/from-event/${e.id}`, { status });
      toast(`ตั้งสถานะเป็น ${status} แล้ว`);
      reload();
    } catch (err) { toast((err as Error).message, "error"); }
  };

  return (
    <div className="card detail">
      <div className="detail-media">
        {(e.has_full || e.has_plate) ? (
          <button className="media-btn" onClick={() => (fullLoaded || view === "plate" ? setBox("image") : setFullLoaded(true))}
            aria-label={fullLoaded ? "ขยายภาพเต็มจอ" : "โหลดภาพเต็ม"}>
            <img src={imgSrc} alt={`ภาพจากกล้อง ${e.camera_name}`} className={view === "plate" ? "is-plate" : ""} />
            {!fullLoaded && view === "full" && <span className="media-hint">แตะเพื่อโหลดภาพเต็ม</span>}
          </button>
        ) : <div className="media-none"><Icon name="image" size={32} /> ไม่มีภาพ (อาจถูกลบตามระยะเก็บภาพ)</div>}
        <div className="media-tools">
          <div className="seg" role="group" aria-label="สลับภาพ">
            <button className={view === "full" ? "on" : ""} onClick={() => setView("full")} disabled={!e.has_full}>ภาพเต็ม</button>
            <button className={view === "plate" ? "on" : ""} onClick={() => setView("plate")} disabled={!e.has_plate}>ภาพป้าย</button>
          </div>
          {e.has_clip && <button className="btn btn-sm" onClick={() => setBox("clip")}><Icon name="play" size={14} /> เล่นคลิป</button>}
          {(e.has_full || e.has_plate) && (
            <button className="icon-btn" onClick={() => { setFullLoaded(true); setBox("image"); }} aria-label="ขยายเต็มจอ">
              <Icon name="maximize" />
            </button>
          )}
        </div>
      </div>

      <div className="detail-plate">
        <BigPlate display={e.plate_display} province={e.province} bg={e.plate_bg} fg={e.plate_fg} />
        <div className="detail-when">
          <DirTag dir={e.direction} />
          <span className="mono">{fmtTime(e.ts)}</span>
          <span className="muted">{fmtDate(e.ts)} · {e.camera_name || "ไม่ระบุกล้อง"}</span>
        </div>
        {e.review_status !== "ปกติ" && <div className="detail-review"><ReviewBadge status={e.review_status} />
          {e.original_plate && <span className="muted small">อ่านได้เดิม: {e.original_plate}</span>}</div>}
      </div>

      <dl className="kv">
        <div><dt>ประเภท</dt><dd>{v?.vehicle_type || e.vehicle_type || "-"}</dd></div>
        <div><dt>สถานะ</dt><dd><StatusBadge status={v?.status || e.vehicle_status} /></dd></div>
        <div><dt>เจ้าของ</dt><dd>{v?.owner_name || "-"}</dd></div>
        <div><dt>บ้านเลขที่</dt><dd>{v?.house_no || "-"}</dd></div>
        <div><dt>พบครั้งแรก</dt><dd>{v?.first_seen ? fmtDateTime(v.first_seen) : "-"}</dd></div>
        <div><dt>ความแม่นยำ</dt><dd>
          <span className="conf"><span className="conf-bar"><span style={{ width: `${Math.round(e.ocr_confidence * 100)}%` }}
            className={e.ocr_confidence >= 0.8 ? "good" : "low"} /></span>{Math.round(e.ocr_confidence * 100)}%</span>
        </dd></div>
      </dl>

      {v && (
        <>
          <section className="detail-sec">
            <h3>เข้า-ออกวันนี้</h3>
            {v.visits_today.length === 0 ? <p className="muted small">ยังไม่มีรายการวันนี้</p> : (
              <ul className="pairs">
                {v.visits_today.map((x) => (
                  <li key={x.id}>
                    <span className="pin">เข้า {x.entry_ts ? fmtHM(x.entry_ts) : "—"}</span>
                    <span className="arrow">→</span>
                    <span className="pout">ออก {x.exit_ts ? fmtHM(x.exit_ts) : x.status === "อยู่ในพื้นที่" ? "ยังอยู่" : "—"}</span>
                    <span className="muted"> · {x.status === "ไม่พบการเข้า" || x.status === "ไม่พบการออก" ? x.status : `อยู่ ${fmtDuration(x.duration_sec)}`}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          {v.stats_30d && (
            <section className="detail-sec">
              <h3>สถิติ 30 วัน</h3>
              <div className="mini-stats">
                <div><b>{v.stats_30d.entries}</b><span>ครั้งที่เข้า</span></div>
                <div><b>{v.stats_30d.exits}</b><span>ครั้งที่ออก</span></div>
                <div><b>{v.stats_30d.days_seen}</b><span>วันที่พบ</span></div>
                <div><b>{fmtDuration(v.stats_30d.avg_duration_sec)}</b><span>อยู่เฉลี่ย</span></div>
              </div>
            </section>
          )}
        </>
      )}

      <div className="detail-actions">
        {v && <button className="btn" onClick={() => setEdit("history")}><Icon name="history" size={16} /> ดูประวัติทั้งหมด</button>}
        {isAdmin && v && <button className="btn" onClick={() => setEdit("vehicle")}><Icon name="car" size={16} /> แก้ไขข้อมูลรถ</button>}
        {isAdmin && <button className="btn" onClick={() => setEdit("plate")}><Icon name="edit" size={16} /> แก้ไขทะเบียนที่อ่านผิด</button>}
      </div>
      {isAdmin && e.plate_norm && (!v || v.status === "ไม่รู้จัก") && (
        <div className="quick">
          <span className="muted small">ตั้งสถานะรถคันนี้:</span>
          <button className="btn btn-sm" onClick={() => quickStatus("สมาชิก")}>สมาชิก</button>
          <button className="btn btn-sm" onClick={() => quickStatus("ผู้มาเยือน")}>ผู้มาเยือน</button>
          <button className="btn btn-sm btn-warn" onClick={() => quickStatus("เฝ้าระวัง")}>เฝ้าระวัง</button>
        </div>
      )}
      {box === "image" && <Lightbox src={view === "plate" && e.has_plate ? media(e.id, "plate", bust) : media(e.id, "full", bust)} onClose={() => setBox(null)} />}
      {box === "clip" && <Lightbox src={media(e.id, "clip")} video onClose={() => setBox(null)} />}
      {edit === "plate" && <EditPlateModal event={e} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }}
        onDeleted={() => { setEdit(null); onDeleted?.(); }} />}
      {edit === "vehicle" && v && <EditVehicleModal vehicle={v} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
      {edit === "history" && v && <HistoryModal vehicle={v} onClose={() => setEdit(null)} />}
    </div>
  );
}

export function EditPlateModal({ event, onClose, onSaved, onDeleted }: {
  event: LprEvent; onClose: () => void; onSaved: () => void; onDeleted?: () => void;
}) {
  const { toast } = useStore();
  const [plate, setPlate] = useState(event.plate_display);
  const [province, setProvince] = useState(event.province);
  const [vtype, setVtype] = useState(event.vehicle_type);
  const [direction, setDirection] = useState(event.direction);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api.patch(`/api/events/${event.id}`, { plate, province, vehicle_type: vtype, direction });
      toast("บันทึกการแก้ไขแล้ว");
      onSaved();
    } catch (e) { toast((e as Error).message, "error"); } finally { setBusy(false); }
  };
  const del = async () => {
    if (!confirm("ลบเหตุการณ์นี้และภาพทั้งหมด?")) return;
    try { await api.del(`/api/events/${event.id}`); toast("ลบแล้ว"); onDeleted?.(); } catch (e) { toast((e as Error).message, "error"); }
  };
  return (
    <Modal title="แก้ไขทะเบียนที่อ่านผิด" onClose={onClose} footer={<>
      {onDeleted && <button className="btn btn-danger" onClick={del}><Icon name="trash" size={16} /> ลบเหตุการณ์</button>}
      <span className="spacer" />
      <button className="btn" onClick={onClose}>ยกเลิก</button>
      <button className="btn btn-primary" onClick={save} disabled={busy}>บันทึก</button>
    </>}>
      {event.has_plate && <img className="edit-plate-img" src={media(event.id, "plate")} alt="ภาพป้ายที่ครอปจากกล้อง" />}
      {event.alternatives?.length > 1 && (
        <div className="alts">
          <span className="muted small">ผลอ่านจากหลายเฟรม:</span>
          {event.alternatives.map((a) => (
            <button key={a.plate_norm} className="btn btn-sm" onClick={() => setPlate(a.display || a.plate_norm)}>
              {a.display || a.plate_norm} <span className="muted">{Math.round(a.share * 100)}%</span>
            </button>
          ))}
        </div>
      )}
      <div className="grid2">
        <Field label="ทะเบียน" hint="เช่น 1กข 4521 หรือ 70-4518">
          <input className="input input-plate" value={plate} onChange={(e) => setPlate(e.target.value)} />
        </Field>
        <Field label="จังหวัด"><ProvinceInput value={province} onChange={setProvince} /></Field>
        <Field label="ประเภทรถ">
          <select className="input" value={vtype} onChange={(e) => setVtype(e.target.value)}>
            {VEHICLE_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </Field>
        <Field label="ทิศทาง">
          <select className="input" value={direction} onChange={(e) => setDirection(e.target.value as "เข้า" | "ออก")}>
            <option>เข้า</option><option>ออก</option>
          </select>
        </Field>
      </div>
      <p className="muted small">อ่านได้จริง: {event.plate_raw || "-"} · ใช้ {event.frames_used} เฟรม</p>
    </Modal>
  );
}

export const PROVINCES = ["กรุงเทพมหานคร", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร", "ขอนแก่น", "จันทบุรี", "ฉะเชิงเทรา",
  "ชลบุรี", "ชัยนาท", "ชัยภูมิ", "ชุมพร", "เชียงราย", "เชียงใหม่", "ตรัง", "ตราด", "ตาก", "นครนายก", "นครปฐม", "นครพนม",
  "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส", "น่าน", "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี",
  "ประจวบคีรีขันธ์", "ปราจีนบุรี", "ปัตตานี", "พระนครศรีอยุธยา", "พะเยา", "พังงา", "พัทลุง", "พิจิตร", "พิษณุโลก",
  "เพชรบุรี", "เพชรบูรณ์", "แพร่", "ภูเก็ต", "มหาสารคาม", "มุกดาหาร", "แม่ฮ่องสอน", "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง",
  "ระยอง", "ราชบุรี", "ลพบุรี", "ลำปาง", "ลำพูน", "เลย", "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล", "สมุทรปราการ",
  "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว", "สระบุรี", "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี", "สุราษฎร์ธานี", "สุรินทร์",
  "หนองคาย", "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ", "อุดรธานี", "อุตรดิตถ์", "อุทัยธานี", "อุบลราชธานี", "เบตง"];

export function ProvinceInput({ value, onChange, id }: { value: string; onChange: (v: string) => void; id?: string }) {
  return (
    <>
      <input className="input" list="provinces" value={value} onChange={(e) => onChange(e.target.value)} id={id}
        placeholder="พิมพ์เพื่อค้นหา" />
      <datalist id="provinces">{PROVINCES.map((p) => <option key={p} value={p} />)}</datalist>
    </>
  );
}

export function EditVehicleModal({ vehicle, onClose, onSaved, isNew = false }: {
  vehicle: Partial<Vehicle>; onClose: () => void; onSaved: (v: Vehicle) => void; isNew?: boolean;
}) {
  const { toast } = useStore();
  const [f, setF] = useState({
    plate: vehicle.plate_display || "", province: vehicle.province || "", vehicle_type: vehicle.vehicle_type || "",
    status: vehicle.status || "สมาชิก", owner_name: vehicle.owner_name || "", house_no: vehicle.house_no || "",
    phone: vehicle.phone || "", note: vehicle.note || "",
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try {
      const v = isNew ? await api.post<Vehicle>("/api/vehicles", f) : await api.patch<Vehicle>(`/api/vehicles/${vehicle.id}`, f);
      toast("บันทึกข้อมูลรถแล้ว");
      onSaved(v);
    } catch (e) { toast((e as Error).message, "error"); }
  };
  return (
    <Modal title={isNew ? "เพิ่มรถ" : `แก้ไขข้อมูลรถ ${vehicle.plate_display}`} onClose={onClose} footer={<>
      <span className="spacer" /><button className="btn" onClick={onClose}>ยกเลิก</button>
      <button className="btn btn-primary" onClick={save}>บันทึก</button></>}>
      <div className="grid2">
        <Field label="ทะเบียน"><input className="input input-plate" value={f.plate} onChange={set("plate")} /></Field>
        <Field label="จังหวัด"><ProvinceInput value={f.province} onChange={(v) => setF({ ...f, province: v })} /></Field>
        <Field label="สถานะ">
          <select className="input" value={f.status} onChange={set("status")}>
            {VEHICLE_STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </Field>
        <Field label="ประเภทรถ" hint="ว่าง = ใช้ผลที่ระบบตรวจได้">
          <select className="input" value={f.vehicle_type} onChange={set("vehicle_type")}>
            <option value="">(อัตโนมัติ)</option>
            {VEHICLE_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </Field>
        <Field label="เจ้าของ"><input className="input" value={f.owner_name} onChange={set("owner_name")} /></Field>
        <Field label="บ้านเลขที่"><input className="input" value={f.house_no} onChange={set("house_no")} /></Field>
        <Field label="โทรศัพท์"><input className="input" type="tel" value={f.phone} onChange={set("phone")} /></Field>
        <Field label="หมายเหตุ"><input className="input" value={f.note} onChange={set("note")} /></Field>
      </div>
    </Modal>
  );
}

export function HistoryModal({ vehicle, onClose }: { vehicle: Vehicle; onClose: () => void }) {
  const [events, setEvents] = useState<LprEvent[] | null>(null);
  const [visits, setVisits] = useState<Visit[]>([]);
  const [tab, setTab] = useState<"events" | "visits">("visits");
  useEffect(() => {
    api.get<{ items: LprEvent[] }>("/api/events", { vehicle_id: vehicle.id, limit: 500 }).then((r) => setEvents(r.items));
    api.get<{ items: Visit[] }>(`/api/vehicles/${vehicle.id}/visits`, { limit: 500 }).then((r) => setVisits(r.items));
  }, [vehicle.id]);
  return (
    <Modal title={`ประวัติ ${vehicle.plate_display} ${vehicle.province}`} onClose={onClose} wide>
      <div className="seg" role="tablist">
        <button className={tab === "visits" ? "on" : ""} onClick={() => setTab("visits")}>การเข้า-ออก ({visits.length})</button>
        <button className={tab === "events" ? "on" : ""} onClick={() => setTab("events")}>เหตุการณ์ ({events?.length ?? "…"})</button>
      </div>
      {tab === "visits" ? (
        <table className="table">
          <thead><tr><th>วันที่</th><th>เข้า</th><th>ออก</th><th>อยู่</th><th>สถานะ</th></tr></thead>
          <tbody>{visits.map((x) => (
            <tr key={x.id}>
              <td>{fmtDate(x.entry_ts || x.exit_ts || 0)}</td>
              <td className="mono">{x.entry_ts ? fmtHM(x.entry_ts) : "—"}</td>
              <td className="mono">{x.exit_ts ? fmtHM(x.exit_ts) : "—"}</td>
              <td>{fmtDuration(x.duration_sec)}</td><td>{x.status}</td>
            </tr>))}</tbody>
        </table>
      ) : (
        <table className="table">
          <thead><tr><th>วันที่</th><th>เวลา</th><th>ทิศทาง</th><th>ทะเบียน</th><th>กล้อง</th><th>ความแม่นยำ</th></tr></thead>
          <tbody>{(events || []).map((e) => (
            <tr key={e.id}>
              <td>{fmtDate(e.ts)}</td><td className="mono">{fmtTime(e.ts)}</td><td><DirTag dir={e.direction} /></td>
              <td><PlateChip display={e.plate_display} bg={e.plate_bg} fg={e.plate_fg} size="sm" /></td>
              <td>{e.camera_name}</td><td>{Math.round(e.ocr_confidence * 100)}%</td>
            </tr>))}</tbody>
        </table>
      )}
    </Modal>
  );
}
