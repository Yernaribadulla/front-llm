import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],

  server: {
    proxy: {
      "/api": {
        target: "https://landslide-tamale-boring.ngrok-free.dev",
        changeOrigin: true,
        secure: true,
      },
    },
  },
});