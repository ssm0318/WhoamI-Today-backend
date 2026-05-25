import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('app labels priority levels 1 and 2 with participant-facing badges', async () => {
  const html = await readFile(new URL('./app.html', import.meta.url), 'utf8');

  assert.match(html, /Prerequisite\/Must Complete/);
  assert.match(html, /High Priority/);
  assert.match(html, /policyDraftValue\(source,\s*'priority_rating'\)/);
});
