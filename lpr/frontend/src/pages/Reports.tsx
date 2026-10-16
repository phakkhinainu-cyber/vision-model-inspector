import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, download, qs } from "../api";
import { GroupedColumns, HBars } from "../components/Charts";
import { ThaiDatePicker } from "../components/DatePicker";
import { Icon } from "../components/Icons";
import { PlateChip, StatusBadge } from "../components/Plate";
import { MONTHS, addDays, fmtDateTime, fmtDuration, isoToTh, todayIso } from "../format";
import { useViewport } from "../store";
import type { Vehicle, Visit } from "../types";

interface Summary {
  date_from: string; date_to: string; total: number; in: number; out: number; unique_vehicles: number; unread: number;
  pending: number; hours: { hour: number; in: number; out: number }[]; days: { date: string; in: number; out: number }[];
  by_type: Record<string, number>; by_status: Record<string, number>; avg_duration_sec: number | null; visits_closed: number;
}

const SERIES = [{ key: "in", label: "เข้า", color: "#1D4ED8" }, { key: "out", label: "ออก", color: "#C2410C" }];

export function Reports() {
  const vp = useViewport();
  const nav = useNavigate();
  const [mode, setMode] = useState<"day" | "month" | "custom">("day");
  const [day, setDay] = useState(todayIso());
  const [month, setMonth] = useState(todayIso().slice(0, 7));
  const [from, setFrom] = useState(addDays(todayIso(), -6));
  const [to, setTo] = useState(todayIso());
  const [data, setData] = useState<Summary | null>(null);
  const [hours, setHours] = useState(12);
  const [long, setLong] = useState<(Visit & { vehicle: Vehicle })[]>([]);

  const [a, b] = useMemo(() => {
    if (mode === "day") return [day, day];
    if (mode === "month") {
      const [y, m] = month.split("-").map(Number);
      const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
      return [`${month}-01`, `${month}-${String(last).padStart(2, "0")}`];
    }
    return [from, to];
  }, [mode, day, month, from, to]);

  useEffect(() => { api.get<Summary>("/api/reports/summary", { date_from: a, date_to: b }).then(setData); }, [a, b]);
  useEffect(() => {
    const t = setTimeout(() => api.get<{ items: (Visit & { vehicle: Vehicle })[] }>("/api/reports/long-stay", { hours, days: 30 })
      .then((r) => setLong(r.items)), 300);
    return () => clearTimeout(t);
  }, [hours]);

  const shiftMonth = (n: number) => {
    const [y, m] = month.split("-").map(Number);
    const d = new Date(Date.UTC(y, m - 1 + n, 1));
    setMonth(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`);
  };
  const [my, mm] = month.split("-").map(Number);
  const hourData = (data?.hours || []).map((h) => ({ ...h, label: `${String(h.hour).padStart(2, "0")}:00`, short: String(h.hour) }));
  const dayData = (data?.days || []).map((d) => ({ ...d, label: isoToTh(d.date), short: String(Number(d.date.slice(8))) }));
  const types = Object.entries(data?.by_type || {}).map(([label, value]) => ({ label, value })).sort((x, y) => y.value - x.value);
  const statuses = Object.entries(data?.by_status || {}).map(([label, value]) => ({ label, value })).sort((x, y) => y.value - x.value);
  const peak = hourData.reduce((best, h) => (h.in + h.out > best.n ? { n: h.in + h.out, h: h.label } : best), { n: 0, h: "-" });

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">
          <h1>รายงาน</h1>
          <p className="muted">{a === b ? isoToTh(a) : `${isoToTh(a)} – ${isoToTh(b)}`}</p>
        </div>
        <div className="tabs" role="tablist">
          <button className={mode === "day" ? "on" : ""} onClick={() => setMode("day")}>รายวัน</button>
          <button className={mode === "month" ? "on" : ""} onClick={() => setMode("month")}>รายเดือน</button>
          <button className={mode === "custom" ? "on" : ""} onClick={() => setMode("custom")}>กำหนดเอง</button>
        </div>
        <div className="head-actions">
          <button className="btn" onClick={() => window.open(`/api/export/events.pdf${qs({ date_from: a, date_to: b })}`, "_blank")}>
            <Icon name="printer" size={16} /> พิมพ์รายงาน</button>
          <button className="btn" onClick={() => download(`/api/export/events.xlsx${qs({ date_from: a, date_to: b })}`)}>
            <Icon name="download" size={16} /> Excel</button>
        </div>
      </div>
      <div className="card toolbar">
        {mode === "day" && <ThaiDatePicker label="วันที่" value={day} onChange={setDay} />}
        {mode === "month" && (
          <div className="month-pick">
            <span className="field-label">เดือน</span>
            <div className="row">
              <button className="icon-btn" onClick={() => shiftMonth(-1)} aria-label="เดือนก่อน"><Icon name="chevronLeft" /></button>
              <b>{MONTHS[mm - 1]} {my + 543}</b>
              <button className="icon-btn" onClick={() => shiftMonth(1)} aria-label="เดือนถัดไป"><Icon name="chevronRight" /></button>
            </div>
          </div>
        )}
        {mode === "custom" && <>
          <ThaiDatePicker label="ตั้งแต่" value={from} onChange={setFrom} max={to} />
          <ThaiDatePicker label="ถึง" value={to} onChange={setTo} min={from} />
        </>}
      </div>
      {!data ? <div className="skeleton" style={{ height: 300 }} /> : <>
        <div className="kpis">
          <div className="card kpi"><span>ทั้งหมด</span><b>{data.total.toLocaleString("th-TH")}</b><small>รายการ</small></div>
          <div className="card kpi"><span><i className="sw in" />เข้า</span><b>{data.in.toLocaleString("th-TH")}</b><small>ครั้ง</small></div>
          <div className="card kpi"><span><i className="sw out" />ออก</span><b>{data.out.toLocaleString("th-TH")}</b><small>ครั้ง</small></div>
          <div className="card kpi"><span>รถไม่ซ้ำ</span><b>{data.unique_vehicles.toLocaleString("th-TH")}</b><small>คัน</small></div>
          <div className="card kpi"><span>อยู่เฉลี่ย</span><b>{fmtDuration(data.avg_duration_sec)}</b><small>{data.visits_closed} ครั้งที่ออกแล้ว</small></div>
          <div className="card kpi"><span>ช่วงที่รถมากที่สุด</span><b>{peak.h}</b><small>{peak.n} รายการ</small></div>
          <div className="card kpi"><span>อ่านไม่ได้ / รอตรวจ</span><b>{data.unread} / {data.pending}</b><small>รายการ</small></div>
        </div>
        <div className="card"><GroupedColumns title="จำนวนเข้า-ออกรายชั่วโมง" data={hourData} series={SERIES} labelKey="hour"
          tickEvery={vp === "mobile" ? 3 : 1} /></div>
        {dayData.length > 1 && <div className="card"><GroupedColumns title="จำนวนเข้า-ออกรายวัน" data={dayData} series={SERIES}
          labelKey="date" tickEvery={dayData.length > 16 ? (vp === "mobile" ? 5 : 2) : 1} /></div>}
        <div className="grid2 gap">
          <div className="card"><HBars title="ประเภทรถ" items={types} color="#4338CA" /></div>
          <div className="card"><HBars title="สถานะรถ" items={statuses} color="#4338CA" /></div>
        </div>
      </>}
      <div className="card">
        <div className="toolbar">
          <h2 className="chart-title">รถที่อยู่นานผิดปกติ (30 วันล่าสุด)</h2>
          <label className="field inline"><span className="field-label">อยู่เกิน (ชั่วโมง)</span>
            <input className="input" type="number" min={1} max={720} value={hours} onChange={(e) => setHours(Number(e.target.value) || 1)} /></label>
        </div>
        {long.length === 0 ? <p className="muted">ไม่มีรถที่อยู่เกิน {hours} ชั่วโมง</p> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>ทะเบียน</th><th>สถานะ</th><th>เจ้าของ</th><th>เข้า</th><th>ออก</th><th>อยู่</th></tr></thead>
            <tbody>{long.map((x) => (
              <tr key={x.id} className="clickable" onClick={() => x.entry_event_id && nav(vp === "mobile" ? `/events/${x.entry_event_id}` : `/?event=${x.entry_event_id}`)}>
                <td><PlateChip display={x.vehicle.plate_display} province={x.vehicle.province} size="sm" /></td>
                <td><StatusBadge status={x.vehicle.status} /></td><td>{x.vehicle.owner_name || "-"}</td>
                <td>{x.entry_ts ? fmtDateTime(x.entry_ts) : "-"}</td>
                <td>{x.exit_ts ? fmtDateTime(x.exit_ts) : <span className="badge rv-pending">ยังไม่ออก</span>}</td>
                <td><b>{fmtDuration(x.duration_sec)}</b></td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
    </div>
  );
}
