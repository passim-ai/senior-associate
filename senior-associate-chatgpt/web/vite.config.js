import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// One self-contained HTML file: no external scripts, so the MCP App needs no CSP entries.
export default defineConfig({
  plugins: [viteSingleFile()],
  build: {
    target: "es2022",
    outDir: "dist",
    emptyOutDir: true,
    minify: true,
    cssMinify: true,
    rollupOptions: { input: "index.html" },
  },
});
