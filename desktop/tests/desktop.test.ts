import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { DEFAULT_BACKEND, loadConfig, normalizeBackendUrl, serverEnv } from '../src/config';
import { freePort, httpOk, waitForHttp } from '../src/net';
import { externalTarget, isSameOrigin } from '../src/security';

describe('navigation policy', () => {
  const origin = 'http://127.0.0.1:4321';

  it('allows only the local server origin inside the window', () => {
    expect(isSameOrigin('http://127.0.0.1:4321/api/chat', origin)).toBe(true);
    expect(isSameOrigin('http://127.0.0.1:9999/', origin)).toBe(false);
    expect(isSameOrigin('https://evil.example/', origin)).toBe(false);
    expect(isSameOrigin('not a url', origin)).toBe(false);
  });

  it('opens only https links externally, never file:, javascript: or http:', () => {
    expect(externalTarget('https://github.com/vercel/ai')).toBe('https://github.com/vercel/ai');
    for (const bad of ['http://example.com', 'file:///C:/Windows/System32/calc.exe', 'javascript:alert(1)', 'ms-msdt:/id', 'garbage'])
      expect(externalTarget(bad)).toBeNull();
  });
});

describe('config', () => {
  let dir = '';
  afterEach(() => dir && fs.rmSync(dir, { recursive: true, force: true }));
  const tmp = () => (dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ta-desktop-')));

  it('normalises and validates the backend URL', () => {
    expect(normalizeBackendUrl('http://10.0.0.5:8000/')).toBe('http://10.0.0.5:8000');
    expect(() => normalizeBackendUrl('ftp://x')).toThrow('http');
    expect(() => normalizeBackendUrl('file:///etc/passwd')).toThrow('http');
    expect(() => normalizeBackendUrl('nonsense')).toThrow('not a valid URL');
  });

  it('uses defaults, then config.json, then environment variables', () => {
    const d = tmp();
    expect(loadConfig(d, {})).toEqual({ backendUrl: DEFAULT_BACKEND, llmProvider: 'ollama', llmModel: '', ollamaUrl: 'http://localhost:11434' });
    fs.writeFileSync(path.join(d, 'config.json'), JSON.stringify({ backendUrl: 'http://server:9000', llmModel: 'llama3.1:8b' }));
    expect(loadConfig(d, {})).toMatchObject({ backendUrl: 'http://server:9000', llmModel: 'llama3.1:8b' });
    expect(loadConfig(d, { BACKEND_URL: 'https://prod.example.com/' }).backendUrl).toBe('https://prod.example.com');
  });

  it('reports an unreadable config file and an invalid URL in it', () => {
    const d = tmp();
    fs.writeFileSync(path.join(d, 'config.json'), '{ not json');
    expect(() => loadConfig(d, {})).toThrow('could not read');
    fs.writeFileSync(path.join(d, 'config.json'), JSON.stringify({ backendUrl: 'javascript:alert(1)' }));
    expect(() => loadConfig(d, {})).toThrow('backendUrl');
  });

  it('gives the web server an allow-listed environment and forwards the API key only for Anthropic', () => {
    const parent = { PATH: 'C:\\bin', ANTHROPIC_API_KEY: 'sk-secret', AWS_SECRET_ACCESS_KEY: 'leak-me', GITHUB_TOKEN: 'leak-me-too' };
    const ollama = serverEnv({ backendUrl: 'http://b', llmProvider: 'ollama', llmModel: '', ollamaUrl: 'http://o' }, 4321, parent);
    expect(ollama).toMatchObject({ PORT: '4321', HOSTNAME: '127.0.0.1', BACKEND_URL: 'http://b', ELECTRON_RUN_AS_NODE: '1', PATH: 'C:\\bin' });
    expect(Object.keys(ollama)).not.toContain('ANTHROPIC_API_KEY');
    expect(Object.keys(ollama)).not.toContain('AWS_SECRET_ACCESS_KEY');
    expect(Object.keys(ollama)).not.toContain('GITHUB_TOKEN');
    expect(serverEnv({ backendUrl: 'http://b', llmProvider: 'ollama', llmModel: '', ollamaUrl: 'http://o' }, 1, {}, 'C:\app\server_modules').NODE_PATH).toBe('C:\app\server_modules');
    const claude = serverEnv({ backendUrl: 'http://b', llmProvider: 'anthropic', llmModel: '', ollamaUrl: 'http://o' }, 4321, parent);
    expect(claude.ANTHROPIC_API_KEY).toBe('sk-secret');
    expect(Object.keys(claude)).not.toContain('AWS_SECRET_ACCESS_KEY');
  });
});

describe('net helpers', () => {
  const servers: http.Server[] = [];
  afterEach(() => { servers.splice(0).forEach(s => s.close()); });
  const listen = (handler: http.RequestListener, port = 0) =>
    new Promise<number>(resolve => {
      const s = http.createServer(handler);
      servers.push(s);
      s.listen(port, '127.0.0.1', () => resolve((s.address() as { port: number }).port));
    });

  it('freePort returns a usable port', async () => {
    const p = await freePort();
    expect(p).toBeGreaterThan(1023);
    await expect(listen((_q, r) => r.end('ok'), p)).resolves.toBe(p);
  });

  it('httpOk is true for 200, false for 500 and for a closed port', async () => {
    const ok = await listen((_q, r) => r.end('ok'));
    const bad = await listen((_q, r) => { r.statusCode = 500; r.end(); });
    expect(await httpOk(`http://127.0.0.1:${ok}/`)).toBe(true);
    expect(await httpOk(`http://127.0.0.1:${bad}/`)).toBe(false);
    expect(await httpOk(`http://127.0.0.1:${await freePort()}/`, 300)).toBe(false);
  });

  it('waitForHttp resolves once the server starts answering and times out otherwise', async () => {
    const port = await freePort();
    setTimeout(() => void listen((_q, r) => r.end('ok'), port), 400);
    await expect(waitForHttp(`http://127.0.0.1:${port}/`, { timeoutMs: 5000, intervalMs: 100 })).resolves.toBeUndefined();
    await expect(waitForHttp(`http://127.0.0.1:${await freePort()}/`, { timeoutMs: 400, intervalMs: 100 })).rejects.toThrow('timed out');
  });
});
