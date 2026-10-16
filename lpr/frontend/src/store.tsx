import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import type { CameraStatus, LprEvent, Me, SystemStatus } from "./types";

export type LiveMsg =
  | { type: "event"; event: LprEvent }
  | { type: "event_update"; event: LprEvent }
  | { type: "event_delete"; id: number }
  | { type: "camera_status"; camera_id: number; status: CameraStatus }
  | { type: "alert"; level: string; message: string }
  | { type: "vehicle_update"; vehicle: unknown }
  | { type: "settings"; changed: string[] }
  | { type: "hello" | "pong" };

type Listener = (m: LiveMsg) => void;

interface Toast { id: number; text: string; kind: "ok" | "error" | "info" }

interface Store {
  me: Me | null;
  isAdmin: boolean;
  houseName: string;
  setupRequired: boolean;
  authChecked: boolean;
  refreshAuth: () => Promise<void>;
  logout: () => Promise<void>;
  system: SystemStatus | null;
  refreshSystem: () => void;
  online: boolean;
  subscribe: (fn: Listener) => () => void;
  toast: (text: string, kind?: Toast["kind"]) => void;
  toasts: Toast[];
}

const Ctx = createContext<Store | null>(null);

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("no store");
  return s;
}

/** รับข้อความสดจาก WebSocket */
export function useLive(fn: Listener): void {
  const { subscribe } = useStore();
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => subscribe((m) => ref.current(m)), [subscribe]);
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [houseName, setHouseName] = useState("");
  const [setupRequired, setSetupRequired] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [online, setOnline] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const listeners = useRef(new Set<Listener>());

  const refreshAuth = useCallback(async () => {
    try {
      const s = await api.get<{ setup_required: boolean; house_name: string; user: Me | null }>("/api/auth/status");
      setSetupRequired(s.setup_required);
      setHouseName(s.house_name);
      setMe(s.user);
    } catch {
      setMe(null);
    } finally {
      setAuthChecked(true);
    }
  }, []);

  const refreshSystem = useCallback(() => {
    api.get<SystemStatus>("/api/system/status").then((s) => {
      setSystem(s);
      setHouseName(s.house_name);
    }).catch(() => undefined);
  }, []);

  const logout = useCallback(async () => {
    await api.post("/api/auth/logout").catch(() => undefined);
    setMe(null);
  }, []);

  const toast = useCallback((text: string, kind: Toast["kind"] = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 6000 : 3500);
  }, []);

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => { listeners.current.delete(fn); };
  }, []);

  useEffect(() => { refreshAuth(); }, [refreshAuth]);
  useEffect(() => {
    const h = () => setMe(null);
    window.addEventListener("lpr:unauthorized", h);
    return () => window.removeEventListener("lpr:unauthorized", h);
  }, []);

  // WebSocket เชื่อมต่อใหม่อัตโนมัติ
  useEffect(() => {
    if (!me) return;
    let ws: WebSocket | null = null;
    let stop = false;
    let retry = 1000;
    let ping: number | undefined;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => {
        setOnline(true);
        retry = 1000;
        refreshSystem();
        ping = window.setInterval(() => ws?.readyState === 1 && ws.send("ping"), 25000);
      };
      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data) as LiveMsg;
          if (m.type === "camera_status") {
            setSystem((s) => s && { ...s, cameras: s.cameras.map((c) => c.id === m.camera_id ? { ...c, status: m.status } : c) });
          }
          if (m.type === "event" && (m.event.review_status === "รอตรวจสอบ" || m.event.review_status === "อ่านไม่ได้")) {
            setSystem((s) => s && { ...s, pending_review: s.pending_review + 1 });
          }
          if (m.type === "alert") toast(m.message, m.level === "warning" ? "error" : "info");
          listeners.current.forEach((fn) => fn(m));
        } catch { /* ignore */ }
      };
      ws.onclose = () => {
        setOnline(false);
        window.clearInterval(ping);
        if (!stop) setTimeout(connect, retry);
        retry = Math.min(retry * 2, 15000);
      };
    };
    connect();
    const iv = window.setInterval(refreshSystem, 60000);
    return () => { stop = true; ws?.close(); window.clearInterval(iv); window.clearInterval(ping); };
  }, [me, refreshSystem, toast]);

  const value: Store = {
    me, isAdmin: me?.role === "admin", houseName, setupRequired, authChecked, refreshAuth, logout, system,
    refreshSystem, online, subscribe, toast, toasts,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** ตรวจขนาดจอ: desktop ≥1200, tablet 768–1199, mobile <768 */
export function useViewport(): "desktop" | "tablet" | "mobile" {
  type VP = "desktop" | "tablet" | "mobile";
  const get = (): VP => (window.innerWidth >= 1200 ? "desktop" : window.innerWidth >= 768 ? "tablet" : "mobile");
  const [v, setV] = useState(get);
  useEffect(() => {
    const h = () => setV(get());
    window.addEventListener("resize", h);
    return () => window.removeEventListener("resize", h);
  }, []);
  return v;
}
