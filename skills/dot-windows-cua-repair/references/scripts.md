# 脚本操作与回滚

## 环境与作用域

目标是 Windows 当前用户的 Codex CUA 运行时。诊断/父进程读取/启动测试需要 Python 3 与 psutil；脚本不会安装依赖。JS 语法检查使用当前 MCP 配置的 Node。运行时桥是独立 Node 脚本。不要用管理员权限改变目录 ACL 来使检查通过。

新增独立 node_repl 注册脚本需要 Python 3.11+（标准库 TOML 解析）。[注册链操作说明](node-registration.md) 给出 `node_registration.py`、`node_registration_probe.py` 的同轮预览、安装、刷新、验证和回滚命令。它复用现有启用定义，不修改权限，也不属于 `repair.py --fixes all` 的运行时文件补丁。

AgentPark 通过 SKILL.md 发现此包；这些是按需执行的维护脚本，没有注册自动运行的 skill.json 工具。此包不发 HTTP 请求，不新增 AgentPark 网络客户端。若以后把网络诊断做成项目代码，遵守根目录 AGENTS.md 的 CurlHttpTransport 边界。

脚本分为只读诊断/验证与显式写入两类。公开版离线测试使用自行构造的最小样例，不分发厂商运行时代码。`scripts/runtime/*` 是安装器复制的实现，不直接从 Skill 目录启动；它们依赖安装器生成的 repair-context.json 与实际 @oai 包环境。

## 1. 发现与诊断

先切换到安装后的 Skill 目录（其中包含 SKILL.md、scripts、references），再执行下面的命令。

```powershell
$skillDir = (Get-Location).Path
python "$skillDir\scripts\diagnose.py"
```

从候选列表和实际进程确定有效 `.mcp.json`，将其绝对路径赋给 `$mcpConfig`，然后运行：

```powershell
python "$skillDir\scripts\diagnose.py" --mcp-config "$mcpConfig"
```

报告只有指定变量的存在性和父子一致性，不导出值。`--output` 可写入一个**尚不存在**的 JSON 文件，避免覆盖旧证据。进程访问失败会明确报告，不假设变量不存在。配置指纹状态分 known-original、historical-repair、unknown-or-new-repair；最后一种应结合安装清单核对，不直接判故障。

## 2. 选择修复并预览

安装器只支持已知原始构建。默认按本次相同场景一次完成四项；`--fixes all` 也是省略该选项时的默认值。用户明确限定单层才选择子集：

```powershell
python "$skillDir\scripts\repair.py" --mcp-config "$mcpConfig" --fixes all
```

该命令核对版本、两份原始文件 SHA-256、安装路径、依赖、Node 语法和 helper 冲突，并输出预计改动。它不会写运行时、重启服务或修改 MCP 配置。

| 选项 | 触发证据 | 实际作用 |
|---|---|---|
| platform | MXC 平台目录错误且精简环境缺变量 | 补 SystemDrive/LOCALAPPDATA，仅这两项加入 untrusted allowlist |
| cwd | stderr 指向启动后 EPERM chdir | 在首次 JS 前对齐宿主 sandboxCwd，不改权限元数据 |
| browser | 当前 Work 父执行器有三项连接信息但 CUA 没有 | 从自己的已核对父执行器继承，保持设置与签名检查 |
| proxy | 父代理存在、子进程缺失，网站检查网络等待吻合 | 继承父进程已有代理；不改全局代理或 untrusted allowlist |

`--python` 可指定已安装且具有 psutil 的 Python；默认使用当前解释器。它的绝对路径会记录在安装配置中，移动/卸载后可能使工具启动失败，必须保留或回滚。Codex 可执行文件路径也在安装时记录，新版本须重新核对。

**已经打过 2026-10-10 手工补丁的本机无需重复安装。** 安装器会拒绝覆盖历史补丁或不明文件。不要为通过预检删 helper 或篡改指纹。若本机已有历史手工修复，使用当时保存在本机的原备份与 Restore.ps1；公开包不包含他人的备份。旧恢复脚本使用其自己的 change-record.json，不与新清单混用。

## 3. 应用与激活

确认预览对应真实故障后，以新、唯一的 `$backupDir` 执行：

```powershell
python "$skillDir\scripts\repair.py" --mcp-config "$mcpConfig" --fixes all --backup-dir "$backupDir" --apply
```

备份目录必须尚不存在。先保存所有原文件与 manifest.json，再写运行时；中断也保留恢复清单。仅修改已核对的入口、必要的 launch.js 并添加选中层的 helper/config。脚本不停止进程，不自动启动新任务。新任务的新 MCP 进程读取新环境；仅 js_reset 不能刷新入口继承。不能因此强杀整套 Codex 或打断无关任务。

若需要从未知版本迁移，先重新读该版本源文件与真实日志，开发适配并单独验证；不要放宽指纹条件或拿旧 vendor 文件覆盖新版本。

## 4. 验证

无部署的包检查和离线行为测试：

```powershell
python "$skillDir\scripts\check_bundle.py" --node "$nodeExe"
python "$skillDir\scripts\test_repair.py"
python -X utf8 -B "$skillDir\scripts\test_node_registration.py"
```

`$nodeExe` 取有效 MCP command。启动验证会运行一个**本脚本拥有**的临时 MCP 进程，用原配置、精简环境及受限 MXC 元数据启动，不操作浏览器：

```powershell
python "$skillDir\scripts\verify_startup.py" --mcp-config "$mcpConfig" --task-dir "$taskDir"
```

`$taskDir` 必须是已存在的诊断目录，且与插件启动目录不同，才能覆盖 cwd 问题。只输出通过状态、用时和有限错误分类。它的父进程是诊断 Python，**不能验证真实 Work 父信息继承、代理认证或网页能力**。随后按 acceptance.md 做本机收尾；网页自测按本机工具可用性选择，无需 Dot 确认。

## 5. 可选耗时插桩

`$browserService` 必须指向同一已确认运行时的 `node_modules/@oai/browser-desktop/scripts/browser-service.mjs`。先预览，需要时再应用：

```powershell
python "$skillDir\scripts\timing.py" --service "$browserService"
python "$skillDir\scripts\timing.py" --service "$browserService" --backup-dir "$timingBackupDir" --apply
```

只有已知原始哈希和两个精确锚点均匹配才写入。日志仅为时间、阶段和操作类型；相对时间差用于拆分 security、site-status fetch、operation。服务插桩可由 kernel 重置重新载入，与入口环境需要新 MCP 的条件不同。诊断结束立即回滚此独立清单，恢复后再重置 kernel，不能把计时改动留在长期运行时。

## 6. 回滚

```powershell
python "$skillDir\scripts\rollback.py" "$backupDir\manifest.json"
python "$skillDir\scripts\rollback.py" "$backupDir\manifest.json" --apply
```

首先核对全部备份和目标文件。若某文件已被更新或用户修改，整个预检失败，不覆盖它。已恢复的文件可重复检查；中断安装可恢复。恢复原文件，只删除本清单创建且哈希仍匹配的单个 helper，不递归删除。保留备份与证据。回滚入口的激活同样需要新工具进程。

## 本包验证范围

新增注册测试使用合成配置，覆盖精确复制、回滚、刷新逆序恢复、未知文件拒绝、配置漂移、禁用/不支持配置拒绝、不持久化任务身份，以及发现探测的失败分类和进程收尾。测试不调用桌面工具；本机原始修复的发现结果与本包离线结果分开记录。

离线测试覆盖完整文件事务、重复恢复、目标漂移拒绝、备份损坏拒绝、修复层选择、父进程身份与端点检查、允许变量筛选。原始版本指纹和包文件有哈希清单，离线事务测试使用独立合成样例；Python/JS 做语法检查。历史部署的四层方案已获用户转述 Dot 成功确认；参数化入口属于整理版，其本机验证范围单独记录，不假称已经重新部署。正常执行不需要 Dot 再验收。
