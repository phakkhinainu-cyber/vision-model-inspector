import "@fontsource/anuphan/thai-400.css";
import "@fontsource/anuphan/thai-500.css";
import "@fontsource/anuphan/thai-600.css";
import "@fontsource/anuphan/thai-700.css";
import "@fontsource/anuphan/latin-400.css";
import "@fontsource/anuphan/latin-500.css";
import "@fontsource/anuphan/latin-600.css";
import "@fontsource/anuphan/latin-700.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-600.css";
import "@fontsource/sarabun/thai-600.css";
import "@fontsource/sarabun/thai-700.css";
import "@fontsource/sarabun/latin-600.css";
import "@fontsource/sarabun/latin-700.css";
import "./styles.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Cameras } from "./pages/Cameras";
import { Inside } from "./pages/Inside";
import { EventPage, Logbook } from "./pages/Logbook";
import { Login } from "./pages/Login";
import { Reports } from "./pages/Reports";
import { Review } from "./pages/Review";
import { Settings } from "./pages/Settings";
import { Vehicles } from "./pages/Vehicles";
import { StoreProvider, useStore } from "./store";

function EventRoute() {
  const { id } = useParams();
  return <EventPage id={Number(id)} />;
}

function App() {
  const { authChecked, me } = useStore();
  if (!authChecked) return <div className="splash"><img src="/icons/icon-192.png" alt="" width={72} height={72} /><p>กำลังโหลด…</p></div>;
  if (!me) return <Login />;
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Logbook />} />
        <Route path="/events/:id" element={<EventRoute />} />
        <Route path="/inside" element={<Inside />} />
        <Route path="/vehicles" element={<Vehicles />} />
        <Route path="/cameras" element={<Cameras />} />
        <Route path="/review" element={<Review />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <StoreProvider><App /></StoreProvider>
    </BrowserRouter>
  </StrictMode>,
);

// PWA: service worker สำหรับติดตั้งเป็นแอปและรับ Web Push (ทำงานเมื่อเปิดผ่าน HTTPS หรือ localhost)
if ("serviceWorker" in navigator && (window.isSecureContext || location.hostname === "localhost")) {
  window.addEventListener("load", () => { navigator.serviceWorker.register("/sw.js").catch(() => undefined); });
}
