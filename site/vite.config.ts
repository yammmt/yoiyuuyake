import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import { validateBuildEnvironment } from "./build/environment";

// macOS Seatbelt blocks FSEvents, so Codex previews need polling for HMR.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === "seatbelt";

export default defineConfig(({ command, mode }) => {
  if (command === "build") {
    validateBuildEnvironment(loadEnv(mode, process.cwd(), "VITE_"), {
      requireHttps: mode === "production" || mode === "staging",
    });
  }

  return {
    server: {
      port: 3000,
      strictPort: true,
      ...(isCodexSeatbeltSandbox
        ? { watch: { useFsEvents: false, usePolling: true } }
        : {}),
    },
    preview: {
      port: 3000,
      strictPort: true,
    },
    plugins: [react()],
  };
});
