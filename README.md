# dingxinglizi

> Software Project Orchestrator v2.0 for Codex

[![CI](https://github.com/lizi-product-studio/dingxinglizi/actions/workflows/ci.yml/badge.svg)](https://github.com/lizi-product-studio/dingxinglizi/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/lizi-product-studio/dingxinglizi)](https://github.com/lizi-product-studio/dingxinglizi/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

`dingxinglizi` 是一套可安装、可恢复、可验证的 Codex 多 Agent 软件交付 Skill。它不会一开始把所有角色全部拉起，而是根据项目复杂度、当前阶段、风险与已有证据，只调用此刻最少且必要的角色，并始终把开发与最终 QA 分离。

稳定调用名：`$software-project-orchestrator`

## 30 秒理解它

它帮用户把“做一个软件项目”变成一条有事实源、有责任人、有门禁、有恢复能力、有证据的交付流程：

- 初始化业务背景、领域规则、术语、PRD、状态/权限、架构、API/数据和测试文档；
- 自动判断 `Simple / Standard / Complex`，按当前阶段路由角色，不按复杂度一次开满；
- 提供 Orchestrator、Requirements、Product Auditor、UX、UI、Architect、Engineering Lead、QA 和按需 Quality Governor；
- 允许 Engineering Lead 按需调用 frontend/backend/AI/data/test Worker，但 Worker 不能继续创建 Agent；
- 按每个任务包选择 Luna、Terra、Sol 与思考强度，失败时先辨别失败类型再升级；
- 开发前校验角色—页面、页面—功能、功能—状态、前台—后台、权限和验收矩阵；
- 用 Task Package 约束目标、范围、文件、模型、能力、验收证据和返回路径；
- 用项目本地 run ledger 记录快照、路由、检查点和证据，可在中断后确定性判断恢复、重规划或人工对账；
- 用独立 QA 和按需对抗审查阻止“代码写完就算完成”；
- MCP/连接器按任务最小权限使用，核心流程不依赖 MCP。

## v2.0 新增

- 一个统一入口：`scripts/orchestrator.py`
- `doctor` 安装/项目诊断
- `run / checkpoint / resume / report` 本地运行记录与确定性恢复
- `eval` 离线路由评测套件
- 电商、CRM、SaaS、拼团、AI Agent、家政六个版本化领域包
- Skill/MCP 的准备、锁定与运行时发现分离，未被当前宿主验证时禁止派发
- v1.x 非破坏性迁移说明
- 68 项自动化测试、18 个路由/升级/安全评测案例和 GitHub CI

这些数字只说明控制层行为被测试，不代表产品需求或 Agent 智能达到某个百分比。最终产品质量仍由项目验收、独立 QA 和真实运行证据决定。

## 安装

需要 Python 3.9+。核心脚本只使用 Python 标准库。

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/lizi-product-studio/dingxinglizi.git \
  ~/.agents/skills/software-project-orchestrator
cd ~/.agents/skills/software-project-orchestrator
python3 "$HOME/.agents/skills/software-project-orchestrator/scripts/orchestrator.py" doctor
```

不要只复制 `SKILL.md`；`references/`、`assets/`、`scripts/`、`agents/` 和 `evals/` 都是 Skill 的一部分。如果安装后未显示，重新启动 Codex。

`~/.agents/skills` 是当前官方 USER 级本地 Skill 发现位置；仓库级安装可放在项目的 `.agents/skills/`。参见 [OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)。`doctor` 的 `READY` 只证明包结构可用；请以 Codex 的 Skill 列表或 `$software-project-orchestrator` 实际出现作为宿主已发现的证据。

## 开箱即用

在 Codex 中直接说：

```text
$software-project-orchestrator 初始化这个项目，收集业务背景，判断复杂度，只调用当前阶段必要角色，并在独立 QA 通过后才判定完成。
```

或者用统一命令初始化：

```bash
SKILL=~/.agents/skills/software-project-orchestrator

python3 "$SKILL/scripts/orchestrator.py" init /path/to/acme-crm \
  --project-name "Acme CRM" \
  --domain "CRM" \
  --complexity Standard \
  --domain-pack crm

python3 "$SKILL/scripts/orchestrator.py" doctor /path/to/acme-crm
python3 "$SKILL/scripts/orchestrator.py" transition /path/to/acme-crm --target DISCOVERY
python3 "$SKILL/scripts/orchestrator.py" plan /path/to/acme-crm --quota economy --write
python3 "$SKILL/scripts/orchestrator.py" run /path/to/acme-crm
```

领域包只生成候选清单，不会把行业惯例、合规判断或商业假设伪装成已确认事实。

## 三档复杂度与按需角色

| 复杂度 | 生命周期职责 | 默认执行方式 |
|---|---|---|
| Simple | 合并的需求/产品、工程、独立 QA；必要时设计/架构 | 当前阶段通常 0–1 个子 Agent |
| Standard | 需求、产品、设计、技术、独立 QA | 按门禁逐个或安全只读双角色 |
| Complex | 全部专业职责和必要 Worker 均可用 | 仍按 `required_now` 分波次，不一次全开 |

`economy` 默认最多 1 个活动子 Agent；`balanced` 与 `quality_first` 只有在路由明确判定为独立只读任务，或 Engineering Lead 带一个受控 Worker 时，才允许 2 个。配置文件存在不等于角色已经启动。

## 模型与失败升级

模型不永久绑定角色。Task Package 根据复杂度、任务类型、风险、角色和有效失败记录解析能力档：

- Luna：提取、扫描、机械修改和低风险高频任务；
- Terra：普通实现、分析、设计与平衡成本/质量的任务；
- Sol：架构、安全、权限、迁移、复杂推理、高影响审查和多次有效失败。

高风险任务需要 Sol 时，如果运行时没有验证到 Sol，任务会阻塞，不会静默降级。普通质量失败先提高思考强度，再提高模型档；网络、权限、认证、缺输入或缺工具不会浪费额度升级模型。官方当前模型定位和思考强度以 [OpenAI Models](https://developers.openai.com/api/docs/models) 与 [Model guidance](https://developers.openai.com/api/docs/guides/latest-model) 为准。

同样，Skill 文件已下载或 MCP 配置已写入，只代表“准备完成”，不代表当前 Codex 会话已经发现它。Orchestrator 必须在新会话中核实，并把真实可见项写入项目的 `runtime-inventory.json`；未验证能力会保持阻塞，因此不会把一个磁盘文件虚报为可用工具。

## 中断恢复

```bash
python3 "$SKILL/scripts/orchestrator.py" resume /path/to/acme-crm
python3 "$SKILL/scripts/orchestrator.py" report /path/to/acme-crm
```

恢复只会返回以下确定性结论之一：`RESUME_SAFE`、`REPLAN_REQUIRED`、`RECONCILIATION_REQUIRED`、`BLOCKED`、`DONE`。`checkpoint` 在每次已落盘 handoff、门禁、阻塞或对账后刷新可信快照和证据索引。它不会假设一个已中断 Agent 还活着，也不会静默清除活动会话或自动重复启动角色。

## 验证与评测

```bash
SKILL="${SKILL:-$HOME/.agents/skills/software-project-orchestrator}"

python3 -m unittest discover -s "$SKILL/scripts/tests" -v
python3 "$SKILL/scripts/orchestrator.py" eval
python3 "$SKILL/scripts/orchestrator.py" doctor
```

更完整的命令、现有项目迁移、任务包、能力路由、行业切换和故障排查见 [USAGE.md](USAGE.md)。设计边界见 [SKILL.md](SKILL.md) 与 [references/](references/)。示例见 [examples/](examples/)。

## 架构边界

| 层 | 负责内容 |
|---|---|
| Skill | 流程、复杂度/角色/模型路由、门禁、恢复和验证 |
| Custom Agents | 专业岗位与严格职责边界 |
| 项目 `AGENTS.md` | 长期协作规则和禁止事项 |
| 项目文档 | 唯一业务事实源、版本、决策、契约和验收 |
| MCP/连接器 | GitHub、Figma、浏览器、任务系统、数据库、部署等可选能力 |

本地 CLI 不会直接创建或恢复 Codex Agent 会话，不会读取账户剩余额度，不会绕过 OAuth/凭据，也不会自动信任未知社区代码。生产写入、公开发布、外部消息、购买、敏感数据、破坏性操作和不可逆迁移仍须明确授权。

## 许可证与贡献

MIT License。欢迎提交 issue 和 pull request；修改路由或恢复策略时必须同时更新离线 eval 案例和测试。

---

## English

`dingxinglizi` is a reusable Codex Skill for on-demand, resumable, evidence-based multi-agent software delivery. Its stable invocation is `$software-project-orchestrator`.

It initializes durable project truth, classifies Simple/Standard/Complex work, activates only the current gate's minimum roles, routes each Task Package to Luna/Terra/Sol with explicit reasoning effort, enforces product and architecture gates, recovers from interruptions through a local run ledger, and requires independent QA before completion.

Install the whole repository under `~/.agents/skills/software-project-orchestrator`, run `python3 "$HOME/.agents/skills/software-project-orchestrator/scripts/orchestrator.py" doctor`, and invoke the stable Skill name in Codex. See [USAGE.md](USAGE.md) for the complete workflow and [references/automation-boundaries.md](references/automation-boundaries.md) for honest limits.
