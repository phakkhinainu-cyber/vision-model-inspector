import { useCallback, useEffect, useRef, useState } from "react";
import { api, download } from "../api";
import { EditVehicleModal, HistoryModal } from "../components/EventDetail";
import { Icon } from "../components/Icons";
import { Empty } from "../components/Modal";
import { PlateChip, StatusBadge } from "../components/Plate";
import { fmtAgo, fmtDate } from "../format";
import { useStore } from "../store";
import { VEHICLE_STATUSES, type Vehicle } from "../types";

interface ListResp { items: Vehicle[]; total: number; counts: Record<string, number> }

export function Vehicles() {
  const { isAdmin, toast } = useStore();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string>("สมาชิก,ผู้มาเยือน,เฝ้าระวัง");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ListResp | null>(null);
  const [edit, setEdit] = useState<Partial<Vehicle> | null>(null);
  const [hist, setHist] = useState<Vehicle | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const load = useCallback(() => {
    api.get<ListResp>("/api/vehicles", { q, status, page, size: 50 }).then(setData).catch((e) => toast(e.message, "error"));
  }, [q, status, page, toast]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  const importFile = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api.upload<{ added: number; updated: number; skipped: number; errors: string[] }>("/api/vehicles-import", fd);
      toast(`นำเข้าแล้ว: เพิ่ม ${r.added} แก้ไข ${r.updated} ข้าม ${r.skipped}${r.errors.length ? ` · ผิดพลาด ${r.errors.length}` : ""}`);
      load();
    } catch (e) { toast((e as Error).message, "error"); }
  };
  const remove = async (v: Vehicle) => {
    if (!confirm(`ลบรถ ${v.plate_display} ${v.province} ออกจากทะเบียน? (ประวัติเหตุการณ์ยังอยู่)`)) return;
    try { await api.del(`/api/vehicles/${v.id}`); toast("ลบแล้ว"); load(); } catch (e) { toast((e as Error).message, "error"); }
  };
  const tabs: [string, string][] = [["สมาชิก,ผู้มาเยือน,เฝ้าระวัง", "ที่ลงทะเบียน"], ...VEHICLE_STATUSES.map((s) => [s, s] as [string, string]), ["", "ทั้งหมด"]];
  const pages = data ? Math.max(1, Math.ceil(data.total / 50)) : 1;
  return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">
          <h1>ทะเบียนรถ</h1>
          <p className="muted">จัดการรายชื่อ สมาชิก / ผู้มาเยือน / เฝ้าระวัง (รถที่ระบบพบครั้งแรกจะเป็น ไม่รู้จัก)</p>
        </div>
        <div className="head-actions">
          {isAdmin && <button className="btn btn-primary" onClick={() => setEdit({ status: "สมาชิก" })}><Icon name="plus" size={16} /> เพิ่มรถ</button>}
          {isAdmin && <button className="btn" onClick={() => fileRef.current?.click()}><Icon name="upload" size={16} /> นำเข้า Excel</button>}
          <button className="btn" onClick={() => download("/api/vehicles-export.xlsx")}><Icon name="download" size={16} /> ส่งออก Excel</button>
          <input ref={fileRef} type="file" accept=".xlsx" hidden aria-label="เลือกไฟล์ Excel"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) importFile(f); e.target.value = ""; }} />
        </div>
      </div>
      <div className="card">
        <div className="toolbar">
          <span className="search"><Icon name="search" size={16} />
            <input className="input" placeholder="ค้นหาทะเบียน เจ้าของ บ้านเลขที่" value={q} aria-label="ค้นหา"
              onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          </span>
          <div className="tabs" role="tablist">
            {tabs.map(([k, l]) => (
              <button key={l} className={status === k ? "on" : ""} onClick={() => { setStatus(k); setPage(1); }}>
                {l}{data && k && !k.includes(",") ? ` (${data.counts[k] || 0})` : ""}
              </button>
            ))}
          </div>
        </div>
        {!data ? <div className="skeleton" style={{ height: 200 }} /> : data.items.length === 0 ? (
          <Empty icon="car" title="ไม่พบรถ" text={isAdmin ? "กด เพิ่มรถ หรือเพิ่มจากเหตุการณ์ในหน้าสมุดบันทึกได้ในคลิกเดียว" : undefined} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>ทะเบียน</th><th>สถานะ</th><th>ประเภท</th><th>เจ้าของ</th><th>บ้านเลขที่</th><th>โทรศัพท์</th><th>พบล่าสุด</th><th /></tr></thead>
              <tbody>{data.items.map((v) => (
                <tr key={v.id}>
                  <td><PlateChip display={v.plate_display} province={v.province} /></td>
                  <td><StatusBadge status={v.status} /></td>
                  <td>{v.vehicle_type || "-"}</td>
                  <td>{v.owner_name || "-"}</td>
                  <td>{v.house_no || "-"}</td>
                  <td>{v.phone || "-"}</td>
                  <td title={v.last_seen ? fmtDate(v.last_seen) : ""}>{fmtAgo(v.last_seen)}</td>
                  <td className="row-actions">
                    <button className="icon-btn" onClick={() => setHist(v)} aria-label="ประวัติ"><Icon name="history" /></button>
                    {isAdmin && <button className="icon-btn" onClick={() => setEdit(v)} aria-label="แก้ไข"><Icon name="edit" /></button>}
                    {isAdmin && <button className="icon-btn danger" onClick={() => remove(v)} aria-label="ลบ"><Icon name="trash" /></button>}
                  </td>
                </tr>))}</tbody>
            </table>
          </div>
        )}
        {pages > 1 && (
          <div className="pager">
            <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>ก่อนหน้า</button>
            <span>หน้า {page} / {pages}</span>
            <button className="btn btn-sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>ถัดไป</button>
          </div>
        )}
      </div>
      {edit && <EditVehicleModal vehicle={edit} isNew={!edit.id} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
      {hist && <HistoryModal vehicle={hist} onClose={() => setHist(null)} />}
    </div>
  );
}
