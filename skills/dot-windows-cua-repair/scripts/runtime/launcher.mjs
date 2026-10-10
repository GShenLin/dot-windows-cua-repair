#!/usr/bin/env node
import * as cua_repl from '@oai/cua-repl';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const config = JSON.parse(readFileSync(new URL('./repair-context.json', import.meta.url), 'utf8'));
if (process.platform !== 'win32') throw new Error('This repair is Windows-only.');
const fixes = new Set(config.fixes);
if (fixes.has('browser') || fixes.has('proxy')) {
  const context = spawnSync(config.python, [
    '-I', fileURLToPath(new URL('./parent_context.py', import.meta.url)), String(process.pid),
  ], {encoding: 'utf8', windowsHide: true, timeout: 5000, maxBuffer: 32768});
  if (context.error || context.status !== 0) {
    throw new Error('Cannot inspect verified parent context: ' +
      (context.error?.message ?? context.stderr.trim()));
  }
  const inherited = JSON.parse(context.stdout);
  const groups = [];
  if (fixes.has('browser') && inherited.kind === 'local-work') {
    groups.push([inherited.env, ['BROWSER_USE_ACCESS_PIPE_PATH',
      'BROWSER_USE_ACCESS_EXECUTOR_ID', 'BROWSER_USE_ACCESS_VERIFYING_IDENTITY']]);
  }
  if (fixes.has('proxy') && ['local-work', 'local-codex'].includes(inherited.kind)) {
    groups.push([inherited.proxy_env, ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
      'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy']]);
  }
  for (const [values, keys] of groups) {
    for (const key of keys) {
      const value = values?.[key];
      if (typeof value !== 'string' || !value) continue;
      if (process.env[key] && process.env[key] !== value) {
        throw new Error('Conflicting parent environment key: ' + key);
      }
      process.env[key] = value;
    }
  }
}
if (fixes.has('cwd')) {
  process.env.CUA_REPL_WINDOWS_CWD_BRIDGE = fileURLToPath(new URL('./windows-cwd-bridge.mjs', import.meta.url));
}
if (fixes.has('platform')) {
  const drive = process.env.SystemDrive ?? /^[A-Za-z]:/.exec(process.env.SystemRoot ?? process.env.windir ?? '')?.[0];
  if (!drive || !/^[A-Za-z]:$/.test(drive)) throw new Error('Cannot determine SystemDrive');
  const values = {SystemDrive: drive, LOCALAPPDATA: process.env.LOCALAPPDATA ?? config.local_appdata};
  const allowed = (process.env.NODE_REPL_UNTRUSTED_ENV_ALLOWLIST ?? '').split(',').map(x => x.trim()).filter(Boolean);
  for (const [key, value] of Object.entries(values)) {
    process.env[key] = value;
    if (!allowed.some(x => x.toLowerCase() === key.toLowerCase())) allowed.push(key);
  }
  process.env.NODE_REPL_UNTRUSTED_ENV_ALLOWLIST = allowed.join(',');
}
try {
  await cua_repl.launch();
} catch (error) {
  console.error('cua_repl could not start: ' + (error instanceof Error ? error.message : String(error)));
  process.exitCode = 1;
}
