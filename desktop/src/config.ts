import fs from 'node:fs';
import path from 'node:path';

export interface DesktopConfig {
  backendUrl: string;
  llmProvider: string;
  llmModel: string;
  ollamaUrl: string;
}

type Env = Record<string, string | undefined>;

export const DEFAULT_BACKEND = 'http://127.0.0.1:8000';

/** Backend must be http(s); the trailing slash is dropped so `${url}/tools/x` is always well formed. */
export function normalizeBackendUrl(raw: string): string {
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    throw new Error(`backendUrl is not a valid URL: ${raw}`);
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') {
    throw new Error(`backendUrl must start with http:// or https:// (got ${u.protocol})`);
  }
  return u.toString().replace(/\/+$/, '');
}

/**
 * Settings come from `<userData>/config.json`, overridden by environment variables.
 * Secrets such as ANTHROPIC_API_KEY are never read from or written to the file.
 */
export function loadConfig(userDataDir: string, env: Env = process.env): DesktopConfig {
  let file: Partial<DesktopConfig> = {};
  const p = path.join(userDataDir, 'config.json');
  if (fs.existsSync(p)) {
    try {
      file = JSON.parse(fs.readFileSync(p, 'utf8'));
    } catch (e) {
      throw new Error(`could not read ${p}: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  return {
    backendUrl: normalizeBackendUrl(env.BACKEND_URL || file.backendUrl || DEFAULT_BACKEND),
    llmProvider: env.LLM_PROVIDER || file.llmProvider || 'ollama',
    llmModel: env.LLM_MODEL || file.llmModel || '',
    ollamaUrl: env.OLLAMA_URL || file.ollamaUrl || 'http://localhost:11434',
  };
}

const PASS_THROUGH = ['PATH', 'SystemRoot', 'SYSTEMROOT', 'TEMP', 'TMP', 'USERPROFILE', 'HOME', 'APPDATA', 'LOCALAPPDATA'];

/** Environment for the local Next.js server process: an allow-list, not the whole parent environment. */
export function serverEnv(cfg: DesktopConfig, port: number, parent: Env = process.env, nodePath?: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of PASS_THROUGH) if (parent[k]) out[k] = parent[k] as string;
  Object.assign(out, {
    ELECTRON_RUN_AS_NODE: '1',
    NODE_ENV: 'production',
    PORT: String(port),
    HOSTNAME: '127.0.0.1',
    BACKEND_URL: cfg.backendUrl,
    LLM_PROVIDER: cfg.llmProvider,
    LLM_MODEL: cfg.llmModel,
    OLLAMA_URL: cfg.ollamaUrl,
  });
  if (nodePath) out.NODE_PATH = nodePath;   // electron-builder drops folders named node_modules, so the bundle ships it as server_modules
  if (cfg.llmProvider === 'anthropic' && parent.ANTHROPIC_API_KEY) out.ANTHROPIC_API_KEY = parent.ANTHROPIC_API_KEY;
  return out;
}
