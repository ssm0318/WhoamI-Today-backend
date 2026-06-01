import assert from 'node:assert/strict';
import { chmod, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { buildReimbursementPreview, readPointSources, writeAllocationFile } from './server.mjs';

test('readPointSources lists survey YAML and manual reimbursement sources', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'point-allocation-'));
  const fixtures = path.join(root, 'adoorback', 'surveys', 'fixtures');
  await mkdir(path.join(root, 'adoorback', 'surveys'), { recursive: true });
  await writeFile(
    path.join(root, 'adoorback', 'surveys', 'reimbursement_config.py'),
    [
      'WIT_BOT_AUDIT_PHASE_1_MAX_POINTS = 10',
      'WIT_BOT_AUDIT_PHASE_2_MAX_POINTS = 12',
      'APP_USAGE_PHASE_1_FULL_POINTS = 50',
      'APP_USAGE_PHASE_2_FULL_POINTS = 50',
      'INTERVIEW_SIGNUP_MAX_POINTS = 5',
      'FRIEND_INVITE_MAX_POINTS = 500',
      '',
    ].join('\n'),
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
      '  priority: 80',
      '  repeatable: true',
      '  point_value: 3',
      '  point_prereq_slug: habit_platform',
      '  questions:',
      '    - order: 1',
      '      slug: mood',
      '      type: likert_5',
      '      prompt:',
      '        en: "How was today?"',
      '      low_label:',
      '        en: "Bad"',
      '      high_label:',
      '        en: "Good"',
      '    - order: 2',
      '      slug: note',
      '      type: free_text',
      '      prompt:',
      '        en: "Anything else?"',
      '      required: false',
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
      ['manual', 'wit_bot_audit_phase_1', 'Wit_bot audit pass - Phase 1', 10],
      ['manual', 'wit_bot_audit_phase_2', 'Wit_bot audit pass - Phase 2', 12],
      ['manual', 'app_usage_phase_1', 'App usage - Phase 1', 50],
      ['manual', 'app_usage_phase_2', 'App usage - Phase 2', 50],
      ['manual', 'interview_signup', 'Interview signup', 5],
      ['manual', 'friend_invite', 'Friend invite reimbursement', 500],
    ],
  );
  assert.equal(sources[0].point_prereq_slug, 'habit_platform');
  assert.equal(sources[0].priority, 80);
  assert.equal(sources[0].repeatable, true);
  assert.equal(sources[0].question_count, 2);
  assert.deepEqual(sources[0].question_metrics.visible_total_range, { min: 2, max: 2 });
  assert.deepEqual(sources[0].question_metrics.visible_mcq_range, { min: 0, max: 0 });
  assert.deepEqual(sources[0].question_metrics.visible_frq_range, { min: 1, max: 1 });
  assert.equal(sources[0].question_metrics.depends_on_user, false);
  assert.equal(sources[0].questions[0].prompt_en, 'How was today?');
  assert.equal(sources[0].questions[1].required, false);
  assert.equal(sources[0].app_url, 'http://localhost:3000/surveys/daily_base/answer');
  const inviteSource = sources.find((source) => source.slug === 'friend_invite');
  assert.equal(inviteSource.current_points_label, 'To be updated');
  assert.equal(inviteSource.file, 'account_user.invited_from_id (pending)');
  assert.match(inviteSource.description_en, /100 pts per invited friend/);
});

test('readPointSources parses indentless question lists without counting options', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'point-allocation-'));
  const fixtures = path.join(root, 'adoorback', 'surveys', 'fixtures');
  await mkdir(fixtures, { recursive: true });
  await writeFile(
    path.join(fixtures, 'recovery.yaml'),
    [
      '- slug: study_endpoint_part2',
      '  title:',
      '    en: "What happens next with WIT: Part 2"',
      '  questions:',
      '  - order: 1',
      '    slug: cadence_dailyq_freq',
      '    type: single_choice',
      '    prompt:',
      '      en: "Daily questions cadence?"',
      '    options:',
      '    - order: 1',
      '      value: never',
      '      label:',
      '        en: Never',
      '    - order: 2',
      '      value: weekly',
      '      label:',
      '        en: Weekly',
      '  - order: 2',
      '    slug: cadence_dailyq_reason',
      '    type: free_text',
      '    prompt:',
      '      en: "Why that rhythm?"',
      '    required: false',
      '',
    ].join('\n'),
  );

  const sources = await readPointSources(root);
  const survey = sources.find((source) => source.slug === 'study_endpoint_part2');

  assert.equal(survey.question_count, 2);
  assert.equal(survey.questions[0].slug, 'cadence_dailyq_freq');
  assert.equal(survey.questions[0].type, 'single_choice');
  assert.equal(survey.questions[0].prompt_en, 'Daily questions cadence?');
  assert.deepEqual(survey.questions[0].options, [
    { order: 1, value: 'never', label_en: 'Never' },
    { order: 2, value: 'weekly', label_en: 'Weekly' },
  ]);
  assert.deepEqual(survey.question_metrics.visible_total_range, { min: 2, max: 2 });
  assert.deepEqual(survey.question_metrics.visible_mcq_range, { min: 1, max: 1 });
  assert.deepEqual(survey.question_metrics.visible_frq_range, { min: 1, max: 1 });
  assert.equal(survey.questions[1].slug, 'cadence_dailyq_reason');
  assert.equal(survey.questions[1].required, false);
});

test('readPointSources marks per-friend question metrics as user-dependent', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'point-allocation-'));
  const fixtures = path.join(root, 'adoorback', 'surveys', 'fixtures');
  await mkdir(fixtures, { recursive: true });
  await writeFile(
    path.join(fixtures, 'closeness_reeval.yaml'),
    [
      '- slug: phase1_friend_closeness',
      '  title_en: Friend closeness',
      '  questions:',
      '    - order: 1',
      '      slug: current',
      '      type: per_friend_likert_5',
      '    - order: 2',
      '      slug: offline',
      '      type: per_friend_single_choice',
      '    - order: 3',
      '      slug: note',
      '      type: free_text',
      '',
    ].join('\n'),
  );

  const sources = await readPointSources(root);
  const survey = sources.find((source) => source.slug === 'phase1_friend_closeness');

  assert.equal(survey.question_metrics.authored_total, 3);
  assert.equal(survey.question_metrics.authored_mcq, 1);
  assert.equal(survey.question_metrics.authored_frq, 1);
  assert.equal(survey.question_metrics.per_friend_total, 2);
  assert.equal(survey.question_metrics.per_friend_mcq, 1);
  assert.equal(survey.question_metrics.depends_on_user, true);
  assert.equal(survey.question_metrics.exact_range, false);
});

test('readPointSources includes DB participant response counts for participant ids 8-87', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'point-allocation-'));
  const fixtures = path.join(root, 'adoorback', 'surveys', 'fixtures');
  const fakePython = path.join(root, 'fake-python.sh');
  await mkdir(fixtures, { recursive: true });
  await writeFile(path.join(root, 'adoorback', 'manage.py'), '');
  await writeFile(
    fakePython,
    [
      '#!/bin/sh',
      'case "$2" in',
      '  *"user_id__gte=8"*"user_id__lte=87"*) ;;',
      '  *) echo "missing participant id range" >&2; exit 1 ;;',
      'esac',
      'cat <<\'JSON\'',
      '{"daily_base":{"visible_total_range":{"min":2,"max":2},"visible_mcq_range":{"min":1,"max":1},"visible_frq_range":{"min":1,"max":1},"user_count":80,"participant_response_count":17}}',
      'JSON',
      '',
    ].join('\n'),
  );
  await chmod(fakePython, 0o755);
  await writeFile(
    path.join(fixtures, 'daily.yaml'),
    [
      '- slug: daily_base',
      '  title_en: Daily diary',
      '  questions:',
      '    - order: 1',
      '      slug: mood',
      '      type: single_choice',
      '    - order: 2',
      '      slug: note',
      '      type: free_text',
      '',
    ].join('\n'),
  );

  const previousPython = process.env.POINT_ALLOCATION_PYTHON;
  process.env.POINT_ALLOCATION_PYTHON = fakePython;
  try {
    const sources = await readPointSources(root);
    const survey = sources.find((source) => source.slug === 'daily_base');

    assert.equal(survey.participant_response_count, 17);
    assert.equal(survey.participant_response_label, '17');
    assert.deepEqual(survey.question_metrics.visible_total_range, { min: 2, max: 2 });
  } finally {
    if (previousPython === undefined) {
      delete process.env.POINT_ALLOCATION_PYTHON;
    } else {
      process.env.POINT_ALLOCATION_PYTHON = previousPython;
    }
  }
});

test('readPointSources prefers remote DB participant counts when remote SSH is configured', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'point-allocation-'));
  const fixtures = path.join(root, 'adoorback', 'surveys', 'fixtures');
  const fakePython = path.join(root, 'fake-python.sh');
  const fakeSsh = path.join(root, 'fake-ssh.sh');
  await mkdir(fixtures, { recursive: true });
  await writeFile(path.join(root, 'adoorback', 'manage.py'), '');
  await writeFile(
    fakePython,
    [
      '#!/bin/sh',
      'cat <<\'JSON\'',
      '{"daily_base":{"visible_total_range":{"min":2,"max":2},"visible_mcq_range":{"min":1,"max":1},"visible_frq_range":{"min":1,"max":1},"user_count":80,"participant_response_count":0}}',
      'JSON',
      '',
    ].join('\n'),
  );
  await chmod(fakePython, 0o755);
  await writeFile(
    fakeSsh,
    [
      '#!/bin/sh',
      'case "$*" in',
      '  *"BETWEEN 8 AND 87"*) ;;',
      '  *) echo "missing participant id range" >&2; exit 1 ;;',
      'esac',
      'printf "daily_base|13\\n"',
      '',
    ].join('\n'),
  );
  await chmod(fakeSsh, 0o755);
  await writeFile(
    path.join(fixtures, 'daily.yaml'),
    [
      '- slug: daily_base',
      '  title_en: Daily diary',
      '  questions:',
      '    - order: 1',
      '      slug: mood',
      '      type: single_choice',
      '    - order: 2',
      '      slug: note',
      '      type: free_text',
      '',
    ].join('\n'),
  );

  const previousPython = process.env.POINT_ALLOCATION_PYTHON;
  const previousRemoteSsh = process.env.POINT_ALLOCATION_REMOTE_SSH;
  const previousSshCommand = process.env.POINT_ALLOCATION_SSH_COMMAND;
  const previousRemoteDir = process.env.POINT_ALLOCATION_REMOTE_DIR;
  try {
    process.env.POINT_ALLOCATION_PYTHON = fakePython;
    process.env.POINT_ALLOCATION_REMOTE_SSH = 'fake-host';
    process.env.POINT_ALLOCATION_SSH_COMMAND = fakeSsh;
    process.env.POINT_ALLOCATION_REMOTE_DIR = '/tmp/remote-whoami';

    const sources = await readPointSources(root);
    const survey = sources.find((source) => source.slug === 'daily_base');

    assert.equal(survey.participant_response_count, 13);
    assert.equal(survey.participant_response_label, '13');
    assert.equal(survey.participant_response_source, 'remote');
  } finally {
    if (previousPython === undefined) delete process.env.POINT_ALLOCATION_PYTHON;
    else process.env.POINT_ALLOCATION_PYTHON = previousPython;
    if (previousRemoteSsh === undefined) delete process.env.POINT_ALLOCATION_REMOTE_SSH;
    else process.env.POINT_ALLOCATION_REMOTE_SSH = previousRemoteSsh;
    if (previousSshCommand === undefined) delete process.env.POINT_ALLOCATION_SSH_COMMAND;
    else process.env.POINT_ALLOCATION_SSH_COMMAND = previousSshCommand;
    if (previousRemoteDir === undefined) delete process.env.POINT_ALLOCATION_REMOTE_DIR;
    else process.env.POINT_ALLOCATION_REMOTE_DIR = previousRemoteDir;
  }
});

test('readPointSources does not fall back to local participant counts when remote SSH fails', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'point-allocation-'));
  const fixtures = path.join(root, 'adoorback', 'surveys', 'fixtures');
  const fakePython = path.join(root, 'fake-python.sh');
  const fakeSsh = path.join(root, 'fake-ssh.sh');
  await mkdir(fixtures, { recursive: true });
  await writeFile(path.join(root, 'adoorback', 'manage.py'), '');
  await writeFile(
    fakePython,
    [
      '#!/bin/sh',
      'cat <<\'JSON\'',
      '{"daily_base":{"visible_total_range":{"min":2,"max":2},"visible_mcq_range":{"min":1,"max":1},"visible_frq_range":{"min":1,"max":1},"user_count":80,"participant_response_count":99}}',
      'JSON',
      '',
    ].join('\n'),
  );
  await chmod(fakePython, 0o755);
  await writeFile(fakeSsh, '#!/bin/sh\nexit 1\n');
  await chmod(fakeSsh, 0o755);
  await writeFile(
    path.join(fixtures, 'daily.yaml'),
    [
      '- slug: daily_base',
      '  title_en: Daily diary',
      '  questions:',
      '    - order: 1',
      '      slug: mood',
      '      type: single_choice',
      '',
    ].join('\n'),
  );

  const previousPython = process.env.POINT_ALLOCATION_PYTHON;
  const previousRemoteSsh = process.env.POINT_ALLOCATION_REMOTE_SSH;
  const previousSshCommand = process.env.POINT_ALLOCATION_SSH_COMMAND;
  try {
    process.env.POINT_ALLOCATION_PYTHON = fakePython;
    process.env.POINT_ALLOCATION_REMOTE_SSH = 'fake-host';
    process.env.POINT_ALLOCATION_SSH_COMMAND = fakeSsh;

    const sources = await readPointSources(root);
    const survey = sources.find((source) => source.slug === 'daily_base');

    assert.equal(survey.participant_response_count, null);
    assert.equal(survey.participant_response_label, 'Remote unavailable');
    assert.equal(survey.participant_response_source, 'remote_unavailable');
  } finally {
    if (previousPython === undefined) delete process.env.POINT_ALLOCATION_PYTHON;
    else process.env.POINT_ALLOCATION_PYTHON = previousPython;
    if (previousRemoteSsh === undefined) delete process.env.POINT_ALLOCATION_REMOTE_SSH;
    else process.env.POINT_ALLOCATION_REMOTE_SSH = previousRemoteSsh;
    if (previousSshCommand === undefined) delete process.env.POINT_ALLOCATION_SSH_COMMAND;
    else process.env.POINT_ALLOCATION_SSH_COMMAND = previousSshCommand;
  }
});

test('writeAllocationFile persists point inputs and reimbursement policy controls', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'point-allocation-'));
  const outputPath = path.join(root, 'point-allocation.values.json');

  await writeAllocationFile(outputPath, [
    {
      kind: 'survey',
      slug: 'daily_base',
      points: 4,
      priority_rating: 5,
      cap_group: 'daily_diary',
      cap_points: 60,
      gate_slug: 'feature_eval_w',
      late_percent: 50,
    },
    { kind: 'manual', slug: 'wit_bot_audit_phase_1', points: 12 },
  ]);

  const saved = JSON.parse(await readFile(outputPath, 'utf8'));
  assert.equal(saved.version, 1);
  assert.equal(saved.sources.length, 2);
  assert.deepEqual(saved.sources[0], {
    kind: 'survey',
    slug: 'daily_base',
    points: 4,
    priority_rating: 5,
    cap_group: 'daily_diary',
    cap_points: 60,
    gate_slug: 'feature_eval_w',
    late_percent: 50,
  });
  assert.deepEqual(saved.sources[1], {
    kind: 'manual',
    slug: 'wit_bot_audit_phase_1',
    points: 12,
    priority_rating: 0,
    cap_group: '',
    cap_points: null,
    gate_slug: '',
    late_percent: 100,
  });
  assert.match(saved.saved_at, /^\d{4}-\d{2}-\d{2}T/);
});

test('buildReimbursementPreview applies merged DB responses, gates, and recurring caps', () => {
  const preview = buildReimbursementPreview({
    sources: [
      {
        kind: 'survey',
        id: 'survey:daily_base',
        slug: 'daily_base',
        title_en: 'Daily diary',
        category_label: 'Daily diary',
        draft_points: 3,
        draft_priority_rating: 1,
        draft_cap_group: 'daily',
        draft_cap_points: 30,
        draft_gate_slug: '',
        draft_late_percent: 100,
      },
      {
        kind: 'survey',
        id: 'survey:feature_eval_w',
        slug: 'feature_eval_w',
        title_en: 'W feature evaluation',
        category_label: 'Phase / feature surveys',
        draft_points: 50,
        draft_priority_rating: 2,
        draft_cap_group: '',
        draft_cap_points: null,
        draft_gate_slug: 'goal_comparison_p1',
        draft_late_percent: 100,
      },
      {
        kind: 'survey',
        id: 'survey:goal_comparison_p1',
        slug: 'goal_comparison_p1',
        title_en: 'Goal comparison',
        category_label: 'Phase / feature surveys',
        draft_points: 10,
        draft_cap_group: '',
        draft_cap_points: null,
        draft_gate_slug: '',
        draft_late_percent: 50,
      },
      {
        kind: 'manual',
        id: 'manual:wit_bot_audit_phase_1',
        slug: 'wit_bot_audit_phase_1',
        title_en: 'Wit_bot audit pass - Phase 1',
        category_label: 'Manual activities',
        draft_points: 20,
        draft_cap_group: '',
        draft_cap_points: null,
        draft_gate_slug: '',
        draft_late_percent: 100,
      },
    ],
    participants: [
      { id: 8, username: 'participant_8', userGroup: 'group_w_first' },
      { id: 9, username: 'participant_9', userGroup: 'group_q_first' },
    ],
    responseCounts: new Map([
      [8, new Map([['daily_base', 12], ['feature_eval_w', 1]])],
      [9, new Map([['daily_base', 2], ['goal_comparison_p1', 1]])],
    ]),
    pointAwardCounts: new Map([[8, new Map([['wit_bot_audit_phase_1', 1]])]]),
    requestedUserId: 8,
  });

  assert.equal(preview.db.name, 'whoamitoday_merged');
  assert.equal(preview.selectedUser.id, 8);
  assert.equal(preview.availableMax, 110);
  assert.equal(preview.earnedPoints, 50);
  assert.equal(preview.estimatedDollars, '5.00');
  assert.equal(preview.capRules[0].group, 'daily');
  assert.equal(preview.capRules[0].earnedPoints, 30);
  assert.equal(preview.gateRules[0].slug, 'feature_eval_w');

  const daily = preview.rows.find((row) => row.slug === 'daily_base');
  assert.equal(daily.completedCount, 12);
  assert.equal(daily.points, 30);
  assert.equal(daily.priorityRating, 1);
  assert.equal(daily.status, 'earned');

  const gated = preview.rows.find((row) => row.slug === 'feature_eval_w');
  assert.equal(gated.completedCount, 1);
  assert.equal(gated.points, 0);
  assert.equal(gated.priorityRating, 2);
  assert.equal(gated.status, 'locked');
  assert.match(gated.note, /goal_comparison_p1/);

  const manual = preview.rows.find((row) => row.slug === 'wit_bot_audit_phase_1');
  assert.equal(manual.completedCount, 1);
  assert.equal(manual.points, 20);
  assert.equal(manual.status, 'earned');
});

test('buildReimbursementPreview filters versioned surveys to the selected participant route', () => {
  const preview = buildReimbursementPreview({
    sources: [
      {
        kind: 'survey',
        id: 'survey:mid_study_w',
        slug: 'mid_study_w',
        title_en: 'Mid study W',
        category_label: 'Phase / feature surveys',
        draft_points: 30,
      },
      {
        kind: 'survey',
        id: 'survey:mid_study_q',
        slug: 'mid_study_q',
        title_en: 'Mid study Q',
        category_label: 'Phase / feature surveys',
        draft_points: 35,
      },
      {
        kind: 'survey',
        id: 'survey:feature_eval_w',
        slug: 'feature_eval_w',
        title_en: 'Feature eval W',
        category_label: 'Phase / feature surveys',
        draft_points: 50,
      },
    ],
    participants: [{ id: 9, username: 'participant_9', userGroup: 'group_q_first' }],
    responseCounts: new Map([[9, new Map([['mid_study_q', 1], ['feature_eval_w', 1]])]]),
    sourceRoutings: new Map([['feature_eval_w', new Set(['group_q_first'])]]),
    requestedUserId: 9,
  });

  assert.deepEqual(
    preview.rows.map((row) => row.slug),
    ['mid_study_q', 'feature_eval_w'],
  );
  assert.equal(preview.availableMax, 85);
  assert.equal(preview.earnedPoints, 85);
});

test('buildReimbursementPreview marks answerable and expired survey actions', () => {
  const preview = buildReimbursementPreview({
    sources: [
      {
        kind: 'survey',
        id: 'survey:open_survey',
        slug: 'open_survey',
        title_en: 'Open survey',
        category_label: 'Survey',
        draft_points: 10,
        app_url: 'http://localhost:3000/surveys/open_survey/answer',
      },
      {
        kind: 'survey',
        id: 'survey:expired_survey',
        slug: 'expired_survey',
        title_en: 'Expired survey',
        category_label: 'Survey',
        draft_points: 12,
        app_url: 'http://localhost:3000/surveys/expired_survey/answer',
      },
      {
        kind: 'survey',
        id: 'survey:future_survey',
        slug: 'future_survey',
        title_en: 'Future survey',
        category_label: 'Survey',
        draft_points: 15,
        app_url: 'http://localhost:3000/surveys/future_survey/answer',
      },
      {
        kind: 'manual',
        id: 'manual:wit_bot_audit_phase_1',
        slug: 'wit_bot_audit_phase_1',
        title_en: 'Wit_bot audit pass - Phase 1',
        category_label: 'Manual activities',
        draft_points: 20,
      },
    ],
    participants: [{ id: 8, username: 'participant_8', userGroup: 'group_w_first' }],
    responseCounts: new Map([[8, new Map()]]),
    sourceSchedules: new Map([
      [
        'open_survey',
        [
          {
            targetUserGroup: 'group_w_first',
            windowStart: '2026-05-01',
            windowEnd: '2026-05-30',
            allowLate: false,
          },
        ],
      ],
      [
        'expired_survey',
        [
          {
            targetUserGroup: 'group_w_first',
            windowStart: '2026-05-01',
            windowEnd: '2026-05-10',
            allowLate: false,
          },
        ],
      ],
      [
        'future_survey',
        [
          {
            targetUserGroup: 'group_w_first',
            windowStart: '2026-06-01',
            windowEnd: '2026-06-10',
            allowLate: false,
          },
        ],
      ],
    ]),
    requestedUserId: 8,
    currentDate: '2026-05-25',
  });

  const open = preview.rows.find((row) => row.slug === 'open_survey');
  assert.equal(open.appUrl, 'http://localhost:3000/surveys/open_survey/answer');
  assert.equal(open.canEarn, true);

  const expired = preview.rows.find((row) => row.slug === 'expired_survey');
  assert.equal(expired.appUrl, 'http://localhost:3000/surveys/expired_survey/answer');
  assert.equal(expired.canEarn, false);
  assert.equal(expired.availability, 'deadline');
  assert.match(expired.note, /deadline/i);

  const future = preview.rows.find((row) => row.slug === 'future_survey');
  assert.equal(future.canEarn, false);
  assert.equal(future.availability, 'future');
  assert.match(future.note, /not available yet/i);

  const witBot = preview.rows.find((row) => row.slug === 'wit_bot_audit_phase_1');
  assert.equal(witBot.appUrl, '/users/7/chat');
  assert.equal(witBot.canEarn, false);
  assert.equal(witBot.availability, 'deadline');
  assert.match(witBot.note, /deadline/i);
});

test('buildReimbursementPreview applies reimbursement-specific deadline overrides', () => {
  const baseSources = [
    {
      kind: 'manual',
      id: 'manual:interview_signup',
      slug: 'interview_signup',
      title_en: 'Interview signup',
      category_label: 'Manual activities',
      draft_points: 200,
    },
    {
      kind: 'manual',
      id: 'manual:friend_invite',
      slug: 'friend_invite',
      title_en: 'Friend invite reimbursement',
      category_label: 'Manual activities',
      draft_points: 500,
    },
    {
      kind: 'survey',
      id: 'survey:feature_eval_w',
      slug: 'feature_eval_w',
      title_en: 'Ver. W features',
      category_label: 'Survey',
      draft_points: 20,
      draft_late_percent: 50,
      app_url: 'http://localhost:3000/surveys/feature_eval_w/answer',
    },
  ];
  const sourceSchedules = new Map([
    [
      'feature_eval_w',
      [
        {
          targetUserGroup: 'group_w_first',
          windowStart: '2026-05-08',
          windowEnd: '2026-05-24',
          allowLate: true,
        },
        {
          targetUserGroup: 'group_q_first',
          windowStart: '2026-05-22',
          windowEnd: '2026-05-24',
          allowLate: true,
        },
      ],
    ],
  ]);

  const qFirstPreview = buildReimbursementPreview({
    sources: baseSources,
    participants: [{ id: 9, username: 'q_first', userGroup: 'group_q_first' }],
    responseCounts: new Map([[9, new Map()]]),
    sourceRoutings: new Map([['feature_eval_w', new Set(['group_w_first', 'group_q_first'])]]),
    sourceSchedules,
    requestedUserId: 9,
    currentDate: '2026-05-25',
  });

  assert.equal(qFirstPreview.rows.find((row) => row.slug === 'interview_signup').canEarn, true);
  assert.equal(
    qFirstPreview.rows.find((row) => row.slug === 'interview_signup').availability,
    'available',
  );
  assert.equal(
    qFirstPreview.rows.find((row) => row.slug === 'interview_signup').appUrl,
    'https://calendly.com/jaewonkim/60min',
  );
  assert.equal(qFirstPreview.rows.find((row) => row.slug === 'friend_invite').canEarn, false);
  assert.equal(
    qFirstPreview.rows.find((row) => row.slug === 'friend_invite').availability,
    'deadline',
  );
  assert.equal(qFirstPreview.rows.find((row) => row.slug === 'feature_eval_w').canEarn, true);
  assert.equal(
    qFirstPreview.rows.find((row) => row.slug === 'feature_eval_w').availability,
    'late',
  );
  assert.equal(qFirstPreview.rows.find((row) => row.slug === 'feature_eval_w').currentPossiblePoints, 10);
  assert.match(qFirstPreview.rows.find((row) => row.slug === 'feature_eval_w').note, /late/i);

  const afterOpenPreview = buildReimbursementPreview({
    sources: baseSources,
    participants: [{ id: 9, username: 'q_first', userGroup: 'group_q_first' }],
    responseCounts: new Map([[9, new Map()]]),
    sourceRoutings: new Map([['feature_eval_w', new Set(['group_w_first', 'group_q_first'])]]),
    sourceSchedules,
    requestedUserId: 9,
    currentDate: '2026-06-01',
  });
  assert.equal(afterOpenPreview.rows.find((row) => row.slug === 'interview_signup').canEarn, true);
  assert.equal(
    afterOpenPreview.rows.find((row) => row.slug === 'interview_signup').availability,
    'available',
  );

  const wFirstPreview = buildReimbursementPreview({
    sources: baseSources,
    participants: [{ id: 8, username: 'w_first', userGroup: 'group_w_first' }],
    responseCounts: new Map([[8, new Map()]]),
    sourceRoutings: new Map([['feature_eval_w', new Set(['group_w_first', 'group_q_first'])]]),
    sourceSchedules,
    requestedUserId: 8,
    currentDate: '2026-05-25',
  });

  assert.equal(wFirstPreview.rows.find((row) => row.slug === 'feature_eval_w').canEarn, true);
  assert.equal(
    wFirstPreview.rows.find((row) => row.slug === 'feature_eval_w').availability,
    'available',
  );
  assert.equal(wFirstPreview.rows.find((row) => row.slug === 'feature_eval_w').currentPossiblePoints, 20);
});

test('app table header is not offset into body rows', async () => {
  const html = await readFile(new URL('./app.html', import.meta.url), 'utf8');

  assert.doesNotMatch(html, /top:\s*(81|156)px/);
  assert.match(html, /th\s*{[\s\S]*top:\s*0;/);
});

test('app table fills the viewport with its own scroll area', async () => {
  const html = await readFile(new URL('./app.html', import.meta.url), 'utf8');

  assert.match(html, /body\s*{[\s\S]*overflow:\s*hidden;[\s\S]*display:\s*flex;/);
  assert.match(html, /main\s*{[\s\S]*grid-template-rows:\s*auto auto minmax\(0,\s*1fr\) auto;/);
  assert.match(html, /\.table-wrap\s*{[\s\S]*height:\s*100%;[\s\S]*overflow:\s*auto;/);
});

test('app exposes sortable allocation table headers', async () => {
  const html = await readFile(new URL('./app.html', import.meta.url), 'utf8');

  for (const key of ['source', 'answered_participants', 'visible_questions', 'mcq_questions', 'frq_questions', 'current', 'points', 'priority', 'cap_group', 'cap_points', 'gate_slug', 'late_percent', 'file']) {
    assert.match(html, new RegExp(`data-sort-key="${key}"`));
  }
  assert.match(html, /function sortedSources\(sources\)/);
  assert.match(html, /aria-sort/);
});

test('app exposes participant response counts scoped to ids 8-87', async () => {
  const html = await readFile(new URL('./app.html', import.meta.url), 'utf8');

  assert.match(html, /Answered \(8-87\)/);
  assert.match(html, /participantResponseCell\(source\)/);
  assert.match(html, /participant_response_count/);
});

test('app can use localhost API when opened as a file', async () => {
  const html = await readFile(new URL('./app.html', import.meta.url), 'utf8');

  assert.match(html, /location\.protocol === 'file:'/);
  assert.match(html, /http:\/\/localhost:4177/);
});

test('app exposes policy controls and survey inspection affordances', async () => {
  const html = await readFile(new URL('./app.html', import.meta.url), 'utf8');

  assert.match(html, /Priority/);
  assert.match(html, /Cap group/);
  assert.match(html, /Gate survey/);
  assert.match(html, /Late %/);
  assert.match(html, /inspect-modal/);
  assert.match(html, /Open in app/);
});

test('app renders manual sources with pending current point labels', async () => {
  const html = await readFile(new URL('./app.html', import.meta.url), 'utf8');

  assert.match(html, /currentPointLabel\(source\)/);
  assert.match(html, /current_points_label/);
});
