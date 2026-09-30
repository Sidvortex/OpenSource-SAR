// Runs the shared dance test cases against the TypeScript classifier.
import { readFileSync } from 'node:fs';
import { classify } from '../src/dance';

const { cases } = JSON.parse(readFileSync(new URL('../../data/dance_tests.json', import.meta.url), 'utf8'));
let failed = 0;
for (const c of cases) {
  const got = classify(c.t, c.y, c.sigma).dance;
  const ok = got === c.expected;
  if (!ok) failed++;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${c.name.padEnd(26)} expected ${c.expected.padEnd(10)} got ${got}`);
}
console.log(`${cases.length - failed}/${cases.length} passed`);
process.exit(failed ? 1 : 0);
