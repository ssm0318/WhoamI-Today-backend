import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { readPointSources, writeAllocationFile } from './server.mjs';

test('readPointSources lists survey YAML and manual reimbursement sources', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'point-allocation-'));
  const fixtures = path.join(root, 'adoorback', 'surveys', 'fixtures');
  await mkdir(path.join(root, 'adoorback', 'surveys'), { recursive: true });
  await writeFile(
    path.join(root, 'adoorback', 'surveys', 'reimbursement_config.py'),
    'WIT_BOT_AUDIT_MAX_POINTS = 10\nINTERVIEW_SIGNUP_MAX_POINTS = 5\n',
  );
  await mkdir(fixtures, { recursive: true });
  await writeFile(
    path.join(fixtures, 'daily.yaml'),
    [
      '- slug: daily_base',
      '  title:',
      '    en: "Daily diary"',
      '  description:',
      '    en: "Long description that should not replace the title"',
      '  point_value: 3',
      '  point_prereq_slug: habit_platform',
      '  questions: []',
      '- slug: no_points',
      '  title_en: No points yet',
      '  questions: []',
      '',
    ].join('\n'),
  );

  const sources = await readPointSources(root);

  assert.deepEqual(
    sources.map((source) => [source.kind, source.slug, source.title_en, source.point_value]),
    [
      ['survey', 'daily_base', 'Daily diary', 3],
      ['survey', 'no_points', 'No points yet', 0],
      ['manual', 'wit_bot_audit', 'Wit_bot audit pass', 10],
      ['manual', 'interview_signup', 'Interview signup', 5],
    ],
  );
  assert.equal(sources[0].point_prereq_slug, 'habit_platform');
});

test('writeAllocationFile persists only the researcher editable point inputs', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'point-allocation-'));
  const outputPath = path.join(root, 'point-allocation.values.json');

  await writeAllocationFile(outputPath, [
    { kind: 'survey', slug: 'daily_base', points: 4 },
    { kind: 'manual', slug: 'wit_bot_audit', points: 12 },
  ]);

  const saved = JSON.parse(await readFile(outputPath, 'utf8'));
  assert.equal(saved.version, 1);
  assert.equal(saved.sources.length, 2);
  assert.deepEqual(saved.sources[0], { kind: 'survey', slug: 'daily_base', points: 4 });
  assert.match(saved.saved_at, /^\d{4}-\d{2}-\d{2}T/);
});

test('app table header is not offset into body rows', async () => {
  const html = await readFile(new URL('./app.html', import.meta.url), 'utf8');

  assert.doesNotMatch(html, /top:\s*(81|156)px/);
  assert.match(html, /th\s*{[\s\S]*top:\s*0;/);
});

test('app can use localhost API when opened as a file', async () => {
  const html = await readFile(new URL('./app.html', import.meta.url), 'utf8');

  assert.match(html, /location\.protocol === 'file:'/);
  assert.match(html, /http:\/\/localhost:4177/);
});
