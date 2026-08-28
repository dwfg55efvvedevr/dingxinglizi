# dingxinglizi

> Software Project Orchestrator v3.0 — portable multi-agent delivery for Codex, Cursor, Claude Code, and OpenCode

[![CI](https://github.com/lizi-product-studio/dingxinglizi/actions/workflows/ci.yml/badge.svg)](https://github.com/lizi-product-studio/dingxinglizi/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/lizi-product-studio/dingxinglizi)](https://github.com/lizi-product-studio/dingxinglizi/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

`dingxinglizi` 是一套跨平台、按需调度、可恢复、可验证的多 Agent 软件交付 Skill。稳定调用名仍是：

```text
$software-project-orchestrator
```

它把“做一个系统”变成一条有唯一事实源、职责边界、阶段门禁、任务包、运行证据和独立 QA 的工程流程。Simple、Standard、Complex 都不会一次拉起全部角色，只激活当前阶段最少且必要的角色。

## 它主要帮助你做什么

- 从 0 到 1 建设新系统，或在老系统上做跨模块迭代；
- 采集并维护业务背景、领域规则、术语、PRD、状态/权限、UX、设计系统、架构、API/数据和测试事实；
- 从全系统角度检查功能、交互、视觉、数据、权限和前后台闭环的一致性；
- 判断需求是否成立，要求证据、暴露假设，并在高影响未知存在时阻止盲目开发；
- 按 `Simple / Standard / Complex` 和当前门禁动态选择角色；
- 用 Task Package 约束目标、输入、范围、文件、能力、模型、验收证据和返回路径；
- 将逻辑能力档映射到当前平台已验证的真实模型，而不是把某个厂商型号永久写死在角色上；
- 在中断后通过项目本地 ledger 判断继续、重规划、人工对账或阻塞；
- 用独立 QA 与按需 Quality Governor 阻止“实现者自验收”和迎合式结论；
- 将已验证结果汇总成待审查的改进候选，但绝不自动改源码、降低门禁或发布。

## v3.0：平台中立核心

| 层 | 责任 |
|---|---|
| Portable Skill | 流程、复杂度/角色/模型路由、门禁、恢复、验证与受监督改进 |
| Native Agents | Codex、Cursor、Claude Code、OpenCode 的原生角色配置 |
| Project `AGENTS.md` | 项目长期规则、权限与禁止事项 |
| Project docs | 唯一业务事实源、版本、决策、契约和验收 |
| MCP / connectors | GitHub、Figma、浏览器、任务系统、数据库、部署等可选外部能力 |

新项目将平台中立运行状态写到 `.dingxinglizi/`。旧 v2 项目可继续直接读取 `.codex/orchestration`、`.codex/runs` 和 `.codex/evolution`；迁移是显式、预览优先、校验哈希、保留源数据的复制过程。

### 支持等级

| 等级 | 含义 |
|---|---|
| L0 | Portable Skill 不可用 |
| L1 | Skill 结构可发现 |
| L2 | 平台中立流程、文档和脚本可用 |
| L3 | 原生角色配置、宿主可执行文件和模型库存都有验证证据 |
| L4 | 本地执行声明通过精确 schema、指纹及已验证模型库存/运行时版本的一致性检查 |

本仓库对四个平台的配置格式和控制合同做自动化测试；当前发布环境只真实检测到 Codex CLI。Cursor、Claude Code、OpenCode 在没有对应本机运行时和执行回执时，不会被宣称为 L4。

## 安装

需要 Python 3.9+，运行时核心只使用标准库。

```bash
git clone https://github.com/lizi-product-studio/dingxinglizi.git /tmp/dingxinglizi
cd /tmp/dingxinglizi
python3 scripts/orchestrator.py platform detect
```

先预览，只安装一个选定平台：

```bash
python3 scripts/orchestrator.py platform install --platform codex --scope user
python3 scripts/orchestrator.py platform install --platform cursor --scope user
python3 scripts/orchestrator.py platform install --platform claude-code --scope user
python3 scripts/orchestrator.py platform install --platform opencode --scope user --opencode-schema v2
```

确认计划后，只对所选命令增加 `--apply`：

```bash
python3 scripts/orchestrator.py platform install --platform codex --scope user --apply
```

已有文件默认不会覆盖；只有明确加 `--update` 才会更新不同的生成文件。安装器不联网、不登录、不读取凭据、不调用包管理器，也不会顺带安装其他平台。

OpenCode V1 与 V2 的权限 schema 不兼容。已安装的 `opencode --version` 返回可解析的 1.x/2.x 版本时可省略 `--opencode-schema` 自动选择；离线安装、版本输出不明确或未来主版本会拒绝猜测，必须明确传 `v1` 或 `v2`。V1 生成 `permission.task`，V2 生成有序 `permissions` 与 `subagent` 规则。

| 平台 | User Skill | User Agents | Project Skill | Project Agents |
|---|---|---|---|---|
| Codex | `~/.agents/skills/` | `~/.codex/agents/` | `.agents/skills/` | `.codex/agents/` |
| Cursor | `~/.cursor/skills/` | `~/.cursor/agents/` | `.cursor/skills/` | `.cursor/agents/` |
| Claude Code | `~/.claude/skills/` | `~/.claude/agents/` | `.claude/skills/` | `.claude/agents/` |
| OpenCode | `~/.config/opencode/skills/` | `~/.config/opencode/agents/` | `.opencode/skills/` | `.opencode/agents/` |

完整格式来源与限制见 [平台适配说明](references/platform-adapters.md)。

## 3 分钟开始一个项目

```bash
SPO=/path/to/dingxinglizi

python3 "$SPO/scripts/orchestrator.py" init /path/to/acme-crm \
  --project-name "Acme CRM" \
  --domain "CRM" \
  --complexity Standard \
  --domain-pack crm \
  --platform cursor

python3 "$SPO/scripts/orchestrator.py" doctor /path/to/acme-crm
python3 "$SPO/scripts/orchestrator.py" transition /path/to/acme-crm --target DISCOVERY
python3 "$SPO/scripts/orchestrator.py" plan /path/to/acme-crm --quota economy --write
python3 "$SPO/scripts/orchestrator.py" run /path/to/acme-crm
```

也可以在支持 Skill 的宿主中直接说：

```text
$software-project-orchestrator 初始化或安全恢复这个项目，先核实业务事实和问题质量，按当前阶段只调用最少必要角色，最终由独立 QA 验收。
```

领域包内置 ecommerce、crm、saas、group-buying、ai-agent、home-services。它们只提供候选问题与检查项，不会把行业惯例伪装成已确认业务事实。

## 角色与额度控制

常驻职责以 Orchestrator、Requirements、Product Auditor、UX、UI、Architect、Engineering Lead、QA 为基准；Quality Governor 按风险触发。Engineering Lead 可调用 frontend、backend、AI、data、test Worker，但 Worker 不能继续委派。

| 复杂度 | 默认执行方式 |
|---|---|
| Simple | 当前阶段通常 0–1 个子 Agent；合并需求/产品职责，但工程与最终 QA 分离 |
| Standard | 专业职责按门禁逐个启用；只有明确独立的读任务可安全并行 |
| Complex | 完整职责在生命周期内可用，仍按波次按需启动，不一次开满 |

`economy` 最多 1 个活动子 Agent；`balanced` 和 `quality_first` 最多 2 个，且必须满足文件所有权与角色拓扑约束。角色配置存在不等于角色已经启动。

## 跨平台模型路由

v3 核心只表达 `ECONOMY / STANDARD / ADVANCED / EXPERT / EXCEPTIONAL` 与 reasoning effort。具体 provider/model 必须来自当前宿主的已验证 runtime manifest：

```json
{
  "models": [
    {
      "id": "provider/model-id",
      "provider": "provider-name",
      "capability_tier": "EXPERT",
      "reasoning_efforts": ["high", "xhigh"]
    }
  ]
}
```

```bash
python3 "$SPO/scripts/orchestrator.py" platform runtime-manifest \
  --platform cursor \
  --project-dir /path/to/acme-crm \
  --models-file /path/to/models.json \
  --models-verified \
  --evidence-source "Cursor model picker exported 2026-08-28"

python3 "$SPO/scripts/orchestrator.py" platform model-resolve \
  /path/to/acme-crm/.dingxinglizi/orchestration/runtime-manifest.json \
  --tier EXPERT --reasoning high --risk security
```

`--models-verified` 只表示模型库存来源得到明确确认，不证明某次 Agent 实际用了该模型。每次加载 manifest 都会重新探测当前宿主，并重新读取、哈希、规范化原始模型库存；清单超过 24 小时、源文件缺失/变化、字段篡改或当前 executable/version 不一致都会阻塞。v3 Task/Preflight 不接受 `--available-model` 手工覆盖来冒充验证；缺少有效 manifest 时只生成 provider/model 未解析的阻塞草稿。L4 还需要符合 [execution receipt 模板](assets/platforms/common/execution-receipt.template.json) 的本地执行声明，且 provider/model/reasoning/runtime 必须与已验证清单精确一致。它仍不是第三方或密码学执行证明。

Codex v2 项目的 Luna/Terra/Sol 路由仍保持兼容；v3 不把它们当作其他平台的通用型号。

## v2 项目迁移

旧项目无需迁移也可继续使用。需要把控制状态复制到平台中立目录时：

```bash
python3 "$SPO/scripts/orchestrator.py" migrate /path/to/old-project
python3 "$SPO/scripts/orchestrator.py" migrate /path/to/old-project --apply
```

默认复制 orchestration 和 runs；`--include-evolution` 只有在 `.dingxinglizi/evolution/` 已被 Git 忽略时才允许。迁移拒绝符号链接和异常硬链接，限制文件数量/总大小，逐文件验证 SHA-256，写入 migration manifest，并保留原 `.codex` 数据。该操作只迁移目录和原有控制事实，不把模型策略 `1.2.0` 自动升级成 `2.0.0`，也不会自动获得跨供应商模型路由。详细回滚规则见 [migration.md](references/migration.md)。

## MCP 与自动能力准备

MCP 不是核心依赖。Agent 只能声明所需能力，由 Orchestrator 集中解析。固定 commit、允许仓库、匹配哈希、允许许可证、无可执行代码的 Skill 候选可被安全准备到当前平台的项目 Skill 目录；但磁盘存在不等于宿主已发现。

自动写入 MCP 配置目前只对 Codex 的受管、无凭据、只读 HTTPS MCP 开放。Cursor、Claude Code、OpenCode 必须走各自宿主支持的配置/授权流程，再把运行时发现证据写回清单。未知社区代码、OAuth、密钥、写权限、数据库和部署能力保持阻塞。

## 验证

```bash
python3 -m py_compile scripts/*.py
python3 -m unittest discover -s scripts/tests -v
python3 scripts/orchestrator.py eval
python3 scripts/orchestrator.py doctor
python3 scripts/orchestrator.py platform doctor --platform codex --scope user
```

完整命令见 [USAGE.md](USAGE.md)，设计合同见 [SKILL.md](SKILL.md) 和 [references/](references/)，安全边界见 [SECURITY.md](SECURITY.md)。

## 诚实边界

本地 CLI 能生成计划、策略、配置、Task Package、ledger、恢复决策、验证结果和待审查改进候选；它不能凭空登录平台、读取剩余额度、保证宿主已加载 Skill/MCP、恢复已消失的 Agent 会话、证明业务事实正确，或替用户完成生产发布和不可逆操作。公开发布、生产写入、购买、外部消息、敏感数据、凭据和破坏性迁移仍需单独授权。

## License

MIT。欢迎提交 issue 和 pull request；修改路由、迁移、权限、适配器或恢复策略时，请同时更新测试和离线评测。

---

## English

`dingxinglizi` v3 is a portable, on-demand, resumable, evidence-based multi-agent software delivery Skill for Codex, Cursor, Claude Code, and OpenCode. It separates portable project truth and control state from host-native Agent profiles, routes each Task Package through abstract capability tiers resolved against an explicitly verified runtime inventory, preserves v2 Codex projects, and requires independent QA before completion.

The four adapters are contract-tested. OpenCode V1 and V2 use separate version-aware renderers and unknown major versions fail closed. Compatibility is reported as L0–L4, and a rendered profile is never presented as proof that a native session launched or used a specific model. See [USAGE.md](USAGE.md) for installation, initialization, runtime evidence, migration, and platform-specific limits.
