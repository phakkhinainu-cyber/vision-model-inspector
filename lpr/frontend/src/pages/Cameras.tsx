import { useCallback, useEffect, useRef, useState, type PointerEvent as RPointerEvent } from "react";
import { api } from "../api";
import { ProvinceInput } from "../components/EventDetail";
import { Icon } from "../components/Icons";
import { Empty, Field, Modal } from "../components/Modal";
import { fmtAgo } from "../format";
import { useLive, useStore } from "../store";
import { CAMERA_ROLES, VEHICLE_TYPES, type Camera } from "../types";

export function Cameras() {
  const { isAdmin, toast } = useStore();
  const [cams, setCams] = useState<Camera[] | null>(null);
  const [edit, setEdit] = useState<Partial<Camera> | null>(null);
  const [manual, setManual] = useState<Camera | null>(null);
  const [live, setLive] = useState<Record<number, boolean>>({});
  const load = useCallback(() => { api.get<{ items: Camera[] }>("/api/cameras").then((r) => setCams(r.items)); }, []);
  useEffect(load, [load]);
  useLive((m) => {
    if (m.type === "camera_status") setCams((cs) => cs && cs.map((c) => (c.id === m.camera_id ? { ...c, status: m.status } : c)));
  });
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); toast(ok); load(); } catch (e) { toast((e as Error).message, "error"); }
  };
  return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">
          <h1>กล้อง</h1>
          <p className="muted">รองรับ 1–8 ตัว · ใช้ไฟล์วิดีโอแทนกล้องได้ (โหมดจำลอง)</p>
        </div>
        {isAdmin && (cams?.length || 0) < 8 && (
          <div className="head-actions">
            <button className="btn btn-primary" onClick={() => setEdit({ role: "สองทาง", enabled: true, line_direction: "pos_in", roi_polygon: [], line_coords: [] })}>
              <Icon name="plus" size={16} /> เพิ่มกล้อง
            </button>
          </div>
        )}
      </div>
      {!cams ? <div className="skeleton" style={{ height: 240 }} /> : cams.length === 0 ? (
        <div className="card"><Empty icon="camera" title="ยังไม่มีกล้อง" text="กด เพิ่มกล้อง แล้วกรอกลิงก์ RTSP จากคู่มือหรือแอปของกล้อง หรือเลือก ใช้วิดีโอตัวอย่าง เพื่อทดลองระบบ" /></div>
      ) : (
        <div className="cam-grid">
          {cams.map((c) => {
            const st = c.status;
            const on = live[c.id] ?? c.enabled;
            return (
              <article key={c.id} className="card cam-card">
                <div className="cam-view">
                  {on && c.enabled && st.state === "online" ? <img src={`/api/cameras/${c.id}/live.mjpg`} alt={`ภาพสด ${c.name}`} />
                    : <div className="cam-off"><Icon name={st.state === "error" ? "alert" : "camera"} size={32} />
                      <span>{!c.enabled ? "ปิดใช้งาน" : st.state === "online" ? "ซ่อนภาพสด" : st.state_th}</span>
                      {st.error && <small>{st.error}</small>}</div>}
                  <span className={`cam-state s-${st.state}`}>{st.state_th}{st.night ? " · กลางคืน" : ""}</span>
                </div>
                <div className="cam-body">
                  <div className="cam-title">
                    <h2>{c.name}</h2>
                    <span className="badge">{c.role}</span>
                  </div>
                  <div className="cam-stats">
                    <span title="เฟรมต่อวินาที">{st.fps ?? 0} fps</span>
                    {st.size && st.size[0] > 0 && <span>{st.size[0]}×{st.size[1]}</span>}
                    <span title="รถที่กำลังติดตาม">รถในภาพ {st.tracks ?? 0}</span>
                    <span>บันทึก {st.events ?? 0} · ล่าสุด {fmtAgo(st.last_event_ts)}</span>
                    {st.ocr && <span title="OCR / อุปกรณ์">{st.ocr} · {st.device?.replace("ExecutionProvider", "")}</span>}
                    {(st.restarts || 0) > 0 && <span className="warn">รีสตาร์ต {st.restarts} ครั้ง</span>}
                  </div>
                  <div className="cam-actions">
                    {c.enabled && st.state === "online" && (
                      <button className="btn btn-sm" onClick={() => setLive({ ...live, [c.id]: !on })}>{on ? "ซ่อนภาพสด" : "ดูภาพสด"}</button>
                    )}
                    {isAdmin && c.enabled && (
                      <button className="btn btn-sm btn-primary" onClick={() => act(() => api.post(`/api/cameras/${c.id}/capture`, {}), "จับภาพแล้ว ดูผลในสมุดบันทึก")}>
                        <Icon name="zap" size={14} /> จับภาพเดี๋ยวนี้
                      </button>
                    )}
                    {isAdmin && <button className="btn btn-sm" onClick={() => setManual(c)}><Icon name="edit" size={14} /> บันทึกด้วยมือ</button>}
                    {isAdmin && <button className="btn btn-sm" onClick={() => setEdit(c)}><Icon name="settings" size={14} /> ตั้งค่า/วาดโซน</button>}
                    {isAdmin && c.enabled && <button className="icon-btn" title="รีสตาร์ตกล้อง" aria-label="รีสตาร์ตกล้อง"
                      onClick={() => act(() => api.post(`/api/cameras/${c.id}/restart`), "กำลังรีสตาร์ตกล้อง")}><Icon name="refresh" /></button>}
                    {isAdmin && <button className="icon-btn danger" aria-label="ลบกล้อง"
                      onClick={() => confirm(`ลบกล้อง ${c.name}?`) && act(() => api.del(`/api/cameras/${c.id}`), "ลบกล้องแล้ว")}><Icon name="trash" /></button>}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
      {edit && <CameraEditor cam={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
      {manual && <ManualRecord cam={manual} onClose={() => setManual(null)} />}
    </div>
  );
}

function ManualRecord({ cam, onClose }: { cam: Camera; onClose: () => void }) {
  const { toast } = useStore();
  const [f, setF] = useState({ plate: "", province: "", direction: cam.role === "ทางออก" ? "ออก" : "เข้า", vehicle_type: "รถเก๋ง", note: "" });
  const save = async () => {
    try {
      await api.post("/api/events/manual", { ...f, camera_id: cam.id, snapshot: cam.enabled });
      toast("บันทึกด้วยมือแล้ว");
      onClose();
    } catch (e) { toast((e as Error).message, "error"); }
  };
  return (
    <Modal title={`บันทึกด้วยมือ · ${cam.name}`} onClose={onClose} footer={<><span className="spacer" />
      <button className="btn" onClick={onClose}>ยกเลิก</button><button className="btn btn-primary" onClick={save}>บันทึก</button></>}>
      <p className="muted small">ใช้ในกรณีพิเศษ เช่น กล้องอ่านไม่ได้หรือรถเข้าทางอื่น ระบบจะแนบภาพปัจจุบันจากกล้องให้</p>
      <div className="grid2">
        <Field label="ทะเบียน"><input className="input input-plate" value={f.plate} onChange={(e) => setF({ ...f, plate: e.target.value })} placeholder="1กข 4521" /></Field>
        <Field label="จังหวัด"><ProvinceInput value={f.province} onChange={(v) => setF({ ...f, province: v })} /></Field>
        <Field label="ทิศทาง">
          <select className="input" value={f.direction} onChange={(e) => setF({ ...f, direction: e.target.value })}><option>เข้า</option><option>ออก</option></select>
        </Field>
        <Field label="ประเภทรถ">
          <select className="input" value={f.vehicle_type} onChange={(e) => setF({ ...f, vehicle_type: e.target.value })}>{VEHICLE_TYPES.map((t) => <option key={t}>{t}</option>)}</select>
        </Field>
      </div>
      <Field label="หมายเหตุ"><input className="input" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
    </Modal>
  );
}

type Pt = [number, number];

function CameraEditor({ cam, onClose, onSaved }: { cam: Partial<Camera>; onClose: () => void; onSaved: () => void }) {
  const { toast, system } = useStore();
  const isNew = !cam.id;
  const [f, setF] = useState({
    name: cam.name || "", rtsp_main: cam.rtsp_main || "", rtsp_sub: cam.rtsp_sub || "", username: cam.username || "",
    password: "", role: cam.role || "สองทาง", enabled: cam.enabled ?? true, line_direction: cam.line_direction || "pos_in",
  });
  const [roi, setRoi] = useState<Pt[]>((cam.roi_polygon || []) as Pt[]);
  const [line, setLine] = useState<Pt[]>((cam.line_coords || []) as Pt[]);
  const [mode, setMode] = useState<"roi" | "line">("line");
  const [img, setImg] = useState<string>(cam.id ? `/api/cameras/${cam.id}/snapshot.jpg?t=${Date.now()}` : "");
  const [imgErr, setImgErr] = useState("");
  const [testing, setTesting] = useState(false);
  const [testMsg, setTestMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const demo = (system as unknown as { demo_video?: string })?.demo_video;

  const test = async () => {
    setTesting(true);
    setTestMsg("");
    try {
      const r = await api.post<{ ok: boolean; error?: string; width?: number; height?: number; fps?: number; image?: string; seconds?: number }>(
        "/api/cameras/test", { url: f.rtsp_main, username: f.username, password: f.password, camera_id: cam.id ?? null });
      if (r.ok) {
        setTestMsg(`เชื่อมต่อสำเร็จ · ${r.width}×${r.height}${r.fps ? ` · ${Math.round(r.fps)} fps` : ""} · ${r.seconds} วินาที`);
        if (r.image) { setImg(r.image); setImgErr(""); }
      } else setTestMsg(`✗ ${r.error}`);
    } catch (e) { setTestMsg(`✗ ${(e as Error).message}`); } finally { setTesting(false); }
  };

  const save = async () => {
    setBusy(true);
    const body: Record<string, unknown> = { ...f, roi_polygon: roi, line_coords: line };
    if (!f.password) delete body.password;
    try {
      if (isNew) await api.post("/api/cameras", body);
      else await api.patch(`/api/cameras/${cam.id}`, body);
      toast("บันทึกกล้องแล้ว ระบบจะเชื่อมต่อใหม่อัตโนมัติ");
      onSaved();
    } catch (e) { toast((e as Error).message, "error"); } finally { setBusy(false); }
  };

  return (
    <Modal title={isNew ? "เพิ่มกล้อง" : `ตั้งค่ากล้อง ${cam.name}`} onClose={onClose} wide footer={<>
      <label className="check"><input type="checkbox" checked={f.enabled} onChange={(e) => setF({ ...f, enabled: e.target.checked })} /><span>เปิดใช้งาน</span></label>
      <span className="spacer" />
      <button className="btn" onClick={onClose}>ยกเลิก</button>
      <button className="btn btn-primary" onClick={save} disabled={busy || !f.rtsp_main}>บันทึก</button>
    </>}>
      <div className="cam-editor">
        <div className="cam-form">
          <Field label="ชื่อกล้อง"><input className="input" value={f.name} onChange={set("name")} placeholder="เช่น CAM 1 ประตูหน้า" /></Field>
          <Field label="ลิงก์ RTSP (main-stream) หรือไฟล์วิดีโอ" hint="เช่น rtsp://192.168.1.20:554/Streaming/Channels/101">
            <input className="input mono" value={f.rtsp_main} onChange={set("rtsp_main")} spellCheck={false} />
          </Field>
          {demo && <button className="btn btn-sm" type="button" onClick={() => setF({ ...f, rtsp_main: demo, name: f.name || "กล้องจำลอง" })}>
            <Icon name="play" size={14} /> ใช้วิดีโอตัวอย่าง (โหมดจำลอง)</button>}
          <Field label="ลิงก์ sub-stream (ไม่บังคับ)" hint="ภาพความละเอียดต่ำสำหรับตรวจจับ ช่วยประหยัด CPU">
            <input className="input mono" value={f.rtsp_sub} onChange={set("rtsp_sub")} spellCheck={false} />
          </Field>
          <div className="grid2">
            <Field label="ชื่อผู้ใช้กล้อง"><input className="input" value={f.username} onChange={set("username")} autoComplete="off" /></Field>
            <Field label="รหัสผ่านกล้อง" hint="เก็บแบบเข้ารหัสใน Windows Credential Manager">
              <input className="input" type="password" value={f.password} onChange={set("password")} autoComplete="new-password"
                placeholder={cam.has_password ? "•••••• (ไม่เปลี่ยน)" : ""} />
            </Field>
          </div>
          <div className="row">
            <button className="btn" type="button" onClick={test} disabled={testing || !f.rtsp_main}>
              <Icon name="refresh" size={16} /> {testing ? "กำลังทดสอบ…" : "ทดสอบการเชื่อมต่อ"}
            </button>
            {testMsg && <span className={`small ${testMsg.startsWith("✗") ? "c-out" : "c-ok"}`} role="status">{testMsg}</span>}
          </div>
          <fieldset className="facet">
            <legend>บทบาทของกล้อง</legend>
            {CAMERA_ROLES.map((r) => (
              <label key={r} className="radio"><input type="radio" name="role" checked={f.role === r} onChange={() => setF({ ...f, role: r })} />
                <span>{r}</span></label>
            ))}
            <span className="field-hint">สองทาง = ใช้ทิศที่รถข้ามเส้นเสมือนบอกว่าเข้าหรือออก</span>
          </fieldset>
        </div>
        <div className="cam-draw">
          <div className="seg" role="group" aria-label="โหมดวาด">
            <button className={mode === "line" ? "on" : ""} onClick={() => setMode("line")}>เส้นเสมือน</button>
            <button className={mode === "roi" ? "on" : ""} onClick={() => setMode("roi")}>โซน ROI</button>
          </div>
          <p className="muted small">
            {mode === "line" ? "คลิก 2 จุดเพื่อวาดเส้นที่รถต้องข้าม ลูกศรสีน้ำเงินคือทิศ เข้า" : "คลิกหลายจุดล้อมบริเวณที่ต้องการตรวจจับ (ว่าง = ทั้งภาพ) ลากจุดเพื่อปรับ"}
          </p>
          <DrawCanvas img={img} onImgError={() => setImgErr("ยังไม่มีภาพจากกล้อง กด ทดสอบการเชื่อมต่อ เพื่อดึงภาพ")}
            roi={roi} setRoi={setRoi} line={line} setLine={setLine} mode={mode} lineDir={f.line_direction} />
          {imgErr && !img.startsWith("data:") && <p className="muted small">{imgErr}</p>}
          <div className="row">
            {mode === "line" ? <>
              <button className="btn btn-sm" onClick={() => setF({ ...f, line_direction: f.line_direction === "pos_in" ? "neg_in" : "pos_in" })} disabled={line.length !== 2}>
                <Icon name="refresh" size={14} /> สลับทิศ เข้า/ออก</button>
              <button className="btn btn-sm" onClick={() => setLine([])}>ลบเส้น</button>
            </> : <>
              <button className="btn btn-sm" onClick={() => setRoi(roi.slice(0, -1))} disabled={!roi.length}>ย้อนจุดล่าสุด</button>
              <button className="btn btn-sm" onClick={() => setRoi([])}>ล้างโซน</button>
            </>}
            {cam.id && <button className="btn btn-sm" onClick={() => setImg(`/api/cameras/${cam.id}/snapshot.jpg?t=${Date.now()}`)}>ภาพใหม่</button>}
          </div>
        </div>
      </div>
    </Modal>
  );
}

function DrawCanvas({ img, onImgError, roi, setRoi, line, setLine, mode, lineDir }: {
  img: string; onImgError: () => void; roi: Pt[]; setRoi: (p: Pt[]) => void; line: Pt[]; setLine: (p: Pt[]) => void;
  mode: "roi" | "line"; lineDir: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [aspect, setAspect] = useState(16 / 9);
  const drag = useRef<{ kind: "roi" | "line"; i: number } | null>(null);
  const pos = (e: RPointerEvent): Pt => {
    const r = ref.current!.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
  };
  const down = (e: RPointerEvent) => {
    const t = e.target as SVGElement;
    if (t.dataset.kind) {
      drag.current = { kind: t.dataset.kind as "roi" | "line", i: Number(t.dataset.i) };
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      return;
    }
    const p = pos(e);
    if (mode === "roi") setRoi([...roi, p]);
    else setLine(line.length >= 2 || line.length === 0 ? [p] : [line[0], p]);
  };
  const move = (e: RPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const p = pos(e);
    if (d.kind === "roi") setRoi(roi.map((q, i) => (i === d.i ? p : q)));
    else setLine(line.map((q, i) => (i === d.i ? p : q)));
  };
  const up = () => { drag.current = null; };
  // ลูกศรทิศ เข้า (ตั้งฉากกับเส้น ไปทางด้านบวกถ้า pos_in)
  let arrow: { x1: number; y1: number; x2: number; y2: number } | null = null;
  if (line.length === 2) {
    const [[ax, ay], [bx, by]] = line;
    const mx = (ax + bx) / 2, my = (ay + by) / 2;
    let nx = -(by - ay) / aspect, ny = (bx - ax) * aspect;
    const len = Math.hypot(nx * aspect, ny) || 1;
    const s = (lineDir === "pos_in" ? 1 : -1) * 0.12 / len;
    nx *= s; ny *= s;
    arrow = { x1: mx - nx, y1: my - ny, x2: mx + nx, y2: my + ny };
  }
  return (
    <div className="draw" ref={ref} style={{ aspectRatio: String(aspect) }} onPointerDown={down} onPointerMove={move}
      onPointerUp={up} role="application" aria-label="พื้นที่วาดโซนและเส้นเสมือน">
      {img ? <img src={img} alt="ภาพจากกล้อง" draggable={false} onError={onImgError}
        onLoad={(e) => { const i = e.currentTarget; if (i.naturalWidth) setAspect(i.naturalWidth / i.naturalHeight); }} />
        : <div className="draw-empty">กด ทดสอบการเชื่อมต่อ เพื่อดึงภาพจากกล้อง</div>}
      <svg viewBox="0 0 1 1" preserveAspectRatio="none">
        <defs>
          <marker id="arr" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" fill="#1D4ED8" />
          </marker>
        </defs>
        {roi.length > 0 && <polygon points={roi.map((p) => p.join(",")).join(" ")} className="roi-poly" vectorEffect="non-scaling-stroke" />}
        {line.length === 2 && <line x1={line[0][0]} y1={line[0][1]} x2={line[1][0]} y2={line[1][1]} className="vline" vectorEffect="non-scaling-stroke" />}
        {arrow && <line {...arrow} className="varrow" markerEnd="url(#arr)" vectorEffect="non-scaling-stroke" />}
      </svg>
      {roi.map((p, i) => <span key={`r${i}`} className="handle roi" style={{ left: `${p[0] * 100}%`, top: `${p[1] * 100}%` }}>
        <svg width="16" height="16"><circle cx="8" cy="8" r="7" data-kind="roi" data-i={i} /></svg></span>)}
      {line.map((p, i) => <span key={`l${i}`} className="handle line" style={{ left: `${p[0] * 100}%`, top: `${p[1] * 100}%` }}>
        <svg width="18" height="18"><circle cx="9" cy="9" r="8" data-kind="line" data-i={i} /></svg></span>)}
      {arrow && <span className="arrow-label" style={{ left: `${arrow.x2 * 100}%`, top: `${arrow.y2 * 100}%` }}>เข้า</span>}
    </div>
  );
}
