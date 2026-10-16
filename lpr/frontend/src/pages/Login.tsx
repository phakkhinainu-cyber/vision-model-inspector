import { useState, type FormEvent } from "react";
import { api } from "../api";
import { Field } from "../components/Modal";
import { useStore } from "../store";

export function Login() {
  const { setupRequired, refreshAuth, houseName } = useStore();
  const [username, setUsername] = useState(setupRequired ? "admin" : "");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [house, setHouse] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (setupRequired && password !== password2) {
      setError("รหัสผ่านทั้งสองช่องไม่ตรงกัน");
      return;
    }
    setBusy(true);
    try {
      if (setupRequired) await api.post("/api/auth/setup", { username, password, house_name: house });
      else await api.post("/api/auth/login", { username, password, remember });
      await refreshAuth();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={submit}>
        <img src="/icons/icon-192.png" alt="" width={64} height={64} />
        <h1>{setupRequired ? "ตั้งค่าครั้งแรก" : "เข้าสู่ระบบ"}</h1>
        <p className="muted">
          {setupRequired ? "สร้างบัญชีผู้ดูแลระบบ (admin) สำหรับจัดการโปรแกรม" : `สมุดบันทึกเข้า-ออก · ${houseName || "LPR บ้าน"}`}
        </p>
        {setupRequired && (
          <Field label="ชื่อบ้าน/ที่อยู่ที่แสดงบนหน้าจอ">
            <input className="input" value={house} onChange={(e) => setHouse(e.target.value)} placeholder="เช่น บ้านเลขที่ 99/1" />
          </Field>
        )}
        <Field label="ชื่อผู้ใช้">
          <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
            required autoFocus />
        </Field>
        <Field label="รหัสผ่าน" hint={setupRequired ? "อย่างน้อย 6 ตัวอักษร" : undefined}>
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete={setupRequired ? "new-password" : "current-password"} required />
        </Field>
        {setupRequired ? (
          <Field label="ยืนยันรหัสผ่าน">
            <input className="input" type="password" value={password2} onChange={(e) => setPassword2(e.target.value)}
              autoComplete="new-password" required />
          </Field>
        ) : (
          <label className="check">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            <span>จำเครื่องนี้ไว้ 30 วัน</span>
          </label>
        )}
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="btn btn-primary btn-block" disabled={busy}>
          {busy ? "กำลังดำเนินการ…" : setupRequired ? "สร้างบัญชีและเริ่มใช้งาน" : "เข้าสู่ระบบ"}
        </button>
        <p className="muted small">ข้อมูลทั้งหมดเก็บอยู่ในคอมเครื่องนี้เท่านั้น</p>
      </form>
    </div>
  );
}
