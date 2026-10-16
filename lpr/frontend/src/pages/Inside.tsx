import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Empty } from "../components/Modal";
import { PlateChip, StatusBadge } from "../components/Plate";
import { fmtDateTime, fmtDuration } from "../format";
import { useLive, useViewport } from "../store";
import type { Vehicle, Visit } from "../types";

type Item = Visit & { vehicle: Vehicle };

export function Inside() {
  const [data, setData] = useState<{ inside: Item[]; no_exit: Item[] } | null>(null);
  const [, tick] = useState(0);
  const nav = useNavigate();
  const vp = useViewport();
  const load = useCallback(() => { api.get<{ inside: Item[]; no_exit: Item[] }>("/api/visits/inside").then(setData); }, []);
  useEffect(load, [load]);
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 60000); return () => clearInterval(t); }, []);
  useLive((m) => { if (m.type === "event" || m.type === "event_update" || m.type === "event_delete") load(); });
  const open = (x: Item) => {
    const id = x.entry_event_id || x.exit_event_id;
    if (!id) return;
    nav(vp === "mobile" ? `/events/${id}` : `/?event=${id}`);
  };
  const list = (items: Item[], noExit = false) => (
    <div className="inside-list">
      {items.map((x) => (
        <button key={x.id} className="card inside-item" onClick={() => open(x)}>
          <PlateChip display={x.vehicle.plate_display} province={x.vehicle.province} size="md" />
          <div className="inside-info">
            <div><StatusBadge status={x.vehicle.status} /> <span className="muted">{x.vehicle.vehicle_type}</span></div>
            <div className="muted small">{x.vehicle.owner_name || "ไม่ระบุเจ้าของ"}{x.vehicle.house_no ? ` · บ้าน ${x.vehicle.house_no}` : ""}</div>
            <div className="small">เข้า {x.entry_ts ? fmtDateTime(x.entry_ts) : "-"}</div>
          </div>
          <div className={`inside-dur ${noExit ? "warn" : ""}`}>
            <b>{fmtDuration(x.entry_ts ? Date.now() / 1000 - x.entry_ts : null)}</b>
            <span>{noExit ? "ไม่พบการออก" : "อยู่ในพื้นที่"}</span>
          </div>
        </button>
      ))}
    </div>
  );
  return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">
          <h1>รถที่อยู่ในพื้นที่ตอนนี้</h1>
          <p className="muted">เข้าแล้วยังไม่ออก {data ? `· ${data.inside.length} คัน` : ""}</p>
        </div>
      </div>
      {!data ? <div className="skeleton" style={{ height: 200 }} /> : data.inside.length === 0
        ? <div className="card"><Empty icon="home" title="ไม่มีรถในพื้นที่" text="เมื่อรถเข้าและยังไม่ออก จะแสดงที่นี่" /></div>
        : list(data.inside)}
      {data && data.no_exit.length > 0 && (
        <>
          <h2 className="sec-title">ไม่พบการออก <span className="muted small">(เข้าแล้วไม่พบการออกเกินเวลาที่ตั้ง หรือเข้าซ้ำโดยไม่พบการออก)</span></h2>
          {list(data.no_exit, true)}
        </>
      )}
    </div>
  );
}
