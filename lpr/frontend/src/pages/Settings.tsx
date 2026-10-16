import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Icon } from "../components/Icons";
import { Field, Modal } from "../components/Modal";
import { fmtBytes, fmtDateTime } from "../format";
import { useStore } from "../store";
import type { SettingItem } from "../types";

const EXTRA = ["ผู้ใช้", "บันทึกการใช้งาน", "ระบบ", "บัญชีของฉัน"] as const;

export function Settings() {
  const { isAdmin, toast, refreshSystem, refreshAuth } = useStore();
  const [items, setItems] = useState<SettingItem[]>([]);
  const [vals, setVals] = useState<Record<string, unknown>>({});
  const [meta, setMeta] = useState<{ home: string; backup_dir: string; restart_required: string[] }>({ home: "", backup_dir: "", restart_required: [] });
  const groups = useMemo(() => [...new Set(items.map((i) => i.group))], [items]);
  const [tab, setTab] = useState<string>("");
  const load = useCallback(() => {
    api.get<{ items: SettingItem[]; home: string; backup_dir: string; restart_required: string[] }>("/api/settings").then((r) => {
      setItems(r.items);
      setVals(Object.fromEntries(r.items.map((i) => [i.key, i.value])));
      setMeta(r);
      setTab((t) => t || r.items[0]?.group || "บัญชีของฉัน");
    });
  }, []);
  useEffect(load, [load]);
  const dirty = items.filter((i) => vals[i.key] !== i.value && !(i.secret && !vals[i.key]));
  const save = async () => {
    try {
      const body = Object.fromEntries(dirty.map((i) => [i.key, vals[i.key]]));
      const r = await api.put<{ changed: string[]; restart_required: string[] }>("/api/settings", body);
      toast(r.changed.length ? `บันทึก ${r.changed.length} รายการแล้ว` : "ไม่มีการเปลี่ยนแปลง");
      if (body.house_name !== undefined) refreshAuth();
      refreshSystem();
      load();
    } catch (e) { toast((e as Error).message, "error"); }
  };
  const tabs = isAdmin ? [...groups, ...EXTRA] : [...groups, "บัญชีของฉัน"];
  return (
    <div className="page">
      <div className="page-head">
        <div className="page-title"><h1>ตั้งค่า</h1><p className="muted">ทุกค่าที่ปรับได้ของระบบอยู่ที่นี่</p></div>
      </div>
      <div className="settings">
        <nav className="card settings-nav" aria-label="หมวดการตั้งค่า">
          {tabs.map((t) => <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t}</button>)}
        </nav>
        <div className="settings-body">
          {groups.includes(tab) && (
            <div className="card">
              <h2>{tab}</h2>
              <div className="settings-form">
                {items.filter((i) => i.group === tab).map((i) => (
                  <SettingField key={i.key} item={i} value={vals[i.key]} disabled={!isAdmin}
                    onChange={(v) => setVals({ ...vals, [i.key]: v })} />
                ))}
              </div>
              {tab.startsWith("การเก็บข้อมูล") && isAdmin && <StoragePanel home={meta.home} backupDir={meta.backup_dir} />}
              {tab === "การแจ้งเตือน" && <NotifyPanel isAdmin={isAdmin} />}
              {isAdmin && (
                <div className="settings-save">
                  {dirty.length > 0 && <span className="muted">แก้ไข {dirty.length} รายการ (ยังไม่บันทึก)</span>}
                  <button className="btn" onClick={() => setVals(Object.fromEntries(items.map((i) => [i.key, i.value])))} disabled={!dirty.length}>ยกเลิก</button>
                  <button className="btn btn-primary" onClick={save} disabled={!dirty.length}>บันทึก</button>
                </div>
              )}
            </div>
          )}
          {tab === "ผู้ใช้" && <UsersPanel />}
          {tab === "บันทึกการใช้งาน" && <AuditPanel />}
          {tab === "ระบบ" && <SystemPanel />}
          {tab === "บัญชีของฉัน" && <AccountPanel />}
        </div>
      </div>
    </div>
  );
}

function SettingField({ item, value, onChange, disabled }: { item: SettingItem; value: unknown; onChange: (v: unknown) => void; disabled: boolean }) {
  const hint = [item.help, item.restart ? "มีผลหลังรีสตาร์ตโปรแกรม" : "", item.cameras ? "กล้องจะเริ่มใหม่อัตโนมัติ" : ""].filter(Boolean).join(" · ");
  if (item.type === "bool") {
    return (
      <label className="toggle-row">
        <span><span className="field-label">{item.label}</span>{hint && <span className="field-hint">{hint}</span>}</span>
        <input type="checkbox" className="switch" checked={Boolean(value)} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      </label>
    );
  }
  let input;
  if (item.type === "select") {
    input = <select className="input" value={String(value)} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      {item.options.map((o) => <option key={o} value={o}>{o}</option>)}</select>;
  } else if (item.type === "int" || item.type === "float") {
    input = <input className="input" type="number" value={String(value ?? "")} disabled={disabled}
      min={item.min ?? undefined} max={item.max ?? undefined} step={item.step ?? (item.type === "int" ? 1 : 0.01)}
      onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />;
  } else if (item.type === "time") {
    input = <input className="input" type="time" value={String(value)} disabled={disabled} onChange={(e) => onChange(e.target.value)} />;
  } else if (item.type === "secret") {
    input = <input className="input" type="password" value={String(value ?? "")} disabled={disabled} autoComplete="off"
      placeholder={item.has_value ? "•••••• (ตั้งไว้แล้ว — กรอกเพื่อเปลี่ยน)" : ""} onChange={(e) => onChange(e.target.value)} />;
  } else {
    input = <input className="input" value={String(value ?? "")} disabled={disabled} onChange={(e) => onChange(e.target.value)} />;
  }
  const range = item.min !== null && item.max !== null ? ` (${item.min}–${item.max})` : "";
  return <Field label={item.label + range} hint={hint || undefined}>{input}</Field>;
}

function StoragePanel({ home, backupDir }: { home: string; backupDir: string }) {
  const { toast } = useStore();
  const [list, setList] = useState<{ file: string; size: number; ts: number }[]>([]);
  const [path, setPath] = useState("");
  const [copy, setCopy] = useState(true);
  const load = () => api.get<{ items: { file: string; size: number; ts: number }[] }>("/api/backup/list").then((r) => setList(r.items));
  useEffect(() => { load(); }, []);
  const run = async () => { try { await api.post("/api/backup/run"); toast("สำรองข้อมูลแล้ว"); load(); } catch (e) { toast((e as Error).message, "error"); } };
  const move = async () => {
    if (!confirm(`ย้ายที่เก็บข้อมูลไปที่ ${path}? (มีผลหลังรีสตาร์ตโปรแกรม)`)) return;
    try { await api.post("/api/system/storage", { path, copy_data: copy }); toast("กำลังคัดลอกข้อมูล เสร็จแล้วกรุณารีสตาร์ตโปรแกรม", "info"); }
    catch (e) { toast((e as Error).message, "error"); }
  };
  const cleanup = async () => {
    if (!confirm("ลบภาพและข้อมูลที่เก่ากว่าระยะเก็บที่ตั้งไว้ตอนนี้เลย?")) return;
    try { const r = await api.post<{ files: number; rows: number }>("/api/maintenance/cleanup"); toast(`ลบไฟล์ ${r.files} แถว ${r.rows}`); }
    catch (e) { toast((e as Error).message, "error"); }
  };
  return (
    <div className="subpanel">
      <h3>ที่เก็บข้อมูล</h3>
      <p className="muted small">ตอนนี้: <code>{home}</code></p>
      <div className="row wrap">
        <input className="input mono grow" value={path} onChange={(e) => setPath(e.target.value)} placeholder="เช่น E:\LPR" aria-label="ตำแหน่งใหม่" />
        <label className="check"><input type="checkbox" checked={copy} onChange={(e) => setCopy(e.target.checked)} /><span>คัดลอกข้อมูลเดิมไปด้วย</span></label>
        <button className="btn" onClick={move} disabled={!path}>ย้ายที่เก็บข้อมูล</button>
      </div>
      <h3>สำรองข้อมูล</h3>
      <p className="muted small">สำรองอัตโนมัติทุกวันตามเวลาที่ตั้ง ไปที่ <code>{backupDir}</code> (แนะนำให้เป็นไดรฟ์อื่นจากที่เก็บข้อมูล)</p>
      <div className="row"><button className="btn" onClick={run}><Icon name="download" size={16} /> สำรองข้อมูลเดี๋ยวนี้</button>
        <button className="btn" onClick={cleanup}><Icon name="trash" size={16} /> ลบข้อมูลเก่าตอนนี้</button></div>
      {list.length > 0 && <ul className="filelist">{list.slice(0, 14).map((f) => <li key={f.file}><code>{f.file}</code> <span className="muted">{fmtBytes(f.size)} · {fmtDateTime(f.ts)}</span></li>)}</ul>}
    </div>
  );
}

function urlB64ToUint8(b64: string): Uint8Array {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

function NotifyPanel({ isAdmin }: { isAdmin: boolean }) {
  const { toast } = useStore();
  const [state, setState] = useState<"unsupported" | "insecure" | "off" | "on" | "denied">("off");
  useEffect(() => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) { setState(window.isSecureContext ? "unsupported" : "insecure"); return; }
    if (Notification.permission === "denied") { setState("denied"); return; }
    navigator.serviceWorker.ready.then((r) => r.pushManager.getSubscription()).then((s) => setState(s ? "on" : "off"));
  }, []);
  const enable = async () => {
    try {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { setState("denied"); return; }
      const { public_key } = await api.get<{ public_key: string }>("/api/push/key");
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlB64ToUint8(public_key) });
      await api.post("/api/push/subscribe", sub.toJSON());
      setState("on");
      toast("เปิดการแจ้งเตือนบนอุปกรณ์นี้แล้ว");
    } catch (e) { toast(`เปิดการแจ้งเตือนไม่สำเร็จ: ${(e as Error).message}`, "error"); }
  };
  const disable = async () => {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) { await api.post("/api/push/unsubscribe", sub.toJSON()).catch(() => undefined); await sub.unsubscribe(); }
    setState("off");
  };
  const test = async (channel: string) => {
    try { const r = await api.post<{ result: string }>("/api/notify/test", { channel }); toast(`ส่งแล้ว: ${r.result}`); }
    catch (e) { toast((e as Error).message, "error"); }
  };
  return (
    <div className="subpanel">
      <h3>การแจ้งเตือนบนอุปกรณ์นี้ (Web Push)</h3>
      {state === "insecure" && <p className="muted small">ต้องเปิดผ่าน HTTPS (เช่นลิงก์ Tailscale https://…ts.net) จึงจะรับแจ้งเตือนได้ — ดูคู่มือ docs/mobile-setup.md</p>}
      {state === "unsupported" && <p className="muted small">เบราว์เซอร์นี้ไม่รองรับ Web Push (iPhone/iPad ต้องเพิ่มลงหน้าจอโฮมก่อน แล้วเปิดจากไอคอน)</p>}
      {state === "denied" && <p className="muted small">การแจ้งเตือนถูกปิดในเบราว์เซอร์ กรุณาเปิดในการตั้งค่าของเบราว์เซอร์</p>}
      <div className="row wrap">
        {state === "off" && <button className="btn btn-primary" onClick={enable}><Icon name="bell" size={16} /> เปิดการแจ้งเตือนบนอุปกรณ์นี้</button>}
        {state === "on" && <><span className="badge st-member">เปิดอยู่</span><button className="btn" onClick={disable}>ปิดการแจ้งเตือนบนอุปกรณ์นี้</button></>}
        {isAdmin && <>
          <button className="btn" onClick={() => test("webpush")}>ทดสอบ Web Push</button>
          <button className="btn" onClick={() => test("telegram")}>ทดสอบ Telegram</button>
          <button className="btn" onClick={() => test("line")}>ทดสอบ LINE</button>
        </>}
      </div>
      <p className="muted small">Telegram: สร้างบอทกับ @BotFather รับ token แล้วส่งข้อความหาบอทหนึ่งครั้ง จากนั้นหา chat id จาก https://api.telegram.org/bot&lt;token&gt;/getUpdates ·
        LINE: สร้าง Messaging API channel ใน LINE Developers แล้วใช้ Channel access token และ user id ของคุณ (LINE Notify ปิดบริการแล้ว)</p>
    </div>
  );
}

interface U { id: number; username: string; role: string; display_name: string; created_at: number }

function UsersPanel() {
  const { toast, me } = useStore();
  const [users, setUsers] = useState<U[]>([]);
  const [edit, setEdit] = useState<Partial<U> & { password?: string } | null>(null);
  const load = () => api.get<{ items: U[] }>("/api/users").then((r) => setUsers(r.items));
  useEffect(() => { load(); }, []);
  const save = async () => {
    if (!edit) return;
    try {
      if (edit.id) await api.patch(`/api/users/${edit.id}`, { role: edit.role, display_name: edit.display_name, password: edit.password || undefined });
      else await api.post("/api/users", edit);
      toast("บันทึกผู้ใช้แล้ว");
      setEdit(null);
      load();
    } catch (e) { toast((e as Error).message, "error"); }
  };
  const del = async (u: U) => {
    if (!confirm(`ลบผู้ใช้ ${u.username}?`)) return;
    try { await api.del(`/api/users/${u.id}`); load(); } catch (e) { toast((e as Error).message, "error"); }
  };
  return (
    <div className="card">
      <div className="toolbar"><h2>ผู้ใช้</h2><button className="btn btn-primary" onClick={() => setEdit({ role: "viewer" })}><Icon name="plus" size={16} /> เพิ่มผู้ใช้</button></div>
      <p className="muted small">admin = แก้ไขได้ทุกอย่าง · viewer = ดูอย่างเดียว</p>
      <table className="table">
        <thead><tr><th>ชื่อผู้ใช้</th><th>ชื่อที่แสดง</th><th>สิทธิ์</th><th>สร้างเมื่อ</th><th /></tr></thead>
        <tbody>{users.map((u) => (
          <tr key={u.id}><td>{u.username}</td><td>{u.display_name}</td><td><span className="badge">{u.role}</span></td>
            <td>{u.created_at ? fmtDateTime(u.created_at) : "-"}</td>
            <td className="row-actions"><button className="icon-btn" onClick={() => setEdit(u)} aria-label="แก้ไข"><Icon name="edit" /></button>
              {u.id !== me?.id && <button className="icon-btn danger" onClick={() => del(u)} aria-label="ลบ"><Icon name="trash" /></button>}</td></tr>
        ))}</tbody>
      </table>
      {edit && (
        <Modal title={edit.id ? `แก้ไขผู้ใช้ ${edit.username}` : "เพิ่มผู้ใช้"} onClose={() => setEdit(null)} footer={<><span className="spacer" />
          <button className="btn" onClick={() => setEdit(null)}>ยกเลิก</button><button className="btn btn-primary" onClick={save}>บันทึก</button></>}>
          {!edit.id && <Field label="ชื่อผู้ใช้"><input className="input" value={edit.username || ""} onChange={(e) => setEdit({ ...edit, username: e.target.value })} /></Field>}
          <Field label="ชื่อที่แสดง"><input className="input" value={edit.display_name || ""} onChange={(e) => setEdit({ ...edit, display_name: e.target.value })} /></Field>
          <Field label="สิทธิ์"><select className="input" value={edit.role} onChange={(e) => setEdit({ ...edit, role: e.target.value })}>
            <option value="viewer">viewer (ดูอย่างเดียว)</option><option value="admin">admin (แก้ไขได้)</option></select></Field>
          <Field label={edit.id ? "รหัสผ่านใหม่ (เว้นว่าง = ไม่เปลี่ยน)" : "รหัสผ่าน"} hint="อย่างน้อย 6 ตัวอักษร">
            <input className="input" type="password" autoComplete="new-password" value={edit.password || ""} onChange={(e) => setEdit({ ...edit, password: e.target.value })} /></Field>
        </Modal>
      )}
    </div>
  );
}

function AuditPanel() {
  const [rows, setRows] = useState<{ id: number; ts: number; user: string; action: string; detail: string }[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  useEffect(() => { api.get<{ items: typeof rows; total: number }>("/api/audit", { page, size: 100 }).then((r) => { setRows(r.items); setTotal(r.total); }); }, [page]);
  return (
    <div className="card">
      <h2>บันทึกการใช้งาน</h2>
      <p className="muted small">บันทึกทุกการแก้ไข ลบ ส่งออกข้อมูล และการเข้าสู่ระบบ</p>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>เวลา</th><th>ผู้ใช้</th><th>การกระทำ</th><th>รายละเอียด</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id}><td className="nowrap">{fmtDateTime(r.ts)}</td><td>{r.user}</td><td>{r.action}</td><td className="small">{r.detail}</td></tr>)}</tbody>
      </table></div>
      <div className="pager">
        <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>ก่อนหน้า</button>
        <span>หน้า {page} / {Math.max(1, Math.ceil(total / 100))}</span>
        <button className="btn btn-sm" disabled={page * 100 >= total} onClick={() => setPage(page + 1)}>ถัดไป</button>
      </div>
    </div>
  );
}

function SystemPanel() {
  const { system, refreshSystem } = useStore();
  useEffect(() => { refreshSystem(); }, [refreshSystem]);
  if (!system) return null;
  return (
    <div className="card">
      <h2>ระบบ</h2>
      <dl className="kv kv-wide">
        <div><dt>เวอร์ชัน</dt><dd>{system.app} {system.version}</dd></div>
        <div><dt>ที่เก็บข้อมูล</dt><dd><code>{system.home}</code></dd></div>
        <div><dt>พื้นที่ดิสก์</dt><dd>ว่าง {fmtBytes(system.disk.free)} จาก {fmtBytes(system.disk.total)} ({system.disk.free_percent}%)</dd></div>
        <div><dt>ที่เก็บรหัสผ่านกล้อง</dt><dd>{system.credentials}</dd></div>
        <div><dt>ตัวประมวลผลโมเดล</dt><dd>{(system.providers || []).map((p) => p.replace("ExecutionProvider", "")).join(", ")}</dd></div>
        <div><dt>การ์ดจอ</dt><dd>{system.gpus?.length ? system.gpus.join(", ") : "ไม่พบ (ใช้ CPU)"}</dd></div>
        <div><dt>ไฟล์โมเดล</dt><dd>{Object.entries(system.models || {}).map(([k, v]) => `${k} ${v ? "✓" : "✗"}`).join(" · ")}</dd></div>
        <div><dt>สำรองข้อมูลล่าสุด</dt><dd>{system.last_backup?.ts ? fmtDateTime(system.last_backup.ts) : "ยังไม่มีในรอบนี้"}</dd></div>
      </dl>
      <h3>กล้อง</h3>
      <ul className="filelist">{system.cameras.map((c) => <li key={c.id}>{c.name} — {c.status.state_th}{c.status.error ? ` (${c.status.error})` : ""}
        {c.status.ocr ? ` · ${c.status.ocr}` : ""}{c.status.device ? ` · ${c.status.device.replace("ExecutionProvider", "")}` : ""}</li>)}</ul>
    </div>
  );
}

function AccountPanel() {
  const { me, toast, logout } = useStore();
  const [a, setA] = useState(""), [b, setB] = useState(""), [c, setC] = useState("");
  const save = async () => {
    if (b !== c) { toast("รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน", "error"); return; }
    try { await api.post("/api/auth/password", { old_password: a, new_password: b }); toast("เปลี่ยนรหัสผ่านแล้ว"); setA(""); setB(""); setC(""); }
    catch (e) { toast((e as Error).message, "error"); }
  };
  return (
    <div className="card">
      <h2>บัญชีของฉัน</h2>
      <p>{me?.display_name} ({me?.username}) · สิทธิ์ {me?.role}</p>
      <div className="settings-form narrow">
        <Field label="รหัสผ่านเดิม"><input className="input" type="password" value={a} onChange={(e) => setA(e.target.value)} autoComplete="current-password" /></Field>
        <Field label="รหัสผ่านใหม่"><input className="input" type="password" value={b} onChange={(e) => setB(e.target.value)} autoComplete="new-password" /></Field>
        <Field label="ยืนยันรหัสผ่านใหม่"><input className="input" type="password" value={c} onChange={(e) => setC(e.target.value)} autoComplete="new-password" /></Field>
      </div>
      <div className="row"><button className="btn btn-primary" onClick={save} disabled={!a || !b}>เปลี่ยนรหัสผ่าน</button>
        <button className="btn" onClick={logout}><Icon name="logout" size={16} /> ออกจากระบบ</button></div>
    </div>
  );
}
