import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, download, qs } from "../api";
import { ThaiDatePicker } from "../components/DatePicker";
import { EventDetail } from "../components/EventDetail";
import { Icon } from "../components/Icons";
import { Empty } from "../components/Modal";
import { DirTag, PlateChip, ReviewBadge, StatusBadge } from "../components/Plate";
import { addDays, fmtDate, fmtTime, hourKey, hourLabel, isoDay, todayIso } from "../format";
import { useLive, useStore, useViewport } from "../store";
import { VEHICLE_STATUSES, VEHICLE_TYPES, type Facets, type LprEvent } from "../types";

type Period = "today" | "7d" | "30d" | "custom";
interface Filters { q: string; direction: string[]; types: string[]; vstatus: string[]; cameras: string[] }
const EMPTY: Filters = { q: "", direction: [], types: [], vstatus: [], cameras: [] };

function range(period: Period, from: string, to: string): [string, string] {
  const t = todayIso();
  if (period === "today") return [t, t];
  if (period === "7d") return [addDays(t, -6), t];
  if (period === "30d") return [addDays(t, -29), t];
  return [from || t, to || t];
}

function normQ(s: string) {
  return s.replace(/[๐-๙]/g, (d) => String("๐๑๒๓๔๕๖๗๘๙".indexOf(d))).replace(/[ะ-ฺเ-๎]/g, "")
    .replace(/[^0-9ก-ฮ]/g, "");
}

/** ตรวจว่ารายการใหม่ (จาก WebSocket) ตรงกับตัวกรองปัจจุบันหรือไม่ */
function matches(e: LprEvent, f: Filters, from: string, to: string): boolean {
  const d = isoDay(e.ts);
  if (d < from || d > to) return false;
  if (f.direction.length && !f.direction.includes(e.direction)) return false;
  if (f.types.length && !f.types.includes(e.vehicle_type)) return false;
  if (f.vstatus.length && !f.vstatus.includes(e.vehicle_status || "ไม่รู้จัก")) return false;
  if (f.cameras.length && !f.cameras.includes(String(e.camera_id))) return false;
  if (f.q) {
    const nq = normQ(f.q);
    if (nq ? !e.plate_norm.includes(nq) : !e.province.includes(f.q.trim())) return false;
  }
  return true;
}

export function Logbook() {
  const { system, houseName } = useStore();
  const vp = useViewport();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [period, setPeriod] = useState<Period>("today");
  const [from, setFrom] = useState(todayIso());
  const [to, setTo] = useState(todayIso());
  const [f, setF] = useState<Filters>(EMPTY);
  const [qInput, setQInput] = useState("");
  const [items, setItems] = useState<LprEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [selected, setSelected] = useState<number | null>(sp.get("event") ? Number(sp.get("event")) : null);
  const [drawer, setDrawer] = useState(false);
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const [dFrom, dTo] = range(period, from, to);
  const query = useMemo(() => ({
    date_from: dFrom, date_to: dTo, q: f.q, direction: f.direction.join(","), types: f.types.join(","),
    vstatus: f.vstatus.join(","), cameras: f.cameras.join(","),
  }), [dFrom, dTo, f]);
  const reqId = useRef(0);

  // ค้นหาทะเบียนแบบหน่วงเวลาเล็กน้อยระหว่างพิมพ์
  useEffect(() => { const t = setTimeout(() => setF((x) => ({ ...x, q: qInput })), 300); return () => clearTimeout(t); }, [qInput]);

  const loadFacets = useCallback(() => {
    api.get<Facets>("/api/events/facets", query).then(setFacets).catch(() => undefined);
  }, [query]);

  useEffect(() => {
    const id = ++reqId.current;
    setLoading(true);
    api.get<{ items: LprEvent[]; next_cursor: string | null }>("/api/events", { ...query, limit: 100 }).then((r) => {
      if (id !== reqId.current) return;
      setItems(r.items);
      setCursor(r.next_cursor);
      if (vp !== "mobile" && !selected && r.items.length) setSelected(r.items[0].id);
    }).finally(() => id === reqId.current && setLoading(false));
    loadFacets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const loadMore = useCallback(() => {
    if (!cursor || loading) return;
    setLoading(true);
    api.get<{ items: LprEvent[]; next_cursor: string | null }>("/api/events", { ...query, limit: 100, cursor })
      .then((r) => { setItems((x) => [...x, ...r.items]); setCursor(r.next_cursor); }).finally(() => setLoading(false));
  }, [cursor, loading, query]);

  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((en) => en[0].isIntersecting && loadMore(), { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, [loadMore]);

  const facetTimer = useRef<number>();
  useLive((m) => {
    if (m.type === "event" && matches(m.event, f, dFrom, dTo)) {
      setItems((x) => (x.some((e) => e.id === m.event.id) ? x : [m.event, ...x]));
      setFresh((s) => new Set(s).add(m.event.id));
      setTimeout(() => setFresh((s) => { const n = new Set(s); n.delete(m.event.id); return n; }), 4000);
    }
    if (m.type === "event_update") setItems((x) => x.map((e) => (e.id === m.event.id ? m.event : e)));
    if (m.type === "event_delete") setItems((x) => x.filter((e) => e.id !== m.id));
    if (m.type === "event" || m.type === "event_update" || m.type === "event_delete") {
      window.clearTimeout(facetTimer.current);
      facetTimer.current = window.setTimeout(loadFacets, 800);
    }
  });

  const select = (id: number) => {
    if (vp === "mobile") nav(`/events/${id}`);
    else { setSelected(id); setSp({ event: String(id) }, { replace: true }); }
  };

  // จัดกลุ่มตามชั่วโมง (และวันที่ ถ้าช่วงมากกว่า 1 วัน)
  const groups = useMemo(() => {
    const out: { key: string; day: string; label: string; items: LprEvent[] }[] = [];
    for (const e of items) {
      const k = hourKey(e.ts);
      const last = out[out.length - 1];
      if (last && last.key === k) last.items.push(e);
      else out.push({ key: k, day: fmtDate(e.ts), label: hourLabel(e.ts), items: [e] });
    }
    return out;
  }, [items]);
  const multiDay = dFrom !== dTo;

  // คีย์บอร์ด: ↑/↓ เลือกรายการ
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || document.querySelector(".modal")) return;
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const i = items.findIndex((x) => x.id === selected);
      const n = items[Math.max(0, Math.min(items.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
      if (n) { e.preventDefault(); select(n.id); document.getElementById(`ev-${n.id}`)?.scrollIntoView({ block: "nearest" }); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  const exportUrl = (fmt: string) => `/api/export/events.${fmt}${qs(query)}`;
  const toggle = (k: keyof Omit<Filters, "q">, v: string) =>
    setF((x) => ({ ...x, [k]: x[k].includes(v) ? x[k].filter((y) => y !== v) : [...x[k], v] }));
  const activeCount = f.direction.length + f.types.length + f.vstatus.length + f.cameras.length + (f.q ? 1 : 0);
  const cams = system?.cameras || [];

  const filtersPanel = (
    <aside className="card filters" aria-label="ตัวกรอง">
      <div className="filters-head">
        <h2>ตัวกรอง</h2>
        {vp !== "desktop" && <button className="icon-btn" onClick={() => setDrawer(false)} aria-label="ปิดตัวกรอง"><Icon name="x" /></button>}
      </div>
      <label className="field">
        <span className="field-label">ค้นหาทะเบียน</span>
        <span className="search"><Icon name="search" size={16} />
          <input className="input" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="เช่น 4521 หรือ กข" inputMode="search" />
        </span>
      </label>
      {period === "custom" && (
        <div className="grid2">
          <ThaiDatePicker label="ตั้งแต่วันที่" value={from} onChange={setFrom} max={to} />
          <ThaiDatePicker label="ถึงวันที่" value={to} onChange={setTo} min={from} />
        </div>
      )}
      {period !== "custom" && <ThaiDatePicker label="วันที่" value={dTo} onChange={(v) => { setPeriod("custom"); setFrom(v); setTo(v); }} />}
      <FacetGroup title="ทิศทาง" values={["เข้า", "ออก"]} counts={facets?.direction} sel={f.direction} onToggle={(v) => toggle("direction", v)} />
      <FacetGroup title="ประเภทรถ" values={[...VEHICLE_TYPES]} counts={facets?.types} sel={f.types} onToggle={(v) => toggle("types", v)} hideZero />
      <FacetGroup title="สถานะ" values={VEHICLE_STATUSES} counts={facets?.vstatus} sel={f.vstatus} onToggle={(v) => toggle("vstatus", v)} />
      {cams.length > 0 && (
        <FacetGroup title="กล้อง" values={cams.map((c) => String(c.id))} labels={Object.fromEntries(cams.map((c) => [String(c.id), c.name]))}
          counts={facets?.cameras} sel={f.cameras} onToggle={(v) => toggle("cameras", v)} />
      )}
      <button className="btn btn-block" onClick={() => { setF(EMPTY); setQInput(""); }} disabled={!activeCount}>ล้างตัวกรอง</button>
    </aside>
  );

  return (
    <div className="logbook">
      <div className="page-head">
        <div className="page-title">
          <h1>สมุดบันทึกเข้า-ออก</h1>
          <p className="muted">บันทึกอัตโนมัติจากกล้อง {system?.camera_count ?? 0} ตัว · เก็บไว้ในเครื่องนี้{vp === "mobile" ? "" : ` · ${houseName}`}</p>
        </div>
        <div className="tabs" role="tablist" aria-label="ช่วงเวลา">
          {([["today", "วันนี้"], ["7d", "7 วัน"], ["30d", "30 วัน"], ["custom", "กำหนดเอง"]] as [Period, string][]).map(([k, l]) => (
            <button key={k} role="tab" aria-selected={period === k} className={period === k ? "on" : ""}
              onClick={() => { setPeriod(k); if (k === "custom") { setFrom(dFrom); setTo(dTo); setDrawer(vp !== "desktop"); } }}>{l}</button>
          ))}
        </div>
        <div className="head-actions">
          <button className="btn" onClick={() => download(exportUrl("csv"))}><Icon name="download" size={16} /> <span>{vp === "mobile" ? "CSV" : "ส่งออก CSV"}</span></button>
          <button className="btn" onClick={() => download(exportUrl("xlsx"))}><Icon name="download" size={16} /> <span>{vp === "mobile" ? "Excel" : "ส่งออก Excel"}</span></button>
          <button className="btn" onClick={() => window.open(exportUrl("pdf"), "_blank")}><Icon name="printer" size={16} /> <span>{vp === "mobile" ? "PDF" : "พิมพ์รายงาน"}</span></button>
        </div>
      </div>

      {vp === "mobile" && (
        <div className="mobile-search">
          <span className="search"><Icon name="search" size={16} />
            <input className="input" value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="ค้นหาทะเบียน" aria-label="ค้นหาทะเบียน" inputMode="search" />
          </span>
          <button className="btn" onClick={() => setDrawer(true)} aria-label="ตัวกรอง"><Icon name="filter" size={16} />{activeCount > 0 && <span className="nav-badge">{activeCount}</span>}</button>
        </div>
      )}

      <div className="cols">
        {vp === "desktop" ? filtersPanel : drawer && (
          <div className="drawer-backdrop" onClick={() => setDrawer(false)}>
            <div className="drawer" onClick={(e) => e.stopPropagation()}>{filtersPanel}</div>
          </div>
        )}
        <section className="card timeline" aria-label="ไทม์ไลน์">
          <div className="timeline-head">
            {vp === "tablet" && <button className="btn btn-sm" onClick={() => setDrawer(true)}><Icon name="filter" size={14} /> ตัวกรอง{activeCount ? ` (${activeCount})` : ""}</button>}
            <span className="muted">{facets ? `${facets.total.toLocaleString("th-TH")} รายการ` : "…"}</span>
            {facets && <span className="muted"> · <span className="c-in">เข้า {facets.direction["เข้า"] || 0}</span> · <span className="c-out">ออก {facets.direction["ออก"] || 0}</span></span>}
          </div>
          {items.length === 0 && !loading ? <Empty icon="car" title="ไม่มีรายการในช่วงนี้" text="รถที่ผ่านกล้องจะแสดงที่นี่แบบสด" /> : (
            <div className="tl-scroll" role="list">
              {groups.map((g, gi) => (
                <div key={g.key + gi} className="tl-group">
                  <div className="tl-ghead">{multiDay ? `${g.day} · ` : ""}{g.label} · {g.items.length} รายการ</div>
                  {g.items.map((e) => (
                    <button key={e.id} id={`ev-${e.id}`} role="listitem" onClick={() => select(e.id)}
                      className={`tl-row ${selected === e.id && vp !== "mobile" ? "sel" : ""} ${fresh.has(e.id) ? "fresh" : ""}`}
                      aria-current={selected === e.id}>
                      <span className={`tl-dot ${e.direction === "เข้า" ? "in" : "out"}`} aria-hidden />
                      <span className="tl-time mono">{fmtTime(e.ts)}</span>
                      <span className="tl-plate">
                        <PlateChip display={e.plate_display} province={e.province} bg={e.plate_bg} fg={e.plate_fg} size="sm" />
                        <span className="tl-prov">{e.province}</span>
                      </span>
                      <span className="tl-meta">{e.vehicle_type} · {e.camera_name || "-"}</span>
                      <span className="tl-badges"><StatusBadge status={e.vehicle_status} /><ReviewBadge status={e.review_status} /></span>
                      <DirTag dir={e.direction} />
                    </button>
                  ))}
                </div>
              ))}
              <div ref={sentinel} className="tl-more">{loading ? "กำลังโหลด…" : cursor ? "" : items.length > 20 ? "— สิ้นสุดรายการ —" : ""}</div>
            </div>
          )}
        </section>
        {vp !== "mobile" && <EventDetail id={selected} onDeleted={() => setSelected(null)} />}
      </div>
    </div>
  );
}

function FacetGroup({ title, values, labels, counts, sel, onToggle, hideZero }: {
  title: string; values: string[]; labels?: Record<string, string>; counts?: Record<string, number>; sel: string[];
  onToggle: (v: string) => void; hideZero?: boolean;
}) {
  const shown = values.filter((v) => !hideZero || (counts?.[v] || 0) > 0 || sel.includes(v));
  return (
    <fieldset className="facet">
      <legend>{title}</legend>
      {shown.length === 0 && <span className="muted small">ไม่มีข้อมูล</span>}
      {shown.map((v) => (
        <label key={v} className={`facet-item ${sel.includes(v) ? "on" : ""}`}>
          <input type="checkbox" checked={sel.includes(v)} onChange={() => onToggle(v)} />
          <span className="facet-name">{v === "เข้า" ? <span className="c-in">● เข้า</span> : v === "ออก" ? <span className="c-out">● ออก</span> : labels?.[v] || v}</span>
          <span className="facet-n">{counts?.[v] || 0}</span>
        </label>
      ))}
    </fieldset>
  );
}

export function EventPage({ id }: { id: number }) {
  const nav = useNavigate();
  return (
    <div className="event-page">
      <button className="btn btn-ghost back" onClick={() => (history.length > 1 ? nav(-1) : nav("/"))}>
        <Icon name="arrowLeft" size={18} /> กลับไปรายการ
      </button>
      <EventDetail id={id} compact onDeleted={() => nav("/")} />
    </div>
  );
}
