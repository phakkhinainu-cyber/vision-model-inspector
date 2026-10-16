// รูปแบบวันที่/เวลาภาษาไทย: ปี พ.ศ., 24 ชั่วโมง, เขตเวลา Asia/Bangkok (UTC+7 ไม่มีเวลาออมแสง)
export const TZ_OFFSET = 7 * 3600;
export const MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม",
  "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"];
export const MONTHS_SHORT = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."];
export const WEEKDAYS = ["อา", "จ", "อ", "พ", "พฤ", "ศ", "ส"];

/** แยกส่วนวันเวลาตามเวลาไทย */
export function bkk(ts: number) {
  const d = new Date((ts + TZ_OFFSET) * 1000);
  return { y: d.getUTCFullYear(), m: d.getUTCMonth(), d: d.getUTCDate(), h: d.getUTCHours(), min: d.getUTCMinutes(),
    s: d.getUTCSeconds(), wd: d.getUTCDay() };
}

const p2 = (n: number) => String(n).padStart(2, "0");

export const fmtTime = (ts: number) => { const t = bkk(ts); return `${p2(t.h)}:${p2(t.min)}:${p2(t.s)}`; };
export const fmtHM = (ts: number) => { const t = bkk(ts); return `${p2(t.h)}:${p2(t.min)}`; };
export const fmtDate = (ts: number) => { const t = bkk(ts); return `${t.d} ${MONTHS_SHORT[t.m]} ${t.y + 543}`; };
export const fmtDateLong = (ts: number) => { const t = bkk(ts); return `${t.d} ${MONTHS[t.m]} พ.ศ. ${t.y + 543}`; };
export const fmtDateTime = (ts: number) => `${fmtDate(ts)} ${fmtHM(ts)} น.`;

/** วันที่แบบ ISO (YYYY-MM-DD) ตามเวลาไทย ใช้ส่งให้ API */
export function isoDay(ts: number): string {
  const t = bkk(ts);
  return `${t.y}-${p2(t.m + 1)}-${p2(t.d)}`;
}
export function todayIso(): string { return isoDay(Date.now() / 1000); }
export function addDays(iso: string, n: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n));
  return `${dt.getUTCFullYear()}-${p2(dt.getUTCMonth() + 1)}-${p2(dt.getUTCDate())}`;
}
export function isoToTh(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS_SHORT[m - 1]} ${y + 543}`;
}
/** epoch เริ่มต้นของวัน ISO ตามเวลาไทย */
export function dayStart(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d) / 1000 - TZ_OFFSET;
}

export function fmtDuration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined) return "-";
  const m = Math.floor(sec / 60);
  const h = Math.floor(m / 60);
  const mm = m % 60;
  if (h >= 24) { const d = Math.floor(h / 24); return `${d} วัน ${h % 24} ชม.`; }
  if (h && mm) return `${h} ชม. ${mm} น.`;
  if (h) return `${h} ชม.`;
  return mm < 1 ? "<1 น." : `${mm} น.`;
}

export function fmtAgo(ts: number | null | undefined): string {
  if (!ts) return "-";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "เมื่อสักครู่";
  if (s < 3600) return `${Math.floor(s / 60)} นาทีที่แล้ว`;
  if (s < 86400) return `${Math.floor(s / 3600)} ชั่วโมงที่แล้ว`;
  return fmtDate(ts);
}

export function fmtBytes(n: number): string {
  if (n > 1e12) return `${(n / 1e12).toFixed(1)} TB`;
  if (n > 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.round(n / 1e3)} KB`;
}

/** ช่วงชั่วโมง เช่น "17:00 – 18:00" */
export function hourLabel(ts: number): string {
  const h = bkk(ts).h;
  return `${p2(h)}:00 – ${p2((h + 1) % 24)}:00`;
}

export function hourKey(ts: number): string {
  const t = bkk(ts);
  return `${t.y}-${t.m}-${t.d}-${t.h}`;
}
