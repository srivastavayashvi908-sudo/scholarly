import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Forward /api calls to the FastAPI backend running in Docker.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
