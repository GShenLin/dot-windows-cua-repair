# 诊断与决策

| 症状 | 必查证据 | 本次结论 | 不能推断 |
|---|---|---|---|
| 恢复对话失败 / App-Server is not available | 本地进程、远端 WebSocket 日志、任务类型 | 观察到 durable open_timeout / 1006，独立于 CUA | CUA 恢复不等于旧对话恢复 |
| MXC platform directory / 0x80070003 | SystemDrive、SystemRoot、LOCALAPPDATA、KnownFolder | 精简环境漏了平台变量 | 所有同码错误都能靠补变量解决 |
| trusted Node 意外退出 | 同时间的真实 stderr 与启动目录 | 后续一次为 EPERM chdir | 通用退出消息证明仍是目录不存在 |
| Browser is not available: iab | Work 父进程变量、服务准备与路由捕获 | 三个 BROWSER_USE_ACCESS_* 未继承 | 可以借别的任务管道 |
| 页面已建，绑定超时 | DOM-ready、网站检查耗时、默认 deadline | 本机 site-status 两次直连各约 21.4 秒 | 看见页面就代表工具已返回 |
| cua_repl 屏幕/鼠标禁用 | CUA_REPL_ENABLED_SURFACES、独立 Windows 工具注册 | 该 cua_repl 仅 browser；独立工具另查 | 整台机器或所有任务都不支持桌面 |
| Computer Use skill 可见、独立 node_repl 缺失 | 插件启用、既有 stdio 配置、插件根 MCP 声明、发现响应 | 本机插件根缺 MCP 声明；补齐后 V1 与 tools/list 通过 | 原任务云端工具筛选或桌面操作已通过 |

## 只读收集

`diagnose.py` 列出候选 `.mcp.json`；多版本时指定有效文件，不按最大目录名猜当前版本。从 command、args、env 追踪 Node、node_repl、Codex。应用日志通常在 `%LOCALAPPDATA%/Codex/Logs/YYYY/MM/DD`，运行时在 `%LOCALAPPDATA%/OpenAI/Codex/runtimes`，以实际配置为准。

区分 `ChatGPT.exe → codex app-server → CUA → node_repl → trusted worker` 与 `codex exec-server --remote … → CUA`。只记录匹配进程的允许字段，不导出完整环境、完整命令行或 proxy 凭证。

北京时间减 8 小时为 UTC。对齐初始化、页面创建、DOM-ready、报错和 turn-ended；日志文件修改时间可能滞后。其他任务的路由探测失败不等于本任务失败。

## 四个机制

四层浏览器环境机制之外，独立 node_repl 缺失按 [注册链修复](node-registration.md) 在本次工作中追加处理。先确认本机已有启用的定义和缺失声明，不修改权限，不将配置缺失一概视为加载故障。

### platform

KnownFolder 的 ProgramData 展开用到 `%SystemDrive%`。精简 MCP 环境缺此值可使 MXC 原生初始化报 0x80070003。由 SystemRoot/windir 取盘符，LOCALAPPDATA 取当前用户 KnownFolder；只把这两项加入既有 untrusted env allowlist，不增加文件/网络权限。

### cwd

worker 启动后执行 `process.chdir(process.argv[2])`。MXC 任务目录与外层插件启动目录不同，切回可 EPERM。桥读取宿主原请求 `_meta['codex/sandbox-state-meta']`：首次 JS、`useMxc=true`、未执行 JS 且无未完成请求时，关闭未用的 NodeREPL，在宿主提供的 file URI 目录重启，重放 initialize/initialized，然后逐字转发请求。运行 JS 后不得搬目录；不能通过扩展沙盒路径掩盖错误。

### browser

父 Work 执行器有 `BROWSER_USE_ACCESS_PIPE_PATH`、`BROWSER_USE_ACCESS_EXECUTOR_ID`、`BROWSER_USE_ACCESS_VERIFYING_IDENTITY`，插件当时只转发 CODEX_WINDOWS_REGISTERED_CORE。缺 executor ID 时浏览器服务不走 Work 准备逻辑，无法捕获任务路由。核对直接父进程的可执行文件路径、同用户和远端端点后恢复三项；保留 Work 设置与签名校验。不能搜索其他进程借值。

### proxy

`getTab/createBrowserTab` 包装层在返回前读 AX，该路径可能前后检查网站策略。`nodeRepl.fetch` 由受信 worker 通过 authenticated_fetch 消息交给 NodeREPL supervisor，并非页面 fetch；页面代理或普通 Node fetch dispatcher 不一定影响它。

本次父 app-server/exec-server 有 HTTP_PROXY、HTTPS_PROXY、NO_PROXY，CUA/NodeREPL 没有。修复仅恢复父进程已有代理，不改全局代理，不把代理/身份放进 untrusted allowlist，保留请求、认证和响应判断。

如需连通性对照，可手动对同一公开检查服务做无凭证 direct/proxy 检查，不携带真实 task ID、token 或浏览历史。403/401 只证明收到响应；最终须实际 CUA 成功。原库请求失败后的 best-effort 行为不等于检查通过。

## 可撤销耗时插桩

`timing.py` 仅接受已知原始 browser-service 指纹，在 runCommand 与 site-status fetch 前后记 UTC、阶段、命令类型，不记请求头、URL、正文或身份。保持原 await、异常与策略行为。启用后让新 kernel 载入，只做一次有界诊断，然后用同一清单恢复。日志在被测任务 cwd 的 `cua-browser-timing.log`；没有新记录不能假设已加载。

若网络慢、浏览器操作快，追踪真实网络传输。若用户任务未重现同样延迟，只报告本机证据和推断，不冒称 Dot 根因最终通过验收。
