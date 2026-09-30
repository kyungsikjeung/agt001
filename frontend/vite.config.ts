import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 빌드 결과(dist/)는 FastAPI가 "/"와 "/assets"로 서빙한다 (app/api/public.py).
// 개발 서버에서는 API 요청을 로컬 백엔드로 넘긴다.
const backend = process.env.BACKEND_URL ?? 'http://localhost:8650';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: { input: { main: 'index.html', editor: 'editor.html', projects: 'projects.html', builder: 'builder.html' } },
  },
  server: {
    proxy: Object.fromEntries(
      ['/room', '/room.html', '/events', '/chat', '/design', '/site', '/health'].map((p) => [p, backend]),
    ),
  },
});
