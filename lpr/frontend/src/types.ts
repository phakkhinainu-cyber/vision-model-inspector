export type Direction = "เข้า" | "ออก";
export type ReviewStatus = "ปกติ" | "รอตรวจสอบ" | "แก้ไขแล้ว" | "อ่านไม่ได้";
export type VehicleStatus = "สมาชิก" | "ผู้มาเยือน" | "ไม่รู้จัก" | "เฝ้าระวัง";

export const VEHICLE_TYPES = ["รถเก๋ง", "รถกระบะ", "รถตู้", "รถจักรยานยนต์", "รถบรรทุก", "แท็กซี่/รับจ้าง", "รถบัส",
  "ป้ายแดง", "อื่นๆ"] as const;
export const VEHICLE_STATUSES: VehicleStatus[] = ["สมาชิก", "ผู้มาเยือน", "ไม่รู้จัก", "เฝ้าระวัง"];
export const CAMERA_ROLES = ["ทางเข้า", "ทางออก", "สองทาง"] as const;

export interface Alternative { plate_norm: string; display: string; share: number }

export interface LprEvent {
  id: number;
  uid: string;
  ts: number;
  camera_id: number | null;
  camera_name: string;
  direction: Direction;
  plate_raw: string;
  plate_norm: string;
  plate_display: string;
  province: string;
  ocr_confidence: number;
  vehicle_type: string;
  plate_bg: string;
  plate_fg: string;
  vehicle_id: number | null;
  vehicle_status: VehicleStatus | null;
  owner_name: string;
  house_no: string;
  review_status: ReviewStatus;
  has_full: boolean;
  has_plate: boolean;
  has_thumb: boolean;
  has_clip: boolean;
  clip_ext: string;
  source: "auto" | "capture" | "manual";
  original_plate: string;
  edited_by: string;
  edited_at: number | null;
  night: boolean;
  frames_used: number;
  note: string;
  alternatives: Alternative[];
}

export interface Visit {
  id: number;
  vehicle_id: number;
  entry_event_id: number | null;
  exit_event_id: number | null;
  entry_ts: number | null;
  exit_ts: number | null;
  duration_sec: number | null;
  status: string;
}

export interface Stats30 {
  days: number; entries: number; exits: number; days_seen: number; visits: number;
  avg_duration_sec: number | null; max_duration_sec: number | null;
}

export interface Vehicle {
  id: number;
  plate_norm: string;
  plate_display: string;
  province: string;
  vehicle_type: string;
  type_locked: boolean;
  status: VehicleStatus;
  owner_name: string;
  house_no: string;
  phone: string;
  note: string;
  first_seen: number | null;
  last_seen: number | null;
  visits_today?: Visit[];
  stats_30d?: Stats30;
}

export interface CameraStatus {
  state: string; state_th: string; fps?: number; night?: boolean; ir?: boolean; error?: string;
  size?: number[]; size_main?: number[]; motion?: number; tracks?: number; reconnects?: number;
  events?: number; last_event_ts?: number | null; restarts?: number; ocr?: string; device?: string;
  plate_detector?: string; brightness?: number;
}

export interface Camera {
  id: number;
  name: string;
  rtsp_main: string;
  rtsp_sub: string;
  username: string;
  has_password: boolean;
  role: string;
  roi_polygon: number[][];
  line_coords: number[][];
  line_direction: "pos_in" | "neg_in";
  enabled: boolean;
  sort_order: number;
  status: CameraStatus;
}

export interface Facets {
  total: number;
  direction: Record<string, number>;
  types: Record<string, number>;
  vstatus: Record<string, number>;
  cameras: Record<string, number>;
}

export interface Me { id: number; username: string; role: "admin" | "viewer"; display_name: string }

export interface SettingItem {
  key: string; type: string; default: unknown; label: string; group: string; help: string;
  min: number | null; max: number | null; step: number | null; options: string[]; restart: boolean;
  cameras: boolean; secret: boolean; value: unknown; has_value?: boolean;
}

export interface SystemStatus {
  app: string; version: string; house_name: string; camera_count: number; pending_review: number;
  cameras: { id: number; name: string; role: string; enabled: boolean; status: CameraStatus }[];
  disk: { path: string; total: number; free: number; free_percent: number };
  alerts: string[]; restart_required: string[]; user: Me;
  home?: string; credentials?: string; providers?: string[]; gpus?: string[]; models?: Record<string, boolean>;
  last_backup?: { file?: string; ts?: number; size?: number };
}
