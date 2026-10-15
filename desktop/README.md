# Trading Assistant: Windows desktop app (Electron)

An Electron shell around the Next.js front end. It starts the bundled web server on a free local port, opens it in a sandboxed window and talks to your FastAPI backend.
It is written in TypeScript (`src/`) and packaged with electron-builder into a per-user installer and a portable `.exe`.

```bash
cd desktop
npm install
npm run prepare:web      # builds ../web and bundles its standalone server into web-server/
npm start                # compile + run the app (needs the backend running: docker compose up, or uvicorn app.main:app)
npm test                 # unit tests (Vitest)
npm run dist             # release/TradingAssistant-Setup-<version>.exe and TradingAssistant-Portable-<version>.exe
"release/win-unpacked/Trading Assistant.exe" --smoke   # starts, loads the page, prints SMOKE_OK and exits (used by CI)
```

## How it works
- `src/main.ts`: single-instance app. Checks the backend `/health` and tells you if it is down (retry, continue, or quit), starts the Next.js server with Electron's own Node runtime
  (`ELECTRON_RUN_AS_NODE`), waits until it answers, then opens the window. The server process is stopped when the app closes; its log is in `%APPDATA%/trading-assistant-desktop/logs/`.
- `src/security.ts`: the window can only show the local server. Other `https://` links open in your browser; `http:`, `file:`, `javascript:` and custom schemes are refused.
  The window runs with `contextIsolation`, `sandbox`, no Node integration, and denies every permission request.
- `src/config.ts`: settings come from `%APPDATA%/trading-assistant-desktop/config.json` (`backendUrl`, `llmProvider`, `llmModel`, `ollamaUrl`) and are overridden by environment variables.
  The web server child gets an allow-list of environment variables, not your whole environment. `ANTHROPIC_API_KEY` is passed on only when the provider is `anthropic`, and is never written to `config.json`.
- `scripts/prepare-web.mjs`: electron-builder never copies folders named `node_modules` into `extraResources`, so the bundle ships it as `server_modules` and `main.ts` sets `NODE_PATH` to it.

## Limits (be honest about these)
- **The Python backend is not bundled.** The app needs a running FastAPI backend (local, Docker, or a server) at `backendUrl`.
- **No code signing and the default Electron icon.** Windows SmartScreen will warn on first run.
- **No auto-update** yet; this is a manual installer.
- **Login screen:** the UI does not log in, so use it with a backend that has `AUTH_REQUIRED` off, or add a login screen first.
- Tested on Windows 11 only. The NSIS installer and the portable exe are built in CI, and the unpacked app is smoke-tested; I have not run the installer wizard end to end.
