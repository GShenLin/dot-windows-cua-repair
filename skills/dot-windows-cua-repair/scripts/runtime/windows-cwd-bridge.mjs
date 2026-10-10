// Preserve all MCP payloads and sandbox permissions. Before the first JS call,
// start NodeREPL in the task cwd supplied by the host's sandbox metadata.
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { statSync } from 'node:fs';
import path from 'node:path';

const executable = process.argv[2];
let child;
let initializedRequest;
let initializedNotification;
let activeCwd = process.cwd();
let boundToTask = false;
let stopping = false;
let generation = 0;
const pending = new Set();
const internal = new Map();
const key = (value) => path.resolve(value).toLowerCase().replace(/[\\/]+$/, '');
const write = (line) => child.stdin.write(line + '\n');
const replyError = (request, message) => {
  if (request.id !== undefined) {
    process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: request.id,
      error: { code: -32603, message } }) + '\n');
  }
};

function start(cwd) {
  const currentGeneration = ++generation;
  child = spawn(executable, [], { cwd, env: process.env, stdio: ['pipe', 'pipe', 'inherit'], windowsHide: true });
  child.on('error', (error) => {
    process.stderr.write(`CUA cwd bridge: ${error.message}\n`);
    process.exitCode = 1;
    process.stdin.destroy();
  });
  child.on('exit', (code) => {
    if (currentGeneration === generation && !stopping) {
      process.exit(code ?? 1);
    }
  });
  createInterface({ input: child.stdout, crlfDelay: Infinity }).on('line', (line) => {
    if (currentGeneration !== generation) return;
    let message;
    try { message = JSON.parse(line); } catch { process.stdout.write(line + '\n'); return; }
    if (message.id !== undefined && internal.has(message.id)) {
      const resolve = internal.get(message.id);
      internal.delete(message.id);
      resolve(message);
      return;
    }
    if (message.id !== undefined && !message.method) pending.delete(message.id);
    process.stdout.write(line + '\n');
  });
}

async function bindTaskCwd(cwd) {
  if (!initializedRequest || pending.size !== 0) {
    throw new Error('Cannot align task cwd while MCP initialization or other requests are pending; retry the call.');
  }
  if (!statSync(cwd).isDirectory()) throw new Error('Sandbox task cwd is not a directory.');
  const old = child;
  // Invalidate the old stdout/exit callbacks before stopping the uninitialized kernel.
  ++generation;
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Previous NodeREPL did not stop.')), 5000);
    old.once('exit', () => { clearTimeout(timer); resolve(); });
    old.stdin.end();
  });
  start(cwd);
  const id = `__cua_cwd_init_${generation}`;
  const response = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { internal.delete(id); reject(new Error('NodeREPL initialization timed out.')); }, 15000);
    internal.set(id, (value) => { clearTimeout(timer); resolve(value); });
    write(JSON.stringify({ ...initializedRequest, id }));
  });
  if (response.error) throw new Error('NodeREPL initialization failed after aligning task cwd.');
  if (initializedNotification) write(initializedNotification);
  activeCwd = cwd;
  process.stderr.write(`CUA cwd bridge: aligned NodeREPL startup with sandbox task cwd ${cwd}\n`);
}

async function forward(line) {
  let message;
  try { message = JSON.parse(line); } catch { write(line); return; }
  try {
    if (message.method === 'initialize') initializedRequest = message;
    if (message.method === 'notifications/initialized') initializedNotification = line;
    if (message.method === 'tools/call' && message.params?.name === 'js') {
      const state = message.params?._meta?.['codex/sandbox-state-meta'];
      if (state?.useMxc === true && typeof state.sandboxCwd === 'string') {
        const url = new URL(state.sandboxCwd);
        if (url.protocol !== 'file:') throw new Error('Sandbox task cwd must be a file URI.');
        const cwd = fileURLToPath(url);
        if (key(cwd) !== key(activeCwd)) {
          if (boundToTask) throw new Error('Task cwd changed after JS execution; start a fresh tool session.');
          await bindTaskCwd(cwd);
        }
      }
      // Also forbid relocation after a JS call without MXC metadata.
      boundToTask = true;
    }
    if (message.id !== undefined && message.method) pending.add(message.id);
    // Forward the original request, including the complete permission profile, unchanged.
    write(line);
  } catch (error) {
    process.stderr.write(`CUA cwd bridge: ${error.message}\n`);
    replyError(message, error.message);
  }
}

start(activeCwd);
let queue = Promise.resolve();
const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on('line', (line) => { queue = queue.then(() => forward(line)); });
input.on('close', () => { queue.finally(() => { stopping = true; child.stdin.end(); }); });
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => { stopping = true; child.kill(); process.exit(0); });
}
