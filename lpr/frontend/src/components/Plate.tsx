// ป้ายทะเบียนจำลอง: สีพื้นและสีตัวอักษรตามสีป้ายจริงที่ระบบวิเคราะห์ได้
const BG: Record<string, string> = { white: "#FFFFFF", yellow: "#F6C71E", red: "#D7262E", green: "#1F7A3A", blue: "#1E3A8A",
  orange: "#F59E0B", unknown: "#FFFFFF", black: "#111827" };
const FG: Record<string, string> = { black: "#111827", green: "#166534", blue: "#1E3A8A", red: "#B91C1C", white: "#FFFFFF",
  yellow: "#111827", orange: "#111827", unknown: "#111827" };

export function plateColors(bg?: string, fg?: string) {
  const b = BG[bg || "unknown"] || BG.unknown;
  let f = FG[fg || "unknown"] || FG.unknown;
  if (bg === "red") f = "#111827";
  if (b === f) f = bg === "white" ? "#111827" : "#FFFFFF";
  return { background: b, color: f };
}

export function PlateChip({ display, province, bg, fg, size = "md" }: {
  display: string; province?: string; bg?: string; fg?: string; size?: "sm" | "md";
}) {
  const st = plateColors(bg, fg);
  if (!display) return <span className={`plate plate-${size} plate-unread`}>อ่านไม่ได้</span>;
  return (
    <span className={`plate plate-${size}`} style={st} title={province ? `${display} ${province}` : display}>
      <span className="plate-num">{display}</span>
      {province && size !== "sm" && <span className="plate-prov">{province}</span>}
    </span>
  );
}

/** ป้ายทะเบียนจำลองขนาดใหญ่ (หน้ารายละเอียด) */
export function BigPlate({ display, province, bg, fg }: { display: string; province?: string; bg?: string; fg?: string }) {
  const st = plateColors(bg, fg);
  return (
    <div className={`bigplate ${display ? "" : "plate-unread"}`} style={display ? st : undefined}
      aria-label={display ? `ป้ายทะเบียน ${display} ${province || ""}` : "อ่านป้ายไม่ได้"}>
      <div className="bigplate-num">{display || "อ่านไม่ได้"}</div>
      <div className="bigplate-prov">{province || (display ? "ไม่ทราบจังหวัด" : "")}</div>
    </div>
  );
}

const STATUS_CLASS: Record<string, string> = { "สมาชิก": "st-member", "ผู้มาเยือน": "st-visitor", "ไม่รู้จัก": "st-unknown",
  "เฝ้าระวัง": "st-watch" };

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const s = status || "ไม่รู้จัก";
  return <span className={`badge ${STATUS_CLASS[s] || "st-unknown"}`}>{s}</span>;
}

export function DirTag({ dir }: { dir: string }) {
  return <span className={`dirtag ${dir === "เข้า" ? "in" : "out"}`}>{dir}</span>;
}

export function ReviewBadge({ status }: { status: string }) {
  if (status === "ปกติ") return null;
  const cls = status === "รอตรวจสอบ" ? "rv-pending" : status === "อ่านไม่ได้" ? "rv-unread" : "rv-edited";
  return <span className={`badge ${cls}`}>{status}</span>;
}
