// Copies the repo's shared /data folder into web/public/data so Vite serves it.
// One source of truth: the pipeline writes /data, the site reads it.
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, '../../data');
const target = resolve(here, '../public/data');

if (!existsSync(source)) {
  console.error(`No data folder at ${source}`);
  process.exit(1);
}
rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
cpSync(source, target, { recursive: true });
console.log(`Synced ${source} -> ${target}`);
