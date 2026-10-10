# dot-windows-cua-repair

An unofficial Windows computer-use automation (CUA) repair skill for Codex Desktop and Dot local Work executors. It covers four browser runtime issues and a separate, conditional fix for a visible Computer Use skill with missing `node_repl` registration: **apply all applicable repairs and run local checks in one pass, without requiring confirmation or repeated testing from Dot.**

Includes diagnostics, an installer that checks version and file fingerprints, startup checks, timing instrumentation, conditional MCP registration, and rollback.

## Install with one command

With Node.js, npm, and Git installed, run this command from your project directory:

```powershell
npx skills add GShenLin/dot-windows-cua-repair
```

To install specifically for Codex in the current project:

```powershell
npx skills add GShenLin/dot-windows-cua-repair --skill dot-windows-cua-repair --agent codex --copy -y
```

Add `-g` for a user-level installation. These commands use the [Vercel Skills CLI](https://github.com/vercel-labs/skills) to fetch the skill directly from GitHub; this repository does not need to be published as an npm package. Running `npx skills add` installs the instructions and scripts. It does not automatically modify the Codex runtime.

After installation, ask your skill-enabled assistant:

> Use `$dot-windows-cua-repair` to apply the applicable Windows CUA repairs, check the conditional node_repl registration fix, and complete local checks in one pass, without requiring Dot to participate or confirm the results.

For AgentPark, you can also copy the entire `skills/dot-windows-cua-repair` directory into your project's `.agents/skills/` directory.

## Included repairs

| Layer | Symptoms | Repair |
|---|---|---|
| Platform environment | MXC platform-directory errors / HRESULT 0x80070003 | Restore `SystemDrive` and `LOCALAPPDATA` |
| Startup directory | Trusted Node exits unexpectedly; stderr reports `EPERM chdir` | Align the startup directory with the host-provided `sandboxCwd` before the first JS call, preserving permission metadata |
| Browser connection | `iab` is unavailable, or the browser is not registered to the task | Inherit connection context from the tool's own verified parent Work executor |
| Network environment | A page is created, but binding to its tab times out while waiting for website checks | Inherit the parent process's existing proxy settings, preserving website checks and authentication |
| Conditional tool registration | Computer Use skill is visible, but its plugin root has no MCP declaration despite an existing, enabled desktop `node_repl` configuration | Register an exact copy of that existing definition in the plugin root; verify local discovery and `tools/list`, with transaction-based rollback |

The user reported success for all four repairs in the original deployment. This public package is a parameterized version of that implementation. Its offline tests and the original deployment results are documented separately to make their validation scope clear.

The newer registration fix passed local V1 discovery and MCP tool listing in the original deployment. The V2 diagnostic returned `-32601` (unsupported). The original Dot task's final tool catalog, cloud filtering, and desktop actions were **not verified by this fix**. A browser-only `cua_repl` does not by itself establish whether the separate Windows `node_repl` is available. Neither a visible skill nor an enabled settings switch proves that a task received the tool.

## Supported environment and dependencies

- Windows. The automated installer accepts only the known original file fingerprints for **CUA 26.1007.21434**. The desktop package version recorded in the original session was 26.1007.2314.0.
- Python 3 and `psutil` for the original runtime scripts; **Python 3.11+** for the new registration scripts. If needed, install the dependency with `python -m pip install psutil`. The scripts do not install dependencies automatically.
- An existing Codex CUA runtime and its Node executable. This repository does not distribute the vendor runtime, credentials, or logs from the original machine.
- The installer refuses to overwrite unknown versions or unrecognized modifications. Preview mode and rollback with hash verification are supported.
- The repairs do not enable disabled native screen or mouse capabilities, or change system ACLs, global proxy settings, or browser policies.
- Registration also requires Computer Use **26.1007.21434**, an explicitly enabled plugin, and an existing enabled desktop definition with the original sky service. It refuses unknown declarations, task-specific identity overrides, and unsupported versions. A desktop restart may change native connection paths: refresh an owned registration using its previous transaction manifest, as described below.

## Documentation and scripts

The detailed skill instructions and reference documents are currently in Chinese.

- [Skill instructions](skills/dot-windows-cua-repair/SKILL.md)
- [Script usage, installation, and rollback](skills/dot-windows-cua-repair/references/scripts.md)
- [Failure mechanisms and diagnosis](skills/dot-windows-cua-repair/references/diagnosis.md)
- [Missing node_repl: registration, local checks, refresh, and rollback](skills/dot-windows-cua-repair/references/node-registration.md)
- [Local verification and cleanup](skills/dot-windows-cua-repair/references/acceptance.md)
- [Original troubleshooting record](skills/dot-windows-cua-repair/references/session-2026-10-10.md)

From the repository root, run the package checks without modifying the installed runtime:

```powershell
python -X utf8 -B skills/dot-windows-cua-repair/scripts/check_bundle.py
python -X utf8 -B skills/dot-windows-cua-repair/scripts/test_repair.py
python -X utf8 -B skills/dot-windows-cua-repair/scripts/test_node_registration.py
```

The runtime installer defaults to preview mode, with `--fixes all` selecting the four environment repairs. The conditional registration step uses `node_registration.py` in the same maintenance session; it is not an additional `--fixes` option. Both installers require an explicit `--apply` flag and a new backup directory. `node_registration_probe.py` only performs local discovery and tool listing, without `tools/call` or desktop actions. See the script usage and registration guides for details.
