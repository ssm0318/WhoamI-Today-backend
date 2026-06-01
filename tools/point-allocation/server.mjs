import { createServer } from 'node:http';
import { execFile } from 'node:child_process';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { access, mkdir, readdir, readFile, stat, writeFile } from 'node:fs/promises';
import { promisify } from 'node:util';

const TOOL_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_REPO_ROOT = resolve(TOOL_DIR, '../..');
const DEFAULT_OUTPUT_PATH = join(DEFAULT_REPO_ROOT, 'point-allocation.values.json');
const PORT = Number(process.env.PORT || 4177);
const APP_BASE_URL = process.env.APP_BASE_URL || 'http://localhost:3000';
const PREVIEW_POINTS_PER_DOLLAR = Number(process.env.POINT_ALLOCATION_POINTS_PER_DOLLAR || 10);
const DEFAULT_ANALYSIS_DB_NAME = 'whoamitoday_merged';
const REIMBURSEMENT_PREVIEW_CACHE_TTL_MS = Number(
  process.env.POINT_ALLOCATION_PREVIEW_CACHE_TTL_MS || 60_000,
);
const execFileAsync = promisify(execFile);
const reimbursementPreviewCache = new Map();

const INPUT_LESS_TYPES = new Set(['display_only']);
const MCQ_TYPES = new Set(['single_choice', 'multi_choice', 'per_friend_single_choice']);
const FRQ_TYPES = new Set(['free_text']);
const PER_FRIEND_TYPES = new Set(['per_friend_likert_5', 'per_friend_single_choice']);

const POLICY_DEFAULTS = {
  priority_rating: 0,
  cap_group: '',
  cap_points: null,
  gate_slug: '',
  late_percent: 100,
};

const REIMBURSEMENT_ACTION_POLICIES = {
  wit_bot_audit_phase_1: {
    actionUrl: '/users/7/chat',
    deadline: '2026-05-17',
  },
  interview_signup: {
    actionUrl: 'https://calendly.com/jaewonkim/60min',
    deadline: '2026-06-30',
  },
  friend_invite: {
    actionUrl: '/friends/explore',
    deadline: '2026-05-24',
  },
};

const GROUP_DEADLINE_OVERRIDES = {
  feature_eval_w: {
    group_q_first: '2026-05-24',
    group_w_first: '2026-06-30',
  },
};

const LATE_CREDIT_SURVEY_SLUGS = new Set(['study_endpoint_part2']);

const MANUAL_SOURCES = [
  {
    slug: 'wit_bot_audit_phase_1',
    title_en: 'Wit_bot audit pass - Phase 1',
    constant: 'WIT_BOT_AUDIT_PHASE_1_MAX_POINTS',
  },
  {
    slug: 'wit_bot_audit_phase_2',
    title_en: 'Wit_bot audit pass - Phase 2',
    constant: 'WIT_BOT_AUDIT_PHASE_2_MAX_POINTS',
  },
  {
    slug: 'app_usage_phase_1',
    title_en: 'App usage - Phase 1',
    constant: 'APP_USAGE_PHASE_1_FULL_POINTS',
  },
  {
    slug: 'app_usage_phase_2',
    title_en: 'App usage - Phase 2',
    constant: 'APP_USAGE_PHASE_2_FULL_POINTS',
  },
  {
    slug: 'interview_signup',
    title_en: 'Interview',
    constant: 'INTERVIEW_SIGNUP_MAX_POINTS',
    priority_rating: 2,
  },
  {
    slug: 'friend_invite',
    title_en: 'Friend invite reimbursement',
    description_en:
      '100 pts per invited friend, capped at 5 friends / 500 pts. Verification is pending account_user.invited_from_id.',
    constant: 'FRIEND_INVITE_MAX_POINTS',
    defaultPointValue: 500,
    current_points_label: 'To be updated',
    file: 'account_user.invited_from_id (pending)',
  },
];

const CATEGORY_LABELS = {
  daily: 'Daily diary',
  sotd: 'Survey of the Day',
  pre: 'Phase / feature surveys',
  endpoint: 'Endpoint',
  weekly_anytime: 'Weekly / anytime',
  closeness_reeval: 'Closeness re-eval',
  habit_platform: 'Prerequisites',
  manual: 'Manual activities',
};

function stripQuotes(value) {
  const trimmed = String(value ?? '').trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function parsePointValue(value) {
  const parsed = Number.parseInt(stripQuotes(value), 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

function parseInteger(value, fallback = 0) {
  const parsed = Number.parseInt(stripQuotes(value), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseOptionalInteger(value) {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number.parseInt(stripQuotes(value), 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function parseBoolean(value) {
  return ['true', 'yes', '1'].includes(stripQuotes(value).toLowerCase());
}

function clampInteger(value, { min = 0, max = Number.MAX_SAFE_INTEGER, fallback = 0 } = {}) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function normalizePolicy(source = {}) {
  return {
    priority_rating: clampInteger(source.priority_rating, { min: 0, max: 5, fallback: 0 }),
    cap_group: stripQuotes(source.cap_group || ''),
    cap_points: parseOptionalInteger(source.cap_points),
    gate_slug: stripQuotes(source.gate_slug || ''),
    late_percent: clampInteger(source.late_percent, { min: 0, max: 100, fallback: 100 }),
  };
}

function withPolicyDefaults(source) {
  return {
    ...POLICY_DEFAULTS,
    ...source,
  };
}

function range(min, max) {
  return { min, max };
}

function emptyQuestionMetrics({ source = 'authored', exact = true, userCount = null } = {}) {
  return {
    authored_total: 0,
    authored_mcq: 0,
    authored_frq: 0,
    per_friend_total: 0,
    per_friend_mcq: 0,
    per_friend_frq: 0,
    visible_total_range: range(0, 0),
    visible_mcq_range: range(0, 0),
    visible_frq_range: range(0, 0),
    depends_on_user: false,
    exact_range: exact,
    range_source: source,
    range_user_count: userCount,
  };
}

function authoredQuestionMetrics(questions = [], dbMetrics = null) {
  const metrics = emptyQuestionMetrics({
    source: dbMetrics ? 'database' : 'authored',
    exact: Boolean(dbMetrics),
    userCount: dbMetrics?.user_count ?? null,
  });

  for (const question of questions) {
    if (INPUT_LESS_TYPES.has(question.type)) continue;
    metrics.authored_total += 1;
    if (MCQ_TYPES.has(question.type)) metrics.authored_mcq += 1;
    if (FRQ_TYPES.has(question.type)) metrics.authored_frq += 1;
    if (PER_FRIEND_TYPES.has(question.type)) {
      metrics.per_friend_total += 1;
      if (MCQ_TYPES.has(question.type)) metrics.per_friend_mcq += 1;
      if (FRQ_TYPES.has(question.type)) metrics.per_friend_frq += 1;
    }
  }

  metrics.depends_on_user = metrics.per_friend_total > 0;
  metrics.visible_total_range = range(metrics.authored_total, metrics.authored_total);
  metrics.visible_mcq_range = range(metrics.authored_mcq, metrics.authored_mcq);
  metrics.visible_frq_range = range(metrics.authored_frq, metrics.authored_frq);

  if (dbMetrics) {
    metrics.visible_total_range = dbMetrics.visible_total_range;
    metrics.visible_mcq_range = dbMetrics.visible_mcq_range;
    metrics.visible_frq_range = dbMetrics.visible_frq_range;
    metrics.depends_on_user =
      metrics.depends_on_user ||
      metrics.visible_total_range.min !== metrics.visible_total_range.max ||
      metrics.visible_mcq_range.min !== metrics.visible_mcq_range.max ||
      metrics.visible_frq_range.min !== metrics.visible_frq_range.max;
  }

  return metrics;
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, "'\\''")}'`;
}

function remoteCdCommand(remoteDir) {
  if (remoteDir.startsWith('~') || remoteDir.startsWith('$')) {
    return `cd ${remoteDir}`;
  }
  return `cd ${shellQuote(remoteDir)}`;
}

function buildRemoteParticipantCountsSql() {
  return [
    'SELECT s.slug, COUNT(DISTINCT r.user_id)',
    'FROM surveys_surveyresponse r',
    'JOIN surveys_survey s ON s.id = r.survey_id',
    'WHERE r.user_id BETWEEN 8 AND 87',
    'GROUP BY s.slug',
    'ORDER BY s.slug;',
  ].join(' ');
}

function parseParticipantCountRows(stdout) {
  const counts = new Map();
  for (const line of stdout.trim().split(/\r?\n/)) {
    if (!line.trim()) continue;
    const [slug, rawCount] = line.split('|');
    const count = Number.parseInt(rawCount, 10);
    if (slug && Number.isFinite(count)) {
      counts.set(slug, count);
    }
  }
  return counts;
}

function shouldReadRemoteParticipantCounts(repoRoot) {
  if (process.env.POINT_ALLOCATION_REMOTE_COUNTS === '0') return false;
  if (process.env.POINT_ALLOCATION_REMOTE_COUNTS === '1') return true;
  return Boolean(process.env.POINT_ALLOCATION_REMOTE_SSH);
}

async function readRemoteParticipantResponseCounts(repoRoot) {
  if (!shouldReadRemoteParticipantCounts(repoRoot)) {
    return { attempted: false, available: false, counts: new Map() };
  }

  const sshCommand = process.env.POINT_ALLOCATION_SSH_COMMAND || 'ssh';
  const sshTarget = process.env.POINT_ALLOCATION_REMOTE_SSH || 'whoami';
  const remoteDir = process.env.POINT_ALLOCATION_REMOTE_DIR || '$HOME/WhoamI-Today-backend';
  const sql = buildRemoteParticipantCountsSql();
  const remoteCommand = [
    remoteCdCommand(remoteDir),
    `docker compose -f docker-compose.production.yml exec -T db psql -U postgres -d whoamitoday -At -c ${shellQuote(sql)}`,
  ].join(' && ');

  try {
    const { stdout } = await execFileAsync(
      sshCommand,
      ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', sshTarget, remoteCommand],
      {
        timeout: 15000,
        maxBuffer: 1024 * 1024,
      },
    );
    return { attempted: true, available: true, counts: parseParticipantCountRows(stdout) };
  } catch {
    return { attempted: true, available: false, counts: new Map() };
  }
}

function buildDbMetricsScript() {
  return String.raw`
import json
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', os.environ.get('DJANGO_SETTINGS_MODULE', 'adoorback.settings.development'))

import django
django.setup()

from django.contrib.auth import get_user_model

from surveys.models import (
    DISPLAY_ONLY,
    FREE_TEXT,
    MULTI_CHOICE,
    PER_FRIEND_SINGLE_CHOICE,
    PER_FRIEND_TYPES,
    SINGLE_CHOICE,
    ScheduledSurvey,
    Survey,
    SurveyResponse,
)
from surveys.friend_scope import eligible_friends_for_survey
from surveys.recovery import missing_recovery_question_ids_for_user
from surveys.scheduling import schedule_routes_to_user

INPUT_LESS_TYPES = {DISPLAY_ONLY}
MCQ_TYPES = {SINGLE_CHOICE, MULTI_CHOICE, PER_FRIEND_SINGLE_CHOICE}
FRQ_TYPES = {FREE_TEXT}


def metric_range(values):
    if not values:
        return {'min': 0, 'max': 0}
    return {'min': min(values), 'max': max(values)}


def routed_users_for_survey(survey, users):
    scheduled_rows = list(
        ScheduledSurvey.objects
        .filter(survey=survey)
        .select_related('survey')
    )
    if not scheduled_rows:
        return users
    return [
        user for user in users
        if any(schedule_routes_to_user(row, user) for row in scheduled_rows)
    ]


User = get_user_model()
users = list(User.objects.filter(is_active=True, is_staff=False).order_by('id'))
payload = {}

for survey in Survey.objects.prefetch_related('questions').all():
    questions = list(survey.questions.all())
    if not questions:
        continue

    totals = []
    mcqs = []
    frqs = []
    routed_users = routed_users_for_survey(survey, users)

    for user in routed_users:
        visible_question_ids = missing_recovery_question_ids_for_user(user, survey)
        visible_questions = [
            question for question in questions
            if question.type not in INPUT_LESS_TYPES
            and (visible_question_ids is None or question.id in visible_question_ids)
        ]
        friend_count = (
            len(eligible_friends_for_survey(user, survey))
            if any(question.type in PER_FRIEND_TYPES for question in visible_questions)
            else 0
        )
        total = 0
        mcq = 0
        frq = 0
        for question in visible_questions:
            multiplier = friend_count if question.type in PER_FRIEND_TYPES else 1
            total += multiplier
            if question.type in MCQ_TYPES:
                mcq += multiplier
            if question.type in FRQ_TYPES:
                frq += multiplier
        totals.append(total)
        mcqs.append(mcq)
        frqs.append(frq)

    participant_response_count = (
        SurveyResponse.objects
        .filter(survey=survey, user_id__gte=8, user_id__lte=87)
        .values('user_id')
        .distinct()
        .count()
    )

    payload[survey.slug] = {
        'visible_total_range': metric_range(totals),
        'visible_mcq_range': metric_range(mcqs),
        'visible_frq_range': metric_range(frqs),
        'user_count': len(routed_users),
        'participant_response_count': participant_response_count,
    }

print(json.dumps(payload))
`;
}

async function readDbQuestionMetrics(repoRoot) {
  const djangoRoot = join(repoRoot, 'adoorback');
  try {
    await access(join(djangoRoot, 'manage.py'));
  } catch {
    return new Map();
  }

  try {
    const { stdout } = await execFileAsync(
      process.env.POINT_ALLOCATION_PYTHON || 'python',
      ['-c', buildDbMetricsScript()],
      {
        cwd: djangoRoot,
        env: {
          ...process.env,
          DB_HOST: process.env.DB_HOST || 'localhost',
          DB_NAME:
            process.env.DB_NAME ||
            process.env.POINT_ALLOCATION_DB_NAME ||
            DEFAULT_ANALYSIS_DB_NAME,
          DJANGO_SETTINGS_MODULE: process.env.DJANGO_SETTINGS_MODULE || 'adoorback.settings.development',
        },
        timeout: 20000,
        maxBuffer: 1024 * 1024 * 4,
      },
    );
    const parsed = JSON.parse(stdout.trim());
    return new Map(Object.entries(parsed));
  } catch {
    return new Map();
  }
}

function categoryFromFile(fileName) {
  return fileName.replace(/\.ya?ml$/, '');
}

function setLocalizedValue(target, field, rawValue) {
  const value = stripQuotes(rawValue);
  if (field === 'title') {
    target.title_en = value;
  } else if (field === 'description') {
    target.description_en = value;
  } else {
    target[`${field}_en`] = value;
  }
}

function parseSurveyYaml(text, fileName) {
  const category = categoryFromFile(fileName);
  const rows = [];
  let current = null;

  const pushCurrent = () => {
    if (!current?.slug) return;
    rows.push({
      kind: 'survey',
      id: `survey:${current.slug}`,
      slug: current.slug,
      title_en: current.title_en || current.slug,
      description_en: current.description_en || '',
      category,
      category_label: CATEGORY_LABELS[category] || category,
      point_value: current.point_value ?? 0,
      point_prereq_slug: current.point_prereq_slug || '',
      priority: current.priority ?? 0,
      repeatable: Boolean(current.repeatable),
      editable: Boolean(current.editable),
      question_count: current.questions.length,
      questions: current.questions,
      app_url: `${APP_BASE_URL}/surveys/${encodeURIComponent(current.slug)}/answer`,
      file: `adoorback/surveys/fixtures/${fileName}`,
    });
  };

  for (const line of text.split(/\r?\n/)) {
    const slugMatch = line.match(/^- slug:\s*(.+)$/);
    if (slugMatch) {
      pushCurrent();
      current = {
        slug: stripQuotes(slugMatch[1]),
        title_en: '',
        description_en: '',
        point_value: 0,
        point_prereq_slug: '',
        priority: 0,
        repeatable: false,
        editable: false,
        questions: [],
        inQuestions: false,
        questionIndent: null,
        question: null,
        questionSection: '',
        option: null,
        optionIndent: null,
      };
      continue;
    }
    if (!current) continue;

    if (current.inQuestions) {
      const listItemMatch = line.match(/^(\s*)-\s+([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$/);
      if (
        listItemMatch &&
        listItemMatch[2] === 'order' &&
        (current.questionIndent === null || listItemMatch[1].length === current.questionIndent)
      ) {
        current.questionIndent = listItemMatch[1].length;
        const question = {
          order: parseInteger(listItemMatch[3], current.questions.length + 1),
          slug: '',
          type: '',
          prompt_en: '',
          required: true,
          options: [],
        };
        current.questions.push(question);
        current.question = question;
        current.questionSection = '';
        current.option = null;
        current.optionIndent = null;
        continue;
      }

      if (
        listItemMatch &&
        current.question &&
        current.questionIndent !== null &&
        listItemMatch[1].length > current.questionIndent &&
        (current.questionSection === 'options' || current.option)
      ) {
        current.optionIndent = listItemMatch[1].length;
        current.option = { order: null, value: '', label_en: '' };
        if (listItemMatch[2] === 'order') {
          current.option.order = parseInteger(listItemMatch[3], current.question.options.length + 1);
        } else if (listItemMatch[2] === 'value') {
          current.option.value = stripQuotes(listItemMatch[3]);
        }
        current.question.options.push(current.option);
        continue;
      }

      const fieldWithIndentMatch = line.match(/^(\s*)([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$/);
      const fieldIndent = fieldWithIndentMatch ? fieldWithIndentMatch[1].length : null;
      if (
        fieldWithIndentMatch &&
        current.questionIndent !== null &&
        fieldIndent <= current.questionIndent
      ) {
        current.inQuestions = false;
        current.questionIndent = null;
        current.question = null;
        current.questionSection = '';
        current.option = null;
        current.optionIndent = null;
      } else if (current.question) {
        if (fieldWithIndentMatch && current.option && fieldIndent === current.optionIndent + 2) {
          const [, , field, rawValue] = fieldWithIndentMatch;
          if (field === 'order') {
            current.option.order = parseInteger(rawValue, current.question.options.length);
          } else if (field === 'value') {
            current.option.value = stripQuotes(rawValue);
          } else if (field === 'label') {
            current.questionSection = 'option_label';
          }
          continue;
        }

        if (
          fieldWithIndentMatch &&
          current.questionSection &&
          current.questionSection !== 'options' &&
          fieldWithIndentMatch[2] === 'en' &&
          fieldIndent === current.questionIndent + 4
        ) {
          setLocalizedValue(current.question, current.questionSection, fieldWithIndentMatch[3]);
          continue;
        }

        if (
          fieldWithIndentMatch &&
          current.option &&
          current.questionSection === 'option_label' &&
          fieldWithIndentMatch[2] === 'en' &&
          fieldIndent === current.optionIndent + 4
        ) {
          current.option.label_en = stripQuotes(fieldWithIndentMatch[3]);
          continue;
        }

        if (fieldWithIndentMatch && fieldIndent === current.questionIndent + 2) {
          const [, , field, rawValue] = fieldWithIndentMatch;
          current.option = null;
          current.optionIndent = null;
          if (['prompt', 'content', 'low_label', 'high_label', 'placeholder', 'na_option'].includes(field)) {
            current.questionSection = field;
          } else if (field === 'slug' || field === 'type') {
            current.question[field] = stripQuotes(rawValue);
            current.questionSection = '';
          } else if (field === 'required') {
            current.question.required = parseBoolean(rawValue);
            current.questionSection = '';
          } else if (field === 'options') {
            current.questionSection = 'options';
          } else {
            current.question[field] = stripQuotes(rawValue);
            current.questionSection = '';
          }
          continue;
        }
        continue;
      }
    }

    if (/^  (title|description):\s*$/.test(line)) {
      current.section = line.trim().replace(':', '');
      continue;
    }
    if (/^  [A-Za-z_][A-Za-z0-9_]*:\s*/.test(line)) {
      current.section = '';
    }
    const nestedTitleMatch = line.match(/^    en:\s*(.+)$/);
    if (['title', 'description'].includes(current.section) && nestedTitleMatch) {
      setLocalizedValue(current, current.section, nestedTitleMatch[1]);
      continue;
    }

    const fieldMatch = line.match(
      /^  (title_en|description_en|point_value|point_prereq_slug|priority|repeatable|editable|questions):\s*(.*)$/,
    );
    if (!fieldMatch) continue;
    const [, field, rawValue] = fieldMatch;
    if (field === 'point_value') {
      current.point_value = parsePointValue(rawValue);
    } else if (field === 'priority') {
      current.priority = parseInteger(rawValue, 0);
    } else if (field === 'repeatable' || field === 'editable') {
      current[field] = parseBoolean(rawValue);
    } else if (field === 'questions') {
      current.inQuestions = true;
      current.questionIndent = null;
    } else {
      current[field] = stripQuotes(rawValue);
    }
    current.section = '';
  }
  pushCurrent();
  return rows;
}

async function readManualSources(repoRoot) {
  const configPath = join(repoRoot, 'adoorback', 'surveys', 'reimbursement_config.py');
  let config = '';
  try {
    config = await readFile(configPath, 'utf8');
  } catch {
    config = '';
  }
  return MANUAL_SOURCES.map((source) => {
    const match = source.constant
      ? config.match(new RegExp(`${source.constant}\\s*=\\s*(\\d+)`))
      : null;
    const pointValue = match
      ? Number.parseInt(match[1], 10)
      : source.defaultPointValue ?? 0;
    return {
      kind: 'manual',
      id: `manual:${source.slug}`,
      slug: source.slug,
      title_en: source.title_en,
      description_en: source.description_en || '',
      category: 'manual',
      category_label: CATEGORY_LABELS.manual,
      point_value: pointValue,
      current_points_label: source.current_points_label || '',
      point_prereq_slug: '',
      priority_rating: source.priority_rating ?? 0,
      priority: 0,
      repeatable: false,
      editable: false,
      question_count: 0,
      question_metrics: emptyQuestionMetrics(),
      participant_response_count: null,
      participant_response_label: '-',
      questions: [],
      app_url: '',
      file: source.file || 'adoorback/surveys/reimbursement_config.py',
    };
  });
}

export async function readPointSources(repoRoot = DEFAULT_REPO_ROOT) {
  const fixturesDir = join(repoRoot, 'adoorback', 'surveys', 'fixtures');
  const files = (await readdir(fixturesDir))
    .filter((file) => file.endsWith('.yaml') || file.endsWith('.yml'))
    .sort();

  const surveys = [];
  for (const file of files) {
    const text = await readFile(join(fixturesDir, file), 'utf8');
    surveys.push(...parseSurveyYaml(text, file));
  }

  const dbQuestionMetrics = await readDbQuestionMetrics(repoRoot);
  const remoteParticipantCounts = await readRemoteParticipantResponseCounts(repoRoot);
  const surveysWithMetrics = surveys.map((source) => {
    const dbMetrics = dbQuestionMetrics.get(source.slug);
    const localParticipantResponseCount = dbMetrics?.participant_response_count;
    let participantResponseCount = localParticipantResponseCount;
    let participantResponseSource = 'local';
    if (remoteParticipantCounts.available) {
      participantResponseCount = remoteParticipantCounts.counts.get(source.slug) ?? 0;
      participantResponseSource = 'remote';
    } else if (remoteParticipantCounts.attempted) {
      participantResponseCount = null;
      participantResponseSource = 'remote_unavailable';
    }
    return {
      ...source,
      question_metrics: authoredQuestionMetrics(source.questions, dbMetrics),
      participant_response_count: Number.isFinite(participantResponseCount) ? participantResponseCount : null,
      participant_response_label: Number.isFinite(participantResponseCount)
        ? String(participantResponseCount)
        : 'Remote unavailable',
      participant_response_source: participantResponseSource,
    };
  });
  const manual = await readManualSources(repoRoot);
  return [...surveysWithMetrics, ...manual];
}

export async function readAllocationFile(outputPath = DEFAULT_OUTPUT_PATH) {
  try {
    const parsed = JSON.parse(await readFile(outputPath, 'utf8'));
    if (!Array.isArray(parsed.sources)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export async function writeAllocationFile(outputPath = DEFAULT_OUTPUT_PATH, sources) {
  if (!Array.isArray(sources)) {
    throw new Error('Expected sources to be an array');
  }

  const normalized = sources.map((source) => {
    const points = Number.parseInt(source.points, 10);
    if (!['survey', 'manual'].includes(source.kind)) {
      throw new Error(`Invalid source kind: ${source.kind}`);
    }
    if (!source.slug) {
      throw new Error('Every source needs a slug');
    }
    if (!Number.isFinite(points) || points < 0) {
      throw new Error(`Invalid points for ${source.slug}`);
    }
    return {
      kind: source.kind,
      slug: source.slug,
      points,
      ...normalizePolicy(source),
    };
  });

  const payload = {
    version: 1,
    saved_at: new Date().toISOString(),
    sources: normalized,
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  return payload;
}

function withSavedPoints(sources, allocation) {
  const saved = new Map(
    (allocation?.sources || []).map((source) => [`${source.kind}:${source.slug}`, source]),
  );
  return sources.map((source) => {
    const savedSource = saved.get(source.id);
    const policy = normalizePolicy(savedSource || source);
    return withPolicyDefaults({
      ...source,
      ...policy,
      draft_points: savedSource ? savedSource.points : source.point_value,
      draft_priority_rating: policy.priority_rating,
      draft_cap_group: policy.cap_group,
      draft_cap_points: policy.cap_points,
      draft_gate_slug: policy.gate_slug,
      draft_late_percent: policy.late_percent,
    });
  });
}

function analysisDbConfig() {
  return {
    host: process.env.POINT_ALLOCATION_DB_HOST || process.env.DB_HOST || 'localhost',
    port: process.env.POINT_ALLOCATION_DB_PORT || process.env.DB_PORT || '5432',
    user: process.env.POINT_ALLOCATION_DB_USER || process.env.DB_USER || 'postgres',
    name: process.env.POINT_ALLOCATION_DB_NAME || process.env.DB_NAME || DEFAULT_ANALYSIS_DB_NAME,
    password: process.env.POINT_ALLOCATION_DB_PASSWORD || process.env.DB_PASSWORD || '',
  };
}

async function runAnalysisPsql(sql, config = analysisDbConfig()) {
  const env = { ...process.env };
  if (config.password) env.PGPASSWORD = config.password;

  const { stdout } = await execFileAsync(
    process.env.POINT_ALLOCATION_PSQL || 'psql',
    [
      '-h',
      config.host,
      '-p',
      String(config.port),
      '-U',
      config.user,
      '-d',
      config.name,
      '-At',
      '-F',
      '\t',
      '-c',
      sql,
    ],
    {
      env,
      timeout: 15000,
      maxBuffer: 1024 * 1024 * 4,
    },
  );

  return stdout
    .trim()
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => line.split('\t'));
}

async function readMergedDbParticipants(config = analysisDbConfig()) {
  const rows = await runAnalysisPsql(
    [
      "SELECT id, COALESCE(NULLIF(username, ''), 'user_' || id::text), user_group",
      'FROM account_user',
      'WHERE id BETWEEN 8 AND 87',
      'ORDER BY id;',
    ].join(' '),
    config,
  );
  return rows
    .map(([rawId, username, userGroup]) => ({
      id: Number.parseInt(rawId, 10),
      username: username || `user_${rawId}`,
      userGroup: userGroup || '',
    }))
    .filter((participant) => Number.isFinite(participant.id));
}

function addNestedCount(map, rawUserId, slug, rawCount) {
  const userId = Number.parseInt(rawUserId, 10);
  const count = Number.parseInt(rawCount, 10);
  if (!Number.isFinite(userId) || !slug || !Number.isFinite(count)) return;
  if (!map.has(userId)) map.set(userId, new Map());
  map.get(userId).set(slug, count);
}

async function readMergedDbSurveyResponseCounts(config = analysisDbConfig()) {
  const rows = await runAnalysisPsql(
    [
      'SELECT r.user_id, s.slug, COUNT(*)',
      'FROM surveys_surveyresponse r',
      'JOIN surveys_survey s ON s.id = r.survey_id',
      'WHERE r.user_id BETWEEN 8 AND 87',
      'GROUP BY r.user_id, s.slug',
      'ORDER BY r.user_id, s.slug;',
    ].join(' '),
    config,
  );
  const counts = new Map();
  rows.forEach(([userId, slug, count]) => addNestedCount(counts, userId, slug, count));
  return counts;
}

async function readMergedDbPointAwardCounts(config = analysisDbConfig()) {
  try {
    const rows = await runAnalysisPsql(
      [
        'SELECT user_id, source_slug, COUNT(*)',
        'FROM surveys_pointaward',
        'WHERE user_id BETWEEN 8 AND 87',
        "AND source_kind <> 'survey'",
        'GROUP BY user_id, source_slug',
        'ORDER BY user_id, source_slug;',
      ].join(' '),
      config,
    );
    const counts = new Map();
    rows.forEach(([userId, slug, count]) => addNestedCount(counts, userId, slug, count));
    return counts;
  } catch {
    return new Map();
  }
}

async function readMergedDbSourceRoutings(config = analysisDbConfig()) {
  const rows = await runAnalysisPsql(
    [
      'SELECT s.slug, ss.target_user_group',
      'FROM surveys_scheduledsurvey ss',
      'JOIN surveys_survey s ON s.id = ss.survey_id',
      "WHERE ss.target_user_group <> ''",
      'GROUP BY s.slug, ss.target_user_group',
      'ORDER BY s.slug, ss.target_user_group;',
    ].join(' '),
    config,
  );
  const routings = new Map();
  for (const [slug, targetUserGroup] of rows) {
    if (!slug || !targetUserGroup) continue;
    if (!routings.has(slug)) routings.set(slug, new Set());
    routings.get(slug).add(targetUserGroup);
  }
  return routings;
}

async function readMergedDbSourceSchedules(config = analysisDbConfig()) {
  const rows = await runAnalysisPsql(
    [
      'SELECT s.slug, ss.target_user_group, ss.window_start, COALESCE(ss.window_end, ss.window_start), ss.allow_late',
      'FROM surveys_scheduledsurvey ss',
      'JOIN surveys_survey s ON s.id = ss.survey_id',
      'ORDER BY s.slug, ss.window_start;',
    ].join(' '),
    config,
  );
  const schedules = new Map();
  for (const [slug, targetUserGroup, windowStart, windowEnd, allowLate] of rows) {
    if (!slug) continue;
    if (!schedules.has(slug)) schedules.set(slug, []);
    schedules.get(slug).push({
      targetUserGroup: targetUserGroup || '',
      windowStart,
      windowEnd,
      allowLate: allowLate === 't' || allowLate === 'true',
    });
  }
  return schedules;
}

function configuredPoints(source) {
  return Math.max(0, parseInteger(source.draft_points ?? source.point_value, 0));
}

function configuredCapGroup(source) {
  return stripQuotes(source.draft_cap_group ?? source.cap_group ?? '');
}

function configuredCapPoints(source) {
  return parseOptionalInteger(source.draft_cap_points ?? source.cap_points);
}

function configuredGateSlug(source) {
  return stripQuotes(source.draft_gate_slug ?? source.gate_slug ?? '');
}

function configuredLatePercent(source) {
  return clampInteger(source.draft_late_percent ?? source.late_percent, {
    min: 0,
    max: 100,
    fallback: 100,
  });
}

function configuredPriorityRating(source) {
  return clampInteger(source.draft_priority_rating ?? source.priority_rating, {
    min: 0,
    max: 5,
    fallback: 0,
  });
}

function countParticipantWork(countMap = new Map()) {
  let total = 0;
  for (const count of countMap.values()) total += count;
  return total;
}

function selectedParticipant({ participants, responseCounts, pointAwardCounts, requestedUserId }) {
  if (participants.length === 0) return { id: null, username: 'No participant responses' };

  const requested = Number.parseInt(requestedUserId, 10);
  if (Number.isFinite(requested)) {
    const match = participants.find((participant) => participant.id === requested);
    if (match) return match;
  }

  return [...participants].sort((a, b) => {
    const bTotal =
      countParticipantWork(responseCounts.get(b.id)) + countParticipantWork(pointAwardCounts.get(b.id));
    const aTotal =
      countParticipantWork(responseCounts.get(a.id)) + countParticipantWork(pointAwardCounts.get(a.id));
    return bTotal - aTotal || a.id - b.id;
  })[0];
}

function sourceRoutesToParticipant(source, participant, sourceRoutings = new Map()) {
  if (source.kind === 'manual') return true;

  const userGroup = participant?.userGroup || participant?.user_group || '';
  const targetGroups = sourceRoutings.get(source.slug);
  if (targetGroups?.size) return targetGroups.has(userGroup);
  if (source.slug.endsWith('_w')) return userGroup === 'group_w_first';
  if (source.slug.endsWith('_q')) return userGroup === 'group_q_first';
  return true;
}

function manualActionUrl(slug) {
  if (REIMBURSEMENT_ACTION_POLICIES[slug]?.actionUrl) {
    return REIMBURSEMENT_ACTION_POLICIES[slug].actionUrl;
  }
  if (slug.startsWith('wit_bot_audit')) return '/users/7/chat';
  if (slug === 'friend_invite') return '/friends/explore';
  return '';
}

function actionUrlForSource(source) {
  return source.app_url || manualActionUrl(source.slug);
}

function scheduleRoutesToParticipant(schedule, source, participant) {
  const target = schedule.targetUserGroup || '';
  if (target) {
    const userGroup = participant?.userGroup || participant?.user_group || '';
    return userGroup === target;
  }
  return sourceRoutesToParticipant(source, participant);
}

function isScheduleAnswerable(schedule, currentDate) {
  const today = String(currentDate);
  if (schedule.windowStart && schedule.windowStart > today) return false;
  if (schedule.allowLate) return true;
  if (!schedule.windowEnd) return true;
  return schedule.windowEnd >= today;
}

function isScheduleOpenNow(schedule, currentDate) {
  const today = String(currentDate);
  if (schedule.windowStart && schedule.windowStart > today) return false;
  if (!schedule.windowEnd) return true;
  return schedule.windowEnd >= today;
}

function isScheduleLateAccepted(schedule, currentDate) {
  const today = String(currentDate);
  return Boolean(
    schedule.allowLate &&
      schedule.windowStart &&
      schedule.windowStart <= today &&
      schedule.windowEnd &&
      schedule.windowEnd < today,
  );
}

function sourceAvailability({ source, participant, sourceSchedules, currentDate }) {
  const appUrl = actionUrlForSource(source);
  if (!appUrl) return 'no_action';
  const userGroup = participant?.userGroup || participant?.user_group || '';
  const schedules = sourceSchedules.get(source.slug) || [];
  const routed = schedules.filter((schedule) =>
    scheduleRoutesToParticipant(schedule, source, participant),
  );

  const groupDeadline = GROUP_DEADLINE_OVERRIDES[source.slug]?.[userGroup];
  if (groupDeadline) {
    if (String(currentDate) <= groupDeadline) return 'available';
    if (routed.some((schedule) => schedule.allowLate)) return 'late';
    return 'deadline';
  }

  if (LATE_CREDIT_SURVEY_SLUGS.has(source.slug) && schedules.length > 0) {
    if (routed.some((schedule) => isScheduleOpenNow(schedule, currentDate))) {
      return 'available';
    }
    if (routed.some((schedule) => schedule.windowStart && schedule.windowStart > currentDate)) {
      return 'future';
    }
    if (routed.some((schedule) => schedule.windowStart && schedule.windowStart <= currentDate)) {
      return 'late';
    }
  }

  const actionPolicy = REIMBURSEMENT_ACTION_POLICIES[source.slug];
  if (actionPolicy?.availableFrom && String(currentDate) < actionPolicy.availableFrom) {
    return 'future';
  }
  if (actionPolicy?.deadline) {
    return String(currentDate) <= actionPolicy.deadline ? 'available' : 'deadline';
  }

  if (source.kind === 'manual') return 'available';

  if (schedules.length === 0) return 'available';

  if (routed.some((schedule) => isScheduleOpenNow(schedule, currentDate))) {
    return 'available';
  }
  if (routed.some((schedule) => isScheduleLateAccepted(schedule, currentDate))) return 'late';
  if (routed.some((schedule) => schedule.windowStart && schedule.windowStart > currentDate)) {
    return 'future';
  }
  return 'deadline';
}

function currentPossiblePointsFor({ possiblePoints, latePercent, availability }) {
  if (availability !== 'late') return possiblePoints;
  return Math.max(0, Math.round((possiblePoints * latePercent) / 100));
}

function availableMaxForRows(rows) {
  let uncappedTotal = 0;
  const capGroups = new Map();

  for (const row of rows) {
    if (!row.capGroup) {
      uncappedTotal += row.possiblePoints;
      continue;
    }
    const current = capGroups.get(row.capGroup) || { sum: 0, capPoints: null, sourceCount: 0 };
    current.sum += row.possiblePoints;
    current.sourceCount += 1;
    if (row.capPoints !== null) current.capPoints = Math.max(current.capPoints || 0, row.capPoints);
    capGroups.set(row.capGroup, current);
  }

  return {
    capRules: Array.from(capGroups.entries()).map(([group, value]) => ({
      group,
      capPoints: value.capPoints,
      sourceCount: value.sourceCount,
      availablePoints: value.capPoints ?? value.sum,
      earnedPoints: 0,
    })),
    total:
      uncappedTotal +
      Array.from(capGroups.values()).reduce(
        (sum, value) => sum + (value.capPoints ?? value.sum),
        0,
      ),
  };
}

function applyEarnedCaps(rows, capRules) {
  const capRuleMap = new Map(capRules.map((rule) => [rule.group, rule]));
  for (const rule of capRules) {
    let remaining = rule.capPoints ?? Number.POSITIVE_INFINITY;
    let earned = 0;
    for (const row of rows.filter((candidate) => candidate.capGroup === rule.group)) {
      const cappedPoints = Math.max(0, Math.min(row.rawPoints, remaining));
      row.points = cappedPoints;
      row.status = cappedPoints > 0 ? 'earned' : row.status;
      row.note =
        cappedPoints < row.rawPoints
          ? `Capped by ${rule.group} at ${rule.capPoints} pts.`
          : row.note;
      remaining -= cappedPoints;
      earned += cappedPoints;
    }
    const persistedRule = capRuleMap.get(rule.group);
    if (persistedRule) persistedRule.earnedPoints = earned;
  }
}

export function buildReimbursementPreview({
  sources,
  participants = [],
  responseCounts = new Map(),
  pointAwardCounts = new Map(),
  sourceRoutings = new Map(),
  sourceSchedules = new Map(),
  requestedUserId = null,
  dbName = DEFAULT_ANALYSIS_DB_NAME,
  pointsPerDollar = PREVIEW_POINTS_PER_DOLLAR,
  currentDate = new Date().toISOString().slice(0, 10),
}) {
  const selected = selectedParticipant({
    participants,
    responseCounts,
    pointAwardCounts,
    requestedUserId,
  });
  const selectedResponses = responseCounts.get(selected.id) || new Map();
  const selectedPointAwards = pointAwardCounts.get(selected.id) || new Map();

  const rows = sources
    .filter((source) => sourceRoutesToParticipant(source, selected, sourceRoutings))
    .map((source) => {
      const possiblePoints = configuredPoints(source);
      const capGroup = configuredCapGroup(source);
      const capPoints = configuredCapPoints(source);
      const gateSlug = configuredGateSlug(source);
      const latePercent = configuredLatePercent(source);
      const priorityRating = configuredPriorityRating(source);
      const completedCount =
        source.kind === 'manual'
          ? selectedPointAwards.get(source.slug) || 0
          : selectedResponses.get(source.slug) || 0;
      const gateMet = !gateSlug || (selectedResponses.get(gateSlug) || 0) > 0;
      const awardCount = capGroup
        ? completedCount
        : completedCount > 0
          ? 1
          : 0;
      const rawPoints = gateMet ? possiblePoints * awardCount : 0;
      const appUrl = actionUrlForSource(source);
      const availability = sourceAvailability({
        source,
        participant: selected,
        sourceSchedules,
        currentDate,
      });
      const currentPossiblePoints = currentPossiblePointsFor({
        possiblePoints,
        latePercent,
        availability,
      });
      const canEarn =
        completedCount === 0 && gateMet && ['available', 'late'].includes(availability);
      const status =
        completedCount === 0
          ? gateMet
            ? 'pending'
            : 'locked'
          : gateMet
            ? 'earned'
            : 'locked';

      return {
        key: `${source.kind}:${source.slug}`,
        kind: source.kind,
        slug: source.slug,
        title: source.title_en || source.slug,
        category: source.category_label || source.category || source.kind,
        points: capGroup ? 0 : rawPoints,
        rawPoints,
        possiblePoints,
        currentPossiblePoints,
        completedCount,
        appUrl,
        canEarn,
        availability,
        capGroup,
        capPoints,
        gateSlug,
        latePercent,
        priorityRating,
        status,
        note: gateMet
          ? completedCount === 0 && appUrl
            ? availability === 'late'
              ? `Late submissions are still accepted. Current draft credit is ${currentPossiblePoints} pts.`
              : !canEarn
                ? availability === 'future'
                  ? 'This activity is not available yet.'
                  : 'The deadline for this activity has passed.'
                : ''
            : ''
          : `Requires ${gateSlug} before this credit counts.`,
      };
    })
    .filter((row) => row.possiblePoints > 0);

  const max = availableMaxForRows(rows);
  applyEarnedCaps(rows, max.capRules);
  const earnedPoints = rows.reduce((sum, row) => sum + row.points, 0);

  return {
    db: {
      name: dbName,
      participantCount: participants.length,
    },
    selectedUser: {
      ...selected,
      responseTotal: countParticipantWork(selectedResponses),
    },
    pointsPerDollar,
    availableMax: max.total,
    earnedPoints,
    estimatedDollars: (earnedPoints / pointsPerDollar).toFixed(2),
    sourceCount: rows.length,
    rows,
    capRules: max.capRules,
    gateRules: rows.filter((row) => Boolean(row.gateSlug)),
    lateRules: rows.filter((row) => row.latePercent < 100),
  };
}

async function readReimbursementPreview(repoRoot, outputPath, requestedUserId) {
  const db = analysisDbConfig();
  const sources = await readPointSources(repoRoot);
  const allocation = await readAllocationFile(outputPath);
  const [participants, responseCounts, pointAwardCounts, sourceRoutings, sourceSchedules] =
    await Promise.all([
      readMergedDbParticipants(db),
      readMergedDbSurveyResponseCounts(db),
      readMergedDbPointAwardCounts(db),
      readMergedDbSourceRoutings(db),
      readMergedDbSourceSchedules(db),
    ]);

  return buildReimbursementPreview({
    sources: withSavedPoints(sources, allocation),
    participants,
    responseCounts,
    pointAwardCounts,
    sourceRoutings,
    sourceSchedules,
    requestedUserId,
    dbName: db.name,
  });
}

async function fileMtimeMs(path) {
  try {
    return (await stat(path)).mtimeMs;
  } catch {
    return 0;
  }
}

function normalizedRequestedUserId(requestedUserId) {
  const parsed = Number.parseInt(requestedUserId, 10);
  return Number.isFinite(parsed) ? String(parsed) : '';
}

async function reimbursementPreviewCacheKey(repoRoot, outputPath, requestedUserId) {
  const outputMtimeMs = await fileMtimeMs(outputPath);
  return JSON.stringify({
    repoRoot: resolve(repoRoot),
    outputPath: resolve(outputPath),
    outputMtimeMs,
    requestedUserId: normalizedRequestedUserId(requestedUserId),
  });
}

async function readReimbursementPreviewCached(repoRoot, outputPath, requestedUserId) {
  const key = await reimbursementPreviewCacheKey(repoRoot, outputPath, requestedUserId);
  const now = Date.now();
  const cached = reimbursementPreviewCache.get(key);
  if (cached?.preview && now - cached.createdAt <= REIMBURSEMENT_PREVIEW_CACHE_TTL_MS) {
    return cached.preview;
  }
  if (cached?.promise) return cached.promise;

  const promise = readReimbursementPreview(repoRoot, outputPath, requestedUserId).then(
    (preview) => {
      reimbursementPreviewCache.clear();
      reimbursementPreviewCache.set(key, {
        createdAt: Date.now(),
        preview,
      });
      return preview;
    },
    (error) => {
      const current = reimbursementPreviewCache.get(key);
      if (current?.promise === promise) reimbursementPreviewCache.delete(key);
      throw error;
    },
  );
  reimbursementPreviewCache.set(key, {
    createdAt: now,
    promise,
  });
  return promise;
}

async function readJsonBody(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
    'access-control-allow-headers': 'content-type',
  });
  response.end(JSON.stringify(payload, null, 2));
}

function sendJsonp(response, callback, payload) {
  const callbackName = String(callback || '');
  if (!/^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*$/.test(callbackName)) {
    sendJson(response, 400, { error: 'Invalid callback' });
    return;
  }
  response.writeHead(200, {
    'content-type': 'application/javascript; charset=utf-8',
    'cache-control': 'no-store',
  });
  response.end(`${callbackName}(${JSON.stringify(payload)});`);
}

function sendText(response, statusCode, text, contentType = 'text/plain; charset=utf-8') {
  response.writeHead(statusCode, {
    'content-type': contentType,
    'cache-control': 'no-store',
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
    'access-control-allow-headers': 'content-type',
  });
  response.end(text);
}

export function createPointAllocationServer({
  repoRoot = DEFAULT_REPO_ROOT,
  outputPath = DEFAULT_OUTPUT_PATH,
} = {}) {
  return createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://localhost');
      if (request.method === 'OPTIONS') {
        sendText(response, 204, '');
        return;
      }

      if (request.method === 'GET' && url.pathname === '/') {
        const html = await readFile(join(TOOL_DIR, 'app.html'), 'utf8');
        sendText(response, 200, html, 'text/html; charset=utf-8');
        return;
      }

      if (request.method === 'GET' && url.pathname === '/api/sources') {
        const sources = await readPointSources(repoRoot);
        const allocation = await readAllocationFile(outputPath);
        sendJson(response, 200, {
          output_path: outputPath,
          output_path_relative: relative(repoRoot, outputPath),
          saved_at: allocation?.saved_at || null,
          sources: withSavedPoints(sources, allocation),
        });
        return;
      }

      if (request.method === 'GET' && url.pathname === '/api/reimbursement-preview') {
        const preview = await readReimbursementPreviewCached(
          repoRoot,
          outputPath,
          url.searchParams.get('user_id'),
        );
        const callback = url.searchParams.get('callback');
        if (callback) {
          sendJsonp(response, callback, preview);
          return;
        }
        sendJson(response, 200, preview);
        return;
      }

      if (request.method === 'POST' && url.pathname === '/api/allocation') {
        const body = await readJsonBody(request);
        const allocation = await writeAllocationFile(outputPath, body.sources);
        reimbursementPreviewCache.clear();
        sendJson(response, 200, {
          ok: true,
          output_path: outputPath,
          saved_at: allocation.saved_at,
          count: allocation.sources.length,
        });
        return;
      }

      sendJson(response, 404, { error: 'Not found' });
    } catch (error) {
      sendJson(response, 500, { error: error.message });
    }
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const server = createPointAllocationServer();
  server.listen(PORT, () => {
    console.log(`Point allocation tool: http://localhost:${PORT}/`);
    console.log(`Saving to: ${DEFAULT_OUTPUT_PATH}`);
  });
}
