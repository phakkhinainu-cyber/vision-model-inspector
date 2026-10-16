import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// ระหว่างพัฒนา: npm run dev แล้วเปิด http://localhost:5173 (ส่งต่อ /api และ /ws ไปที่ backend พอร์ต 8765)
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/ws": { target: "ws://127.0.0.1:8765", ws: true },
    },
  },
  build: { outDir: "dist", assetsInlineLimit: 0, chunkSizeWarningLimit: 900 },
});
