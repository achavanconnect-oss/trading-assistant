import { app, BrowserWindow, dialog, session, shell } from 'electron';
import { spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { loadConfig, serverEnv, type DesktopConfig } from './config';
import { freePort, httpOk, waitForHttp } from './net';
import { externalTarget, isSameOrigin } from './security';

const SMOKE = process.argv.includes('--smoke');   // start, load the page, print one line, exit (used by CI and manual checks)
let server: ChildProcess | null = null;
let win: BrowserWindow | null = null;

function serverEntry(): string {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'web-server', 'server.js')
    : path.join(__dirname, '..', 'web-server', 'server.js');
}

/** Run the bundled Next.js server on a free local port, using Electron's own Node runtime. */
async function startServer(cfg: DesktopConfig): Promise<string> {
  const entry = serverEntry();
  if (!fs.existsSync(entry)) throw new Error(`web server bundle not found at ${entry} (run: npm run prepare:web)`);
  const port = await freePort();
  const logDir = path.join(app.getPath('userData'), 'logs');
  fs.mkdirSync(logDir, { recursive: true });
  const log = fs.createWriteStream(path.join(logDir, 'web-server.log'), { flags: 'a' });
  server = spawn(process.execPath, [entry], {
    cwd: path.dirname(entry),
    env: serverEnv(cfg, port, process.env, path.join(path.dirname(entry), 'server_modules')),
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  server.stdout?.pipe(log);
  server.stderr?.pipe(log);
  server.once('exit', code => {
    if (!app.isReady() || win === null) return;
    dialog.showErrorBox('Trading Assistant', `The local web server stopped (exit code ${code}). See ${logDir}.`);
    app.quit();
  });
  const origin = `http://127.0.0.1:${port}`;
  await waitForHttp(`${origin}/`, { timeoutMs: 30_000 });
  return origin;
}

/** Tell the user early if the FastAPI backend is not reachable instead of failing on the first question. */
async function checkBackend(cfg: DesktopConfig): Promise<void> {
  while (!(await httpOk(`${cfg.backendUrl}/health`, 3000))) {
    const { response } = await dialog.showMessageBox({
      type: 'warning',
      title: 'Trading Assistant',
      message: `The backend is not reachable at ${cfg.backendUrl}.`,
      detail: 'Start it first, for example: docker compose up   or   uvicorn app.main:app\n' +
        `You can point the app at another server with a BACKEND_URL environment variable or ${path.join(app.getPath('userData'), 'config.json')}.`,
      buttons: ['Retry', 'Continue anyway', 'Quit'],
      defaultId: 0,
      cancelId: 2,
    });
    if (response === 1) return;
    if (response === 2) {
      app.quit();
      return;
    }
  }
}

function lockDown(origin: string): void {
  session.defaultSession.setPermissionRequestHandler((_wc, _perm, cb) => cb(false));
  app.on('web-contents-created', (_e, contents) => {
    contents.on('will-navigate', (event, url) => {
      if (isSameOrigin(url, origin)) return;
      event.preventDefault();
      const ext = externalTarget(url);
      if (ext) void shell.openExternal(ext);
    });
    contents.setWindowOpenHandler(({ url }) => {
      const ext = externalTarget(url);
      if (ext) void shell.openExternal(ext);
      return { action: 'deny' };
    });
  });
}

async function createWindow(origin: string): Promise<void> {
  win = new BrowserWindow({
    width: 1100,
    height: 780,
    title: 'Trading Assistant',
    show: !SMOKE,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true },
  });
  win.removeMenu();
  win.on('closed', () => { win = null; });
  if (SMOKE) {
    win.webContents.once('did-finish-load', async () => {
      const title = await win!.webContents.executeJavaScript('document.title');
      const heading = await win!.webContents.executeJavaScript("document.querySelector('h1')?.textContent ?? ''");
      console.log(`SMOKE_OK ${JSON.stringify({ title, heading, origin })}`);
      app.quit();
    });
    setTimeout(() => { console.error('SMOKE_TIMEOUT'); app.exit(1); }, 60_000);
  }
  await win.loadURL(origin);
}

const gotLock = SMOKE || app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(async () => {
    try {
      const cfg = loadConfig(app.getPath('userData'));
      if (!SMOKE) await checkBackend(cfg);
      const origin = await startServer(cfg);
      lockDown(origin);
      await createWindow(origin);
    } catch (e) {
      dialog.showErrorBox('Trading Assistant could not start', e instanceof Error ? e.message : String(e));
      app.exit(1);
    }
  });
  app.on('window-all-closed', () => app.quit());
  app.on('before-quit', () => { server?.kill(); });
}
