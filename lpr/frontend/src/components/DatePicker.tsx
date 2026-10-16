import { useEffect, useRef, useState } from "react";
import { MONTHS, WEEKDAYS, isoToTh, todayIso } from "../format";
import { Icon } from "./Icons";

/** ปฏิทินเลือกวันที่ แสดงปี พ.ศ. (ค่าที่ส่งออกเป็น YYYY-MM-DD ปฏิทินสากล) */
export function ThaiDatePicker({ value, onChange, label, min, max }: {
  value: string; onChange: (v: string) => void; label: string; min?: string; max?: string;
}) {
  const [open, setOpen] = useState(false);
  const init = (value || todayIso()).split("-").map(Number);
  const [ym, setYm] = useState<[number, number]>([init[0], init[1] - 1]);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const v = (value || todayIso()).split("-").map(Number);
    setYm([v[0], v[1] - 1]);
    const h = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open, value]);
  const [y, m] = ym;
  const first = new Date(Date.UTC(y, m, 1)).getUTCDay();
  const days = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  const cells: (number | null)[] = [...Array(first).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  const iso = (d: number) => `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  const today = todayIso();
  const move = (n: number) => { const t = new Date(Date.UTC(y, m + n, 1)); setYm([t.getUTCFullYear(), t.getUTCMonth()]); };
  return (
    <div className="datepicker" ref={ref}>
      <span className="field-label">{label}</span>
      <button type="button" className="input date-btn" onClick={() => setOpen((o) => !o)} aria-haspopup="dialog"
        aria-expanded={open}>
        <Icon name="calendar" size={16} /> {value ? isoToTh(value) : "เลือกวันที่"}
      </button>
      {open && (
        <div className="cal" role="dialog" aria-label={`ปฏิทิน ${label}`}>
          <div className="cal-head">
            <button type="button" className="icon-btn" onClick={() => move(-1)} aria-label="เดือนก่อน"><Icon name="chevronLeft" /></button>
            <span>{MONTHS[m]} {y + 543}</span>
            <button type="button" className="icon-btn" onClick={() => move(1)} aria-label="เดือนถัดไป"><Icon name="chevronRight" /></button>
          </div>
          <div className="cal-grid">
            {WEEKDAYS.map((w) => <span key={w} className="cal-wd">{w}</span>)}
            {cells.map((d, i) => d === null ? <span key={`e${i}`} /> : (
              <button type="button" key={d}
                disabled={(min !== undefined && iso(d) < min) || (max !== undefined && iso(d) > max)}
                className={`cal-day ${iso(d) === value ? "sel" : ""} ${iso(d) === today ? "today" : ""}`}
                onClick={() => { onChange(iso(d)); setOpen(false); }}>{d}</button>
            ))}
          </div>
          <div className="cal-foot">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => { onChange(today); setOpen(false); }}>วันนี้</button>
          </div>
        </div>
      )}
    </div>
  );
}
