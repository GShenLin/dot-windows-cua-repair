# Computer Use skill 可见，但独立 node_repl 缺失

这是原四层浏览器修复之外的**条件分支**，在同一次维修中完成诊断、注册和本机验证，不需要 Dot 确认。不要只因“屏幕/鼠标禁用”就执行：必须先确认下面的注册缺口，而非权限拒绝、模型限制或该任务类型不支持。

## 注册链与本次证据

1. Windows Computer Use skill 使用独立 `node_repl` 与已有的 `@oai/sky/service`。`cua_repl` 的 `CUA_REPL_ENABLED_SURFACES=browser` 只描述那个工具的浏览器能力，不足以判断独立 Windows 工具是否可用。设置页“任意应用”开启也不能证明工具已提供给当前任务。
2. 本次有效用户配置已有启用的 `mcp_servers.node_repl`，Computer Use 插件也已启用；但插件目录没有 `.mcp.json`，插件清单没有 `mcpServers` 声明。因此插件根发现能返回 skill，却未返回 MCP 定义。这是本机能复现的注册缺口。
3. 本地源码中，插件根选择与 skill/MCP 文件发现是不同步骤；`exec-server/src/environment_config.rs` 的独立用户配置导入路径只保留带 `url` 的服务器，不能据此假定现有 stdio 配置会自动进入 Local Work。源码用于解释本地路径，不代表已验证云端运行相同版本。
4. 修复只在该 Computer Use 插件根新增 `.mcp.json`，内容为当前既有 `node_repl` 定义的完整拷贝，放在 `mcpServers.node_repl` 下。不改 config.toml、厂商 plugin.json、命令、参数、权限、受信服务名单或工具名称；没有显式任务身份可写入此文件。
5. 原始本机修复于 **2026-10-10 17:05:20（北京时间）**通过新诊断进程的 V1 插件发现和 MCP `tools/list`：发现 skill 与 MCP，工具包括 `js`、`js_add_node_module_dir`、`js_reset`、`turn_ended`。V2 返回 `-32601`，只能记为“不支持本次探测”。**原 Dot 任务的最终工具目录、云端筛选和桌面操作没有在这次修复中验收。**

## 适用条件与停止条件

新脚本要求 Python **3.11+**，仅支持 Computer Use **26.1007.21434**。它从 `$env:CODEX_HOME` 或当前用户 `.codex` 读取配置；可用 `--codex-home` 指定实际目录。

预检要求：插件明确启用；既有 node_repl 是启用的 stdio 服务；现有绝对路径分别指向 node_repl.exe 和 codex.exe；版本一致；既有受信服务包含 sky；CODEX_HOME 一致；插件没有厂商 MCP 声明；目标不是重定向路径。脚本不创造缺失的运行时定义，不启用插件或服务，不把别的任务连接信息写进去。

若用户配置本就没有可用 node_repl，或失败来自权限/签名/策略拒绝，保留现状并报告缺失层，不能套用此注册修复。若已有未知 `.mcp.json`，拒绝覆盖。版本变化、旧手工补丁和旧 change-record.json 都不能伪装成这个安装器的事务。

## 同一次维修的执行步骤

先切换到安装后的 Skill 目录。以下命令不启动桌面操作；应用注册需要 `--apply`，默认只预览。

```powershell
$skillDir = (Get-Location).Path
python -X utf8 -B "$skillDir\scripts\node_registration.py"
```

预览符合实际缺口后，在用户已要求修复的范围内继续应用，不重复请求授权。备份目录必须尚不存在；示例保存在本机用户目录，不能提交到 Git：

```powershell
$registrationBackup = Join-Path $env:LOCALAPPDATA ("CodexRepair\node-registration-" + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
python -X utf8 -B "$skillDir\scripts\node_registration.py" --backup-dir "$registrationBackup" --apply
python -X utf8 -B "$skillDir\scripts\node_registration_probe.py"
```

探测脚本只启动并关闭自己创建的 exec-server / node_repl 诊断进程，调用 initialize、发现接口和 `tools/list`，**不发送 `tools/call`**。不借原任务身份，不读取桌面，不点击，不启动用户应用。它核对当前声明与既有配置是否一致、源文件是否未变，并报告 V1、V2、工具列表及范围。

`local_registration_checks_passed=true` 仅表示声明一致、源文件未变、V1 无错误/警告且含 MCP、必需工具齐全。读取 V2 时，仅 `-32601` 归为 unsupported，其他错误直接失败；V2 的 responded 结果也需单独检查插件数量及 MCP 字段。即使本机检查通过，`task_catalog_verified` 和 `desktop_actions_tested` 仍为 false；不能宣称云端筛选或桌面操作通过。若 V1 缺 MCP、声明不一致或工具缺失，保留报告中的失败，不能以成功退出或看到 skill 代替验证。

有需要可加 `--output` 写入尚不存在的本机 JSON；不要把真实配置、运行时管道、身份、诊断报告或备份发布到开源仓库。

## 激活、刷新与回滚

新增声明须由下一次插件发现及新工具进程读取。已运行的任务可能缓存旧目录；本地 V1 缓存实现不会以文件 mtime 自动失效。`js_reset` 不是插件重新注册。完成本机检查后说明生效范围即可，不强杀应用、不要求 Dot 创建新任务。

这个声明复制的是**当前桌面配置快照**。桌面重启后，原生服务管道或可执行路径可能变化，不能假定旧声明永久有效。原来的首次安装清单在 `$registrationBackup\manifest.json`；需要刷新时，先正常读取当前配置，再提供该清单，并为本次刷新选择新的备份目录：

```powershell
$previousManifest = Join-Path $registrationBackup 'manifest.json'
python -X utf8 -B "$skillDir\scripts\node_registration.py" --previous-manifest "$previousManifest"
$refreshBackup = Join-Path $env:LOCALAPPDATA ("CodexRepair\node-registration-refresh-" + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
python -X utf8 -B "$skillDir\scripts\node_registration.py" --previous-manifest "$previousManifest" --backup-dir "$refreshBackup" --apply
python -X utf8 -B "$skillDir\scripts\node_registration_probe.py"
```

之后再次刷新要使用最新一次 manifest。只有当前目标哈希仍与上次安装相同，才允许替换；外部更新或用户修改会触发拒绝。预览 `changes_required=false` 时无需再次应用。没有旧清单时不猜测归属、不强制覆盖。

回滚沿用通用事务工具。首次安装回滚会删除自己新增且哈希未变的单个 `.mcp.json`；刷新回滚恢复之前的声明。若多次刷新，必须从最新清单向最早清单依次回滚：

```powershell
python -X utf8 -B "$skillDir\scripts\rollback.py" "$registrationBackup\manifest.json"
python -X utf8 -B "$skillDir\scripts\rollback.py" "$registrationBackup\manifest.json" --apply
```

该分支不属于 `repair.py --fixes all` 的文件补丁；同一次工作中按条件追加执行，避免把缺少注册与浏览器环境故障混为一谈。整理后的脚本提供离线事务/拒绝条件/探测边界测试，未在打包时重新部署本机手工修复。
