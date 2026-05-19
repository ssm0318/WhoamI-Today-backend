import { createServer } from 'node:http';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises';

const TOOL_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_REPO_ROOT = resolve(TOOL_DIR, '../..');
const DEFAULT_OUTPUT_PATH = join(DEFAULT_REPO_ROOT, 'point-allocation.values.json');
const PORT = Number(process.env.PORT || 4177);

const MANUAL_SOURCES = [
  {
    slug: 'wit_bot_audit',
    title_en: 'Wit_bot audit pass',
    constant: 'WIT_BOT_AUDIT_MAX_POINTS',
  },
  {
    slug: 'interview_signup',
    title_en: 'Interview signup',
    constant: 'INTERVIEW_SIGNUP_MAX_POINTS',
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

function categoryFromFile(fileName) {
  return fileName.replace(/\.ya?ml$/, '');
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
      category,
      category_label: CATEGORY_LABELS[category] || category,
      point_value: current.point_value ?? 0,
      point_prereq_slug: current.point_prereq_slug || '',
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
        point_value: 0,
        point_prereq_slug: '',
      };
      continue;
    }
    if (!current) continue;

    if (/^  title:\s*$/.test(line)) {
      current.section = 'title';
      continue;
    }
    if (/^  [A-Za-z_][A-Za-z0-9_]*:\s*/.test(line)) {
      current.section = '';
    }
    const nestedTitleMatch = line.match(/^    en:\s*(.+)$/);
    if (current.section === 'title' && nestedTitleMatch) {
      current.title_en = stripQuotes(nestedTitleMatch[1]);
      continue;
    }

    const fieldMatch = line.match(/^  (title_en|point_value|point_prereq_slug):\s*(.*)$/);
    if (!fieldMatch) continue;
    const [, field, rawValue] = fieldMatch;
    if (field === 'point_value') {
      current.point_value = parsePointValue(rawValue);
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
    const match = config.match(new RegExp(`${source.constant}\\s*=\\s*(\\d+)`));
    return {
      kind: 'manual',
      id: `manual:${source.slug}`,
      slug: source.slug,
      title_en: source.title_en,
      category: 'manual',
      category_label: CATEGORY_LABELS.manual,
      point_value: match ? Number.parseInt(match[1], 10) : 0,
      point_prereq_slug: '',
      file: 'adoorback/surveys/reimbursement_config.py',
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

  const manual = await readManualSources(repoRoot);
  return [...surveys, ...manual];
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
    (allocation?.sources || []).map((source) => [`${source.kind}:${source.slug}`, source.points]),
  );
  return sources.map((source) => ({
    ...source,
    draft_points: saved.has(source.id) ? saved.get(source.id) : source.point_value,
  }));
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
  });
  response.end(JSON.stringify(payload, null, 2));
}

function sendText(response, statusCode, text, contentType = 'text/plain; charset=utf-8') {
  response.writeHead(statusCode, {
    'content-type': contentType,
    'cache-control': 'no-store',
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

      if (request.method === 'POST' && url.pathname === '/api/allocation') {
        const body = await readJsonBody(request);
        const allocation = await writeAllocationFile(outputPath, body.sources);
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
