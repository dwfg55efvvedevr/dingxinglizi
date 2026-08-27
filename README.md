# Software Project Orchestrator

[中文](#中文介绍) · [English](#english)

## 中文介绍

`software-project-orchestrator` 是一套面向 Codex 的通用软件项目交付 Skill。它把需求、产品完整性、UX、UI、架构、开发和独立 QA 串成一条可验证的交付流程，并根据项目复杂度动态启用最小充分的 Agent 团队。1.1 版进一步按“每个任务包”自动选择 Luna、Terra 或 Sol 及思考强度，并在安全边界内自动准备所需 Skill/MCP。

它适用于从简单内部工具，到 CRM、电商、SaaS、家政平台、AI Agent 等跨行业项目。业务事实保存在项目文档中，不依赖聊天 Session 记忆；外部 MCP/连接器是可选增强能力，不是运行前提。

### 它解决什么问题

- 在开发前补齐业务背景、角色、页面、功能、状态、权限和验收标准。
- 按 `Simple / Standard / Complex` 自动选择 Agent 组合，避免小项目过度编排、复杂项目角色缺失。
- 根据角色、复杂度、任务类型、风险和失败记录，稳定路由 `gpt-5.6-luna`、`gpt-5.6-terra` 或 `gpt-5.6-sol`，无需用户逐个 Agent 配模型。
- 普通质量失败先提升思考强度，再提升模型档位；网络、权限、缺上下文等非推理失败不会浪费额度升级模型。
- 自动复用已安装能力；对项目白名单中固定 commit、哈希校验、许可允许、无需凭据的 Skill/MCP 可自动准备。
- 保持一个全局 Orchestrator，禁止 Agent 网状互相管理。
- 通过阶段门禁阻止“需求没定就开写”“开发完成就自称验收通过”。
- 用标准 Task Package 限定目标、范围、文件所有权、交付物和返回路径。
- 将缺陷打回真正的责任源头，而不是把所有问题都交给开发修补。
- 用独立 QA、测试、截图、日志等证据判定项目是否真正完成。
- 把项目事实和决策沉淀到仓库，便于跨会话继续工作。

### 核心架构

| 层 | 负责内容 |
|---|---|
| Skill | 流程编排、复杂度路由、阶段门禁和验证 |
| Custom Agents | 需求、产品、UX、UI、架构、开发、QA 等专业岗位 |
| 项目 `AGENTS.md` | 长期有效的协作边界和禁止事项 |
| 项目文档 | 业务事实、规则、决策、契约、任务和验收证据 |
| MCP/连接器 | GitHub、Figma、浏览器、任务系统、数据库、部署等可选能力 |

模型不永久绑定角色。任务包先解析 `Economy / Standard / Advanced / Expert / Exceptional` 能力档，再映射到 Luna／Terra／Sol；Orchestrator 以显式模型和思考强度启动 Agent。能力也不由各 Agent 随意安装，而是由一个中央 Capability Broker 在 Agent 启动前统一解析、锁定和配置。

基准角色为：

`orchestrator`、`requirements`、`product_auditor`、`ux`、`ui`、`architect`、`engineering_lead`、`qa`。

按需可以增加 `frontend_worker`、`backend_worker`、`ai_worker`、`data_worker`、`test_worker`。Worker 只能由 Engineering Lead 调度，且不能继续创建下级 Agent。所有复杂度下，开发和最终 QA 必须分离。

### 安装

复制或链接整个目录，不要只复制 `SKILL.md`：

```bash
# 个人范围：对所有项目可用
mkdir -p ~/.agents/skills
cp -R software-project-orchestrator ~/.agents/skills/

# 或仓库范围：只对当前项目可用
mkdir -p /path/to/project/.agents/skills
cp -R software-project-orchestrator /path/to/project/.agents/skills/
```

如果安装后没有立即出现，请重启 Codex。

### 在 Codex 中调用

```text
$software-project-orchestrator 初始化这个项目，收集业务背景，判断复杂度，并生成第一个可执行任务包。
```

也可以直接说明项目类型和目标：

```text
$software-project-orchestrator 这是一个电商售后模块。请先建立业务事实和状态机，完成产品完整性检查，通过门禁后再进入开发。
```

### 初始化项目

在 Skill 目录运行：

```bash
python3 scripts/init_project.py /path/to/project \
  --project-name "Acme CRM" \
  --domain "CRM" \
  --complexity Standard
```

先预览、不写入：

```bash
python3 scripts/init_project.py /path/to/project \
  --project-name "Acme CRM" \
  --domain "CRM" \
  --complexity Standard \
  --dry-run
```

初始化器不会覆盖已有项目合同文件。若项目已有 `AGENTS.md`，请先预览，再人工合并缺失规则，并保留原有的更严格约束。

### 注入业务背景

初始化后，优先填写这些项目文档：

```text
docs/
├── 00-project-context.md
├── 01-domain-rules.md
├── 02-glossary.md
├── 03-role-journey-matrix.md
├── 04-prd.md
├── 05-state-permission-matrix.md
├── 06-ux-spec.md
├── 07-design-system.md
├── 08-system-design.md
├── 09-api-data-contract.md
├── 10-test-plan.md
├── decisions/
└── checklists/
```

`00-project-context.md` 用于记录一句话目标、核心问题、商业模式、用户角色、业务对象、核心流程、状态机、规则、权限、支付退款结算、通知、后台运营、范围、限制、成功指标和未确定问题。

所有事实使用明确状态：`CONFIRMED`、`EVIDENCE_INFERRED`、`DEFAULT_ASSUMPTION`、`NOT_APPLICABLE` 或 `BLOCKING_UNKNOWN`。不能把未经确认的商业、合规或知识产权判断写成事实。

### 复杂度与 Agent 路由

| 级别 | 默认角色组合 |
|---|---|
| Simple | Orchestrator、合并的需求/产品负责人、Engineering Lead、独立 QA；必要时增加设计或架构 |
| Standard | Orchestrator、Requirements、Product Auditor、设计负责人、技术负责人、独立 QA |
| Complex | 8 个基准角色全部启用，并按具体任务增加必要 Worker |

角色可以合并，但职责不能消失；独立最终 QA 不能与开发合并。

### 生成 Task Package

```bash
python3 scripts/create_task_package.py /path/to/project \
  --task-id TASK-001 \
  --owner engineering_lead \
  --reviewer qa \
  --stage READY_FOR_BUILD \
  --task-type implementation \
  --risk permissions \
  --available-model gpt-5.6-luna \
  --available-model gpt-5.6-terra \
  --available-model gpt-5.6-sol \
  --required-capability browser-control \
  --objective "实现已批准的客户资料流程"
```

`--available-model` 必须来自当前运行时实际可用模型；Skill 正常运行时由 Orchestrator 自动读取并维护项目的 runtime inventory，不需要用户逐个配置。任务包还会写入模型、思考强度、路由理由、降级规则、最大尝试次数和能力需求。生成器会拒绝重复任务 ID，以及 owner 与 reviewer 为同一角色的任务。

单独预览模型路由：

```bash
python3 scripts/route_task.py \
  --complexity Complex \
  --task-type architecture \
  --role architect \
  --risk security
```

解析或安全准备能力：

```bash
python3 scripts/resolve_capabilities.py /path/to/project \
  --required browser-control

# 只有计划结果为 AUTO_PROVISIONABLE 时才会实际准备
python3 scripts/resolve_capabilities.py /path/to/project \
  --required browser-control \
  --apply

python3 scripts/check_execution_plan.py /path/to/project \
  tasks/TASK-001.yaml \
  --available-model gpt-5.6-luna \
  --available-model gpt-5.6-terra \
  --available-model gpt-5.6-sol
```

### “完全自动化”的准确范围

无需用户逐个选择角色、模型、思考强度或配置已经批准的能力。系统可以自动完成背景读取、复杂度判断、角色选择、任务路由、可信能力准备、执行、验证、有限重试、模型升级和独立 QA。

它不会无条件执行任意 GitHub/社区代码，也不会绕过 OAuth、密钥、账号连接、许可证、写权限、全局安装、生产发布或破坏性操作。以上情况会给出精确的 `BLOCKED_*` 原因和所需授权。这样既实现日常零手工编排，也不虚假宣称可以安全地接管所有外部账号和未知软件。

### 运行阶段门禁

```bash
python3 scripts/validate_documents.py /path/to/project
python3 scripts/check_missing_modules.py /path/to/project
python3 scripts/check_traceability.py /path/to/project
python3 scripts/check_project_status.py /path/to/project --target READY_FOR_BUILD
```

进入 `READY_FOR_BUILD` 前，必须完成角色—页面、页面—功能、功能—状态、前台—后台、权限和验收矩阵。脚本校验结构与追踪关系，业务语义仍需由 Orchestrator 和独立 QA 审核。

### 切换行业

流程骨架可以复用，行业事实不能照搬。切换项目时保留 Skill，替换业务背景、术语、领域规则、状态机、权限、完整性适用性、架构与测试：

- 家政：服务者、地址、预约、派单、履约证据、取消、投诉、结算。
- 电商：SPU/SKU、库存、购物车、订单、优惠、支付、物流、退款、售后。
- CRM：租户、线索、客户/联系人、商机阶段、活动、归属、导入导出、数据范围。
- SaaS：组织、成员、套餐、权益、订阅、账单、计量、审计、租户隔离。
- AI Agent：模型/供应商、提示词和工具策略、知识检索、运行状态、人工审批、评测、成本和隐私。

### MCP 是可选能力

核心工作流不依赖 MCP。需要访问 GitHub、Figma、Browser/Playwright、Linear/Jira、Obsidian/文件、数据库或部署系统时，再按 Agent 的当前任务授予最小权限；生产写入、凭据、敏感数据、公开发布和不可逆操作仍需单独授权。详见 [`references/mcp-guide.md`](references/mcp-guide.md)。

### 验证 Skill

```bash
python3 -m unittest discover -s scripts/tests -v
```

更完整的安装、项目初始化、Agent 调整、门禁和行业迁移说明见 [`USAGE.md`](USAGE.md)。

---

## English

`software-project-orchestrator` is a reusable Codex Skill for governing software delivery from discovery to independent QA. It creates durable project memory, classifies work as Simple, Standard, or Complex, selects the smallest sufficient Agent team, routes each task to Luna, Terra or Sol with an explicit reasoning effort, safely resolves approved capabilities, enforces pre-build gates, and requires evidence before completion.

It is domain-neutral: reuse the workflow for CRM, e-commerce, SaaS, home services, AI agents, and other products while replacing the project-specific facts, rules, state machines, permissions, architecture, and tests.

### Quick start

Install the whole folder under `~/.agents/skills/software-project-orchestrator/` or `<repository>/.agents/skills/software-project-orchestrator/`, then invoke:

```text
$software-project-orchestrator initialize this project, collect the business context, classify complexity, and prepare the first approved task package.
```

Initialize from the command line:

```bash
python3 scripts/init_project.py /path/to/project \
  --project-name "Acme CRM" \
  --domain "CRM" \
  --complexity Standard
```

Run the build-readiness gates:

```bash
python3 scripts/validate_documents.py /path/to/project
python3 scripts/check_missing_modules.py /path/to/project
python3 scripts/check_traceability.py /path/to/project
python3 scripts/check_project_status.py /path/to/project --target READY_FOR_BUILD
```

See [`USAGE.md`](USAGE.md) for the complete guide and [`SKILL.md`](SKILL.md) for the orchestration contract.

## License

Released under the [MIT License](LICENSE).
