import { spawn, type ChildProcess } from 'child_process';
import fs from 'fs';
import path from 'path';

// The dashboard lives in <repo>/dashboard; the Python pipeline is in <repo>
export const REPO_ROOT = path.resolve(process.cwd(), '..');
const LOG_DIR = path.join(REPO_ROOT, 'logs');
const MAX_LINES = 300;

export type RunMode = 'target' | 'random';

export interface RunRequest {
  mode: RunMode;
  city: string;
  niche: string;
  quota: number;
}

export interface RunStatus {
  running: boolean;
  request: RunRequest | null;
  startedAt: string | null;
  finishedAt: string | null;
  exitCode: number | null;
  inserted: number;
  currentTarget: { city: string; niche: string } | null;
  completed: boolean;
  logLines: string[];
}

interface RunnerState {
  child: ChildProcess | null;
  status: RunStatus;
  lines: string[];
}

declare global {
  // eslint-disable-next-line no-var
  var __pipelineRunner: RunnerState | undefined;
}

// Kept on globalThis so a dev-server hot reload doesn't lose track of a running pipeline
const state: RunnerState =
  global.__pipelineRunner ??
  (global.__pipelineRunner = {
    child: null,
    lines: [],
    status: {
      running: false,
      request: null,
      startedAt: null,
      finishedAt: null,
      exitCode: null,
      inserted: 0,
      currentTarget: null,
      completed: false,
      logLines: [],
    },
  });

function pythonBinary(): string {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  const venv =
    process.platform === 'win32'
      ? path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe')
      : path.join(REPO_ROOT, '.venv', 'bin', 'python');
  return fs.existsSync(venv) ? venv : 'python';
}

// Log lines start with a timestamp; anything else is stderr noise (e.g. Windows asyncio
// shutdown tracebacks from Playwright) that isn't useful in the dashboard
const LOG_LINE = /^\d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2}),\d+ \[(\w+)\] [\w.]+: (.*)$/;

function handleLine(raw: string) {
  const line = raw.trimEnd();
  if (!line) return;

  const target = line.match(/\[TARGET\] city=(.+?) \| niche=(.+)$/);
  if (target) state.status.currentTarget = { city: target[1], niche: target[2] };

  const progress = line.match(/★ \[QUOTA PROGRESS\].*\((\d+)\/\d+\)$/);
  if (progress) state.status.inserted = parseInt(progress[1], 10);

  const complete = line.match(/\[RUN COMPLETE\] inserted=(\d+)/);
  if (complete) {
    state.status.inserted = parseInt(complete[1], 10);
    state.status.completed = true;
  }

  const parsed = line.match(LOG_LINE);
  if (parsed) {
    state.lines.push(`${parsed[1]} ${parsed[2] === 'INFO' ? '' : parsed[2] + ' '}${parsed[3]}`);
    if (state.lines.length > MAX_LINES) state.lines.splice(0, state.lines.length - MAX_LINES);
  }
}

export function startRun(request: RunRequest): RunStatus {
  if (state.child) {
    throw new Error('A pipeline run is already in progress.');
  }

  const args = ['-u', 'pipeline.py', '--mode', request.mode, '--quota', String(request.quota)];
  if (request.city) args.push('--city', request.city);
  if (request.niche) args.push('--niche', request.niche);

  fs.mkdirSync(LOG_DIR, { recursive: true });
  const logFile = fs.createWriteStream(path.join(LOG_DIR, 'pipeline_run.log'), { flags: 'w' });

  // spawn with an argument array (no shell), so typed city/niche text can't inject commands
  const child = spawn(pythonBinary(), args, {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8' },
    windowsHide: true,
  });

  state.child = child;
  state.lines = [];
  state.status = {
    running: true,
    request,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    exitCode: null,
    inserted: 0,
    currentTarget: null,
    completed: false,
    logLines: [],
  };

  let buffer = '';
  const onData = (chunk: Buffer) => {
    logFile.write(chunk);
    buffer += chunk.toString('utf-8');
    const parts = buffer.split(/\r?\n/);
    buffer = parts.pop() ?? '';
    parts.forEach(handleLine);
  };
  child.stdout?.on('data', onData);
  child.stderr?.on('data', onData);

  const finish = (code: number | null) => {
    if (state.child !== child) return;
    if (buffer) handleLine(buffer);
    logFile.end();
    state.child = null;
    state.status.running = false;
    state.status.exitCode = code;
    state.status.finishedAt = new Date().toISOString();
  };
  child.on('exit', finish);
  child.on('error', (err) => {
    handleLine(`${new Date().toISOString().replace('T', ' ').slice(0, 19)},000 [ERROR] runner: ${err.message}`);
    finish(-1);
  });

  return getStatus();
}

export function stopRun(): void {
  const child = state.child;
  if (!child?.pid) return;
  if (process.platform === 'win32') {
    // Kill the whole tree so Playwright's Chromium processes go too
    spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
  } else {
    child.kill('SIGTERM');
  }
}

export function getStatus(): RunStatus {
  return { ...state.status, logLines: state.lines.slice(-40) };
}

export function getTargetSuggestions(): { cities: string[]; niches: string[] } {
  const targets = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, 'targets.json'), 'utf-8'));
  return { cities: Object.keys(targets.cities), niches: targets.niches };
}
