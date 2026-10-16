import { useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useStore, useViewport } from "../store";
import { Icon } from "./Icons";

const NAV = [
  { to: "/", label: "สมุดบันทึก", icon: "book", end: true },
  { to: "/inside", label: "ในพื้นที่", icon: "home" },
  { to: "/vehicles", label: "ทะเบียนรถ", icon: "car" },
  { to: "/cameras", label: "กล้อง", icon: "camera" },
  { to: "/review", label: "รอตรวจสอบ", icon: "check", badge: true },
  { to: "/reports", label: "รายงาน", icon: "chart" },
  { to: "/settings", label: "ตั้งค่า", icon: "settings" },
];
const MOBILE_MAIN = ["/", "/inside", "/review", "/cameras"];

export function Layout({ children }: { children: ReactNode }) {
  const { me, houseName, system, online, logout, toasts } = useStore();
  const vp = useViewport();
  const [more, setMore] = useState(false);
  const loc = useLocation();
  const pending = system?.pending_review || 0;
  const camsOk = system ? system.cameras.filter((c) => c.enabled && c.status.state === "online").length : 0;
  const camsAll = system ? system.cameras.filter((c) => c.enabled).length : 0;
  const link = (n: (typeof NAV)[number], cls = "nav-link") => (
    <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `${cls} ${isActive ? "active" : ""}`}
      onClick={() => setMore(false)}>
      <Icon name={n.icon} size={vp === "mobile" ? 22 : 18} />
      <span>{n.label}</span>
      {n.badge && pending > 0 && <span className="nav-badge" aria-label={`${pending} รายการ`}>{pending > 99 ? "99+" : pending}</span>}
    </NavLink>
  );
  return (
    <div className={`app vp-${vp}`}>
      <header className="topbar">
        <div className="brand">
          <img src="/icons/icon-192.png" alt="" width={32} height={32} />
          <div className="brand-text">
            <strong>LPR บ้าน</strong>
            <span>{houseName}</span>
          </div>
        </div>
        {vp !== "mobile" && <nav className="nav" aria-label="เมนูหลัก">{NAV.map((n) => link(n))}</nav>}
        <div className="topbar-right">
          <span className={`conn ${online ? "on" : "off"}`} title={online ? "เชื่อมต่อแบบสด" : "ขาดการเชื่อมต่อ กำลังเชื่อมต่อใหม่"}>
            <span className="dot" /> {vp === "mobile" ? "" : online ? "สด" : "ขาดการเชื่อมต่อ"}
          </span>
          {camsAll > 0 && (
            <span className={`camchip ${camsOk === camsAll ? "ok" : "warn"}`} title="กล้องที่ออนไลน์">
              <Icon name="camera" size={15} /> {camsOk}/{camsAll}
            </span>
          )}
          {vp !== "mobile" && me && (
            <button className="btn btn-ghost btn-sm" onClick={logout} title={`ออกจากระบบ (${me.display_name})`}>
              <Icon name="logout" size={16} /> <span className="hide-tablet">{me.display_name}</span>
            </button>
          )}
        </div>
      </header>
      {system && (system.alerts.length > 0 || system.restart_required.length > 0) && (
        <div className="banners">
          {system.alerts.map((a) => <div key={a} className="banner warn"><Icon name="alert" size={16} /> {a}</div>)}
          {system.restart_required.length > 0 && (
            <div className="banner info"><Icon name="refresh" size={16} /> ค่าตั้งค่าบางอย่างจะมีผลหลังรีสตาร์ตโปรแกรม</div>
          )}
        </div>
      )}
      <main className="main" key={vp === "mobile" ? loc.pathname : undefined}>{children}</main>
      {vp === "mobile" && (
        <nav className="bottomnav" aria-label="เมนูหลัก">
          {NAV.filter((n) => MOBILE_MAIN.includes(n.to)).map((n) => link(n, "bn-link"))}
          <button className={`bn-link ${more ? "active" : ""}`} onClick={() => setMore((m) => !m)} aria-expanded={more}>
            <Icon name="menu" size={22} /><span>เมนู</span>
          </button>
        </nav>
      )}
      {more && vp === "mobile" && (
        <div className="sheet-backdrop" onClick={() => setMore(false)}>
          <div className="sheet" onClick={(e) => e.stopPropagation()} role="menu">
            {NAV.filter((n) => !MOBILE_MAIN.includes(n.to)).map((n) => link(n, "sheet-link"))}
            <button className="sheet-link" onClick={() => { setMore(false); logout(); }}>
              <Icon name="logout" size={22} /><span>ออกจากระบบ ({me?.display_name})</span>
            </button>
          </div>
        </div>
      )}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>)}
      </div>
    </div>
  );
}
