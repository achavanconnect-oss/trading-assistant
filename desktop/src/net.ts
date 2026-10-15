import http from 'node:http';
import net from 'node:net';

/** Ask the OS for an unused local TCP port. */
export function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address() as net.AddressInfo;
      srv.close(() => resolve(port));
    });
  });
}

/** True if a GET to `url` answers with a 2xx or 3xx status within the timeout. */
export function httpOk(url: string, timeoutMs = 1500): Promise<boolean> {
  return new Promise(resolve => {
    const req = http.get(url, res => {
      res.resume();
      resolve((res.statusCode ?? 500) >= 200 && (res.statusCode ?? 500) < 400);
    });
    req.setTimeout(timeoutMs, () => req.destroy());
    req.on('error', () => resolve(false));
  });
}

export interface WaitOptions {
  timeoutMs?: number;
  intervalMs?: number;
  probe?: (url: string) => Promise<boolean>;
}

/** Poll until the URL answers, or throw when the deadline passes. */
export async function waitForHttp(url: string, opts: WaitOptions = {}): Promise<void> {
  const { timeoutMs = 30_000, intervalMs = 250, probe = httpOk } = opts;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    if (await probe(url)) return;
    if (Date.now() + intervalMs > deadline) throw new Error(`timed out after ${timeoutMs} ms waiting for ${url}`);
    await new Promise(r => setTimeout(r, intervalMs));
  }
}
