import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://localhost:8001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },

      // 🔥 NUEVO — STATIC (museum images)
      "/static": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
    },
  },
})