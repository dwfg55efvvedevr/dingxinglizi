# dingxinglizi

> Software Project Orchestrator v3.2.2 — 任务定尺、依赖透明、按需调度、可恢复、可审查的多 Agent 软件交付 Skill

[![CI](https://github.com/lizi-product-studio/dingxinglizi/actions/workflows/ci.yml/badge.svg)](https://github.com/lizi-product-studio/dingxinglizi/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/lizi-product-studio/dingxinglizi)](https://github.com/lizi-product-studio/dingxinglizi/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

`dingxinglizi` 把“让一个 Agent 一直啃完整个项目”改造成一条有事实源、角色边界、阶段门禁、任务包、上下文预算、运行证据和独立 QA 的工程流程。稳定调用名仍是：

```text
$software-project-orchestrator
```

它适合从小修复到新系统 0→1、老系统跨模块迭代，以及大型/复杂仓库的分片审查与有界修复。v3.2 把“项目有多复杂”和“当前任务有多复杂”彻底分开：Complex 项目里的小任务不会再被放大成重大项目流程。

## v3.2 新增：先给任务定尺，再决定流程

即使用户显式调用 `$software-project-orchestrator` 或要求“走全流程”，也必须先选择最小充分模式。用户另行明确指定更高的 `requested_mode` 时可以主动加严，但不能降低风险计算得到的安全下限：

| 当前任务模式 | 适用情况 | 默认角色与验证 |
|---|---|---|
| `QUICK_PATCH` | 文案、样式、局部配置、孤立低风险 bug | 主线程，0 子 Agent；用户可见产物 + 定向检查 |
| `BOUNDED_CHANGE` | 边界明确、可逆的多文件或前端/API 迭代 | Compact Delta → Engineering → 定向验证 → 独立 QA；最多一轮返修 |
| `GOVERNED_DELIVERY` | 新/重大模块，支付、权限、隐私、迁移、并发、不可逆数据或生产动作 | 按风险启用完整门禁与独立 QA |

例如，Complex 拼团平台里的“后台自提点地图定位 + API 失败关闭，无迁移”是 `BOUNDED_CHANGE`，不会重走 Requirements → QG → 全局生命周期。只有当前任务本身出现真实高风险信号才升级。Quality Governor 也改为风险触发；单纯措辞精度不再阻断研发。

首条执行说明会给出模式、范围、Agent 数、预计时间和验证计划。Quick 默认 3–15 分钟、0 子 Agent；Bounded 默认 15–45 分钟、最多 1 个并发子 Agent和 2 个顺序专业会话。连续等待无进展会触发 `TAKEOVER_OR_REPLAN`，而不是无限等。

```bash
python3 scripts/orchestrator.py quick /path/to/project \
  --goal "删除首页说明文案" --target frontend/src/pages/index.vue \
  --verify "targeted frontend test"

python3 scripts/orchestrator.py change /path/to/project \
  --goal "优化后台自提点地图定位并让 API 失败关闭" \
  --surface admin --surface api
```

详见 [任务模式路由](references/task-mode-routing.md) 与 [v3.2 使用示例](examples/task-mode-routing/README.md)。

## v3.1 新增：大型仓库审查引擎

面对单体大仓库、monorepo、多语言、多模块或高风险代码，v3.1 会先固定目标版本、盘点文件与排除项，再按模块和风险切成有预算的审查分片。每个分片对应独立 Task Package，推荐由新会话执行并只返回结构化证据；跨模块 API、数据、权限、状态、迁移与安全问题另开横切分片。

```text
固定 target → 仓库清单 → 模块/风险分片 → 新会话审查
           → 结果校验 → 确定性合并 → 覆盖判定
           → [可选] 独立修复 → 不同会话复审 → 独立 QA
```

- `review_only`：默认模式；审查业务源码，但不修改业务源码。
- `review_and_fix`：只有显式授权后才允许生成与执行有界修复计划。
- 上下文预算是静态估算，不冒充宿主真实 token 使用量；超限时先拆分或缩小任务，而不是把更大模型当作无限上下文。
- 修复者不能关闭自己的发现；修复、复审、最终 QA 由不同身份/会话留下证据。
- 每个分片必须先绑定可校验 Task Package 与 READY 调度回执；COMPLETE 结果还必须逐文件绑定 pinned object、检查项和具体观察，不能用“无发现”空口完成。
- 仓库内容默认是不可信输入；只有显式列出的指令文件进入信任清单。仓库命令、hook、安装、网络、凭据和生成代码默认不执行。
- 文件名无法暴露的权限、隐私、数据完整性、状态机、外部副作用、发布和 AI 安全风险，可用 `--required-risk` 强制生成横切审查。
- 仓库漂移、覆盖不足、超大文件、未知排除项或证据缺失会进入 `STALE` / `BLOCKED`，不会通过弱化口径假装完成。
- `review_only` 的最强结论仅为 `COMPLETE_FOR_DECLARED_SCOPE`；`review_and_fix` 使用区分初始覆盖与修复目标的独立结论。两者都不等于“零缺陷”“100% 理解全部代码”或“绝对上下文干净”。

详细规则见 [大型仓库审查](references/large-repository-review.md)、[上下文卫生](references/context-hygiene.md) 和 [审查—修复闭环](references/review-and-repair.md)。

## 它主要帮助你做什么

- 建立项目唯一事实源，维护业务背景、领域规则、术语、PRD、状态/权限、UX、设计系统、架构、API/数据和测试事实；
- 从全系统角度检查功能、交互、视觉、权限、数据和前后台闭环一致性；
- 质疑缺乏证据的需求与假设，在高影响未知存在时阻止盲目开发；
- 按复杂度、阶段、风险和额度动态选择角色，而非固定启动全部角色；
- 为每个工作包约束目标、输入、范围、文件、模型能力档、验收证据和返回路径；
- 让大仓库按模块/风险并行审查，控制上下文污染并保留可追溯覆盖；
- 在中断后通过项目本地 ledger 恢复、重规划、人工对账或阻塞；
- 用独立 QA 与按需 Quality Governor 阻止实现者自验收和迎合式结论；
- 将经过验证的经验汇总为待人工审查的改进候选，但不自动改门禁或发布。

## 架构与角色

| 层 | 责任 |
|---|---|
| Portable Skill | 流程、复杂度/角色/模型路由、门禁、恢复、验证、审查与受监督改进 |
| Native Agents | Codex、Cursor、Claude Code、OpenCode 的宿主原生角色配置 |
| Project `AGENTS.md` | 项目长期规则、权限与禁止事项 |
| Project docs | 唯一业务事实源、版本、决策、契约和验收 |
| MCP / connectors | GitHub、Figma、浏览器、任务系统、数据库、部署等可选外部能力 |

常驻职责以 Orchestrator、Requirements、Product Auditor、UX、UI、Architect、Engineering Lead、QA 为基准；Quality Governor 按风险触发。Engineering Lead 只能调度 frontend/backend/AI/data/test Worker，Worker 不能继续委派。开发/修复与最终 QA 始终分离。

| 复杂度 | 默认执行方式 |
|---|---|
| Simple | 当前阶段通常 0–1 个子 Agent；可合并职责，但工程与最终 QA 分离 |
| Standard | 专业职责按门禁逐个启用；仅独立读任务安全并行 |
| Complex | 完整职责在生命周期内可用，仍按波次启动；大型审查按模块与风险分片 |

`economy` 最多 1 个活动子 Agent；`balanced` 和 `quality_first` 最多 2 个，且必须满足文件所有权和角色拓扑。角色配置存在不等于角色已经启动。

## 安装

需要 Python 3.9+；运行时核心只使用标准库，不需要 PyYAML 或其他第三方 Python 包。PyYAML 只用于 OpenAI `skill-creator` 自带的可选开发校验器 `quick_validate.py`，缺少它不会影响本 Skill 运行。

```bash
git clone https://github.com/lizi-product-studio/dingxinglizi.git /tmp/dingxinglizi
cd /tmp/dingxinglizi
python3 scripts/orchestrator.py platform detect
python3 scripts/orchestrator.py dependencies
```

先预览，再只安装一个平台：

```bash
python3 scripts/orchestrator.py platform install --platform codex --scope user
python3 scripts/orchestrator.py platform install --platform codex --scope user --apply
```

把 `codex` 换成 `cursor`、`claude-code` 或 `opencode`。OpenCode 离线或版本无法验证时必须增加 `--opencode-schema v1` 或 `v2`。已有不同文件默认不覆盖，只有明确增加 `--update` 才更新。安装器不联网、不登录、不读凭据、不调用包管理器。

`dependencies` 会分别报告运行必需项、Git/宿主 CLI 等可选功能项，以及 PyYAML 这类开发校验项。缺少可选项时会明确说明受影响功能和处理方法，不会把可选依赖伪装成运行阻塞。完整说明见 [依赖与能力限制](references/dependencies.md)。

| 平台 | User Skill | User Agents | Project Skill | Project Agents |
|---|---|---|---|---|
| Codex | `~/.agents/skills/` | `~/.codex/agents/` | `.agents/skills/` | `.codex/agents/` |
| Cursor | `~/.cursor/skills/` | `~/.cursor/agents/` | `.cursor/skills/` | `.cursor/agents/` |
| Claude Code | `~/.claude/skills/` | `~/.claude/agents/` | `.claude/skills/` | `.claude/agents/` |
| OpenCode | `~/.config/opencode/skills/` | `~/.config/opencode/agents/` | `.opencode/skills/` | `.opencode/agents/` |

四个平台共享流程与项目事实，但宿主是否真正发现配置、启动新会话、支持某个模型或记录执行回执，必须由对应运行时证据确认。生成配置不等于真实执行。

## 3 分钟开始一个项目

```bash
SPO=/path/to/dingxinglizi

python3 "$SPO/scripts/orchestrator.py" init /path/to/acme-crm \
  --project-name "Acme CRM" --domain "CRM" \
  --complexity Standard --domain-pack crm --platform codex
python3 "$SPO/scripts/orchestrator.py" doctor /path/to/acme-crm
python3 "$SPO/scripts/orchestrator.py" transition /path/to/acme-crm --target DISCOVERY
python3 "$SPO/scripts/orchestrator.py" plan /path/to/acme-crm --quota economy --write
python3 "$SPO/scripts/orchestrator.py" run /path/to/acme-crm
```

在支持 Skill 的宿主中直接说：

```text
$software-project-orchestrator
初始化或安全恢复这个项目。先核实业务事实和问题质量，按当前阶段只调用最少必要角色；把假设、风险、权限边界和验收证据写进项目，最终由独立 QA 验收。
```

内置 ecommerce、crm、saas、group-buying、ai-agent、home-services 领域包。它们提供候选问题与检查项，不会把行业惯例伪装成已确认事实。

## 大型仓库审查快速开始

审查引擎绑定一个已存在的 `OPEN` run；先完成项目诊断和运行初始化。`preview` 零写入展示目标、清单、排除项和分片计划，确认后再用同参数 `start` 持久化：

```bash
python3 "$SPO/scripts/orchestrator.py" review preview /path/to/project \
  --baseline main --target HEAD --mode review_only \
  --required-risk permissions --required-risk privacy
python3 "$SPO/scripts/orchestrator.py" review start /path/to/project \
  --baseline main --target HEAD --mode review_only \
  --required-risk permissions --required-risk privacy

python3 "$SPO/scripts/orchestrator.py" review status /path/to/project
python3 "$SPO/scripts/orchestrator.py" review contract /path/to/project SHARD-0001
```

根据生成的 `plan.json` 逐个派发分片；`review contract` 会输出该分片的固定目标、pinned objects、风险、预算、信任策略、建议角色与只读边界。每个分片必须通过 `task --review-shard` 建立标准 Task Package、补齐具体字段并由 `preflight --record-ready` 生成调度回执，才能回收结构化 JSON：

```bash
python3 "$SPO/scripts/orchestrator.py" review ingest /path/to/project \
  SHARD-0001 /path/to/SHARD-0001-result.json
python3 "$SPO/scripts/orchestrator.py" review merge /path/to/project
```

最终 QA 不是一条可以跳过治理流程的记录命令：先从 `CODE_REVIEW` 进入 `READY_FOR_QA`，重新路由只启用 `qa`，创建并预检 `TASK-LARGE-REVIEW-FINAL-QA`，由独立会话完成后再用 `--task-id`、QA 证据和逐项最终目标验证 JSON 登记。验证集合必须包含所有 P0/P1，以及所有进入过授权 repair plan 的发现（含 P2/P3），防止后续同文件修复让早期复审静默过期；项目进入 `QA_PASS` 后才可 `finalize`。

修复模式必须在预览和开始时显式使用 `--mode review_and_fix --authorize-fix`。每轮 `record-repair` 与 `record-rereview` 都必须先用 `review repair-contract` 查看约束，再通过 `task --repair-plan` 建立、预检并完成各自的 Task Package。修复 Worker 由 `engineering_lead` 复审；最终发布 QA 仍是后续独立的 `qa`。不要手工编造产物哈希；完整命令和 JSON 约定见 [USAGE.md](USAGE.md)。

## 如何发挥最大能力

不要手工指定“开 8 个 Agent”。给 Skill 高价值事实：目标、仓库/目标版本、权威文档、范围与不做事项、风险面、测试命令、期望证据和真实授权边界。推荐提示词：

```text
$software-project-orchestrator
对这个仓库做 Complex 级 review_only 审查。固定当前 commit；盘点声明范围和全部排除项；按模块及 API/数据/权限/状态/迁移/安全风险切分有预算的分片；每个分片使用新会话和紧凑交接；不要修改业务源码；最后只在证据满足时给出 COMPLETE_FOR_DECLARED_SCOPE，并列出未解决发现、阻塞项和下一步授权。
```

更多 0→1、老系统迭代、审查修复和额度模式提示词见 [最大能力使用指南](references/max-capability-guide.md) 与 [完整使用手册](USAGE.md)。

## 模型与平台边界

Skill 按 Task Package 表达 `ECONOMY / STANDARD / ADVANCED / EXPERT / EXCEPTIONAL` 和 reasoning effort。具体 provider/model 必须来自当前宿主的已验证 runtime manifest，不把 Luna/Terra/Sol 或任何厂商型号永久绑定到角色。上下文超限先拆包；架构、安全、权限、迁移、并发和高影响审查才提高能力档。

Codex v2 项目的 Luna/Terra/Sol 路由继续兼容；它们不被当作 Cursor、Claude Code 或 OpenCode 的通用模型名。跨平台支持表示“流程和适配器可用”，不表示四个平台拥有相同模型、Agent 生命周期、MCP 或执行证明能力。支持等级和 manifest 用法见 [平台适配](references/platform-adapters.md)。

## 验证

```bash
python3 -m py_compile scripts/*.py
python3 -m unittest discover -s scripts/tests -v
python3 scripts/orchestrator.py eval
python3 scripts/orchestrator.py doctor
python3 scripts/check_release_consistency.py
```

离线评测验证确定性控制规则，不衡量模型智能、业务真伪、产品市场匹配或零缺陷。大型审查还必须检查目标指纹、声明范围、分片覆盖、排除项、风险透镜、会话证明和独立 QA 证据。

## 诚实边界

本地 CLI 能生成计划、策略、配置、Task Package、ledger、仓库清单、审查分片、覆盖报告、恢复判断、验证结果和待审查改进候选；它不能凭空登录平台、读取剩余额度、保证宿主已加载 Skill/MCP、证明真实 token 使用、恢复已消失的 Agent 会话、自动理解全部业务语义、保证发现所有缺陷，或替用户完成生产发布和不可逆操作。

公开发布、生产写入、购买、外部消息、敏感数据、凭据和破坏性迁移仍需单独授权。MIT License。

---

## English

`dingxinglizi` v3.2.2 is a task-sized, dependency-transparent, portable, on-demand, resumable, and evidence-based multi-agent software delivery Skill for Codex, Cursor, Claude Code, and OpenCode. Its runtime requires Python 3.9+ and no third-party Python packages; PyYAML is used only by OpenAI skill-creator's optional external validator. It separates project complexity from current task mode so Quick and Bounded changes do not inherit a heavy lifecycle, while an explicit higher `requested_mode` remains available when the user intentionally wants stricter governance. Its large-repository review engine pins a target, inventories declared scope and exclusions, creates budgeted module/risk shards, validates structured results, merges findings deterministically, and optionally governs bounded repair plus independent re-review and QA.

The strongest `review_only` conclusion is `COMPLETE_FOR_DECLARED_SCOPE`; repair mode uses a distinct claim that separates initial full-target coverage from the repaired worktree. Neither means “zero defects” or “full semantic understanding.” Context/token values are estimates, generated host profiles are not proof of native execution, and cross-platform support does not imply identical models or runtime capabilities. See [USAGE.md](USAGE.md) and the [large review example](examples/large-repository-review/README.md).
