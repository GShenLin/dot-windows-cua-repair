# dot-windows-cua-repair

Windows 上 Codex Desktop / Dot 本地执行器的 CUA 故障修复 Skill。把一次真实排错中定位到的四层问题整理成可复用步骤：**一次完成适用的四层修复与本机检查，无需 Dot 配合确认。**

Unofficial Windows CUA repair skill for Codex Desktop and local Work executors. Includes diagnostics, a fingerprint-gated installer, startup checks, timing instrumentation and rollback.

## 一条命令安装

已安装 Node.js / npm 和 Git 后，在项目目录执行：

```powershell
npx skills add GShenLin/dot-windows-cua-repair
```

仅安装到 Codex 的当前项目，可使用：

```powershell
npx skills add GShenLin/dot-windows-cua-repair --skill dot-windows-cua-repair --agent codex --copy -y
```

需要用户级安装时加 `-g`。命令使用 [Vercel Skills CLI](https://github.com/vercel-labs/skills) 从 GitHub 获取 Skill，不需要把本仓库发布到 npm。`npx skills add` 安装的是说明与脚本，不会自动修改 Codex 运行时。

安装后对支持 Skill 的助手说：

> 使用 `$dot-windows-cua-repair`，按已验证方案一次完成 Windows CUA 四层修复及本机检查，无需 Dot 配合确认。

AgentPark 也可直接将 `skills/dot-windows-cua-repair` 整个目录复制到项目的 `.agents/skills/` 下。

## 包含的修复

| 层级 | 故障现象 | 修复方式 |
|---|---|---|
| 平台环境 | MXC platform directory / HRESULT 0x80070003 | 恢复 SystemDrive、LOCALAPPDATA |
| 启动目录 | trusted Node 意外退出，stderr 为 EPERM chdir | 首次 JS 前对齐宿主 sandboxCwd，保持权限元数据 |
| 浏览器连接 | 找不到 iab / 浏览器未注册到任务 | 继承自己已核对的父 Work 执行器连接信息 |
| 网络环境 | 页面已创建，但绑定标签页等待网站检查而超时 | 继承父进程已有代理，保持网站检查与认证 |

历史部署的四层修复已获得使用者成功反馈。公开包为参数化整理版，其离线测试与真实历史验证分别记录，避免将测试范围混为一谈。

## 支持范围与依赖

- Windows；自动安装器只接受已知原始 **CUA 26.1007.21434** 的文件指纹，对应记录中的桌面包版本为 26.1007.2314.0。
- Python 3 与 `psutil`；需要时执行 `python -m pip install psutil`。脚本自身不自动安装依赖。
- 已安装的 Codex CUA 运行时及其 Node。公开仓库不分发厂商运行时、认证信息或原机器日志。
- 未知版本或已有不明修改会拒绝覆盖；支持单独预览与基于哈希的回滚。
- 不开启被禁用的原生屏幕/鼠标能力，不修改系统 ACL、全局代理或浏览器策略。

## 文档与脚本

- [Skill 入口](skills/dot-windows-cua-repair/SKILL.md)
- [脚本操作、安装及回滚](skills/dot-windows-cua-repair/references/scripts.md)
- [故障机制与诊断](skills/dot-windows-cua-repair/references/diagnosis.md)
- [本机验证与收尾](skills/dot-windows-cua-repair/references/acceptance.md)
- [历史维修记录](skills/dot-windows-cua-repair/references/session-2026-10-10.md)

从本仓库根目录运行不修改运行时的包检查：

```powershell
python -X utf8 -B skills/dot-windows-cua-repair/scripts/check_bundle.py
python -X utf8 -B skills/dot-windows-cua-repair/scripts/test_repair.py
```

安装器默认只预览，`--fixes all` 是默认整套方案；应用需显式 `--apply` 和新的备份目录。详细用法见脚本操作文档。
