// Build the Next.js app (../web) and copy its standalone server into desktop/web-server for packaging.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.resolve(here, '..', '..', 'web');
const out = path.resolve(here, '..', 'web-server');

const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
if (!fs.existsSync(path.join(web, 'node_modules'))) {
  console.log('installing web dependencies...');
  const r = spawnSync(npm, ['ci'], { cwd: web, stdio: 'inherit', shell: process.platform === 'win32' });
  if (r.status !== 0) process.exit(r.status ?? 1);
}
const build = spawnSync(npm, ['run', 'build'], { cwd: web, stdio: 'inherit', shell: process.platform === 'win32', env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1' } });
if (build.status !== 0) process.exit(build.status ?? 1);

const standalone = path.join(web, '.next', 'standalone');
if (!fs.existsSync(path.join(standalone, 'server.js'))) {
  console.error(`missing ${standalone}/server.js: is output: 'standalone' set in web/next.config.ts?`);
  process.exit(1);
}
fs.rmSync(out, { recursive: true, force: true });
fs.cpSync(standalone, out, { recursive: true });
fs.cpSync(path.join(web, '.next', 'static'), path.join(out, '.next', 'static'), { recursive: true });
// electron-builder never copies folders named node_modules into extraResources; main.ts points NODE_PATH at this one
fs.renameSync(path.join(out, 'node_modules'), path.join(out, 'server_modules'));
console.log(`web server bundle ready: ${out}`);
