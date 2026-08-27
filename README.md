# dingxinglizi

> Codex Software Project Orchestrator

[中文](#中文介绍) · [English](#english)

## 中文介绍

`dingxinglizi` 是一套面向 Codex 的通用软件项目交付 Skill；稳定调用名为 `$software-project-orchestrator`。它把需求、产品完整性、UX、UI、架构、开发和独立 QA 串成一条可验证的交付流程。1.2 版会先按“当前阶段”只唤醒最小必要角色，再按“每个任务包”选择 Luna、Terra 或 Sol 及思考强度，并在安全边界内准备所需 Skill/MCP。

它适用于从简单内部工具，到 CRM、电商、SaaS、家政平台、AI Agent 等跨行业项目。业务事实保存在项目文档中，不依赖聊天 Session 记忆；外部 MCP/连接器是可选增强能力，不是运行前提。

### 它解决什么问题

- 在开发前补齐业务背景、角色、页面、功能、状态、权限和验收标准。
- 按 `Simple / Standard / Complex` 自动选择 Agent 组合，避免小项目过度编排、复杂项目角色缺失。
- 角色配置全部随 Skill 安装，但默认一次只运行 1 个子 Agent；只有显式独立的只读任务才允许并行 2 个。Complex 也不会一次启动全员。
- 根据角色、复杂度、任务类型、风险和失败记录，稳定路由 `gpt-5.6-luna`、`gpt-5.6-terra` 或 `gpt-5.6-sol`，无需用户逐个 Agent 配模型。
- 普通质量失败先提升思考强度，再提升模型档位；网络、权限、缺上下文等非推理失败不会浪费额度升级模型。
- 自动复用已安装能力；对项目白名单中固定 commit、哈希校验、许可允许、无需凭据的 Skill/MCP 可自动准备。
- 保持一个全局 Orchestrator，禁止 Agent 网状互相管理。
- 通过阶段门禁阻止“需求没定就开写”“开发完成就自称验收通过”。
- 用标准 Task Package 限定目标、范围、文件所有权、交付物和返回路径。
- 将缺陷打回真正的责任源头，而不是把所有问题都交给开发修补。
- 用独立 QA、测试、截图、日志等证据判定项目是否真正完成。
- 用按需 `quality_governor` 对抗审查问题是否真实、方案因果是否成立、发布证据是否支持结论。
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

可用专业角色为：

`orchestrator`、`requirements`、`product_auditor`、`ux`、`ui`、`architect`、`engineering_lead`、`qa`，以及按需只读的 `quality_governor`。

按需可以增加 `frontend_worker`、`backend_worker`、`ai_worker`、`data_worker`、`test_worker`。Worker 只能由 Engineering Lead 调度，且不能继续创建下级 Agent。所有复杂度下，开发和最终 QA 必须分离。

配置文件存在不等于角色已经启动。Orchestrator 始终留在主线程，Role Router 只为当前关卡生成 `required_now` 和顺序 `execution_waves`；角色交付完成后退出活动集，后续阶段通过项目文档继续。

### 安装

复制或链接整个目录，不要只复制 `SKILL.md`：

```bash
# 直接从 GitHub 安装到个人 Skill 目录
mkdir -p ~/.agents/skills
git clone https://github.com/dwfg55efvvedevr/software-project-orchestrator.git \
  ~/.agents/skills/software-project-orchestrator

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

希望优先节省额度时，可以直接这样说：

```text
$software-project-orchestrator 用 economy 模式推进，只调用当前阶段必要角色；先给我 role plan，再执行，不要一次启动全部角色。
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

### 复杂度与按需 Agent 路由

| 级别 | 整个生命周期可用职责 | 当前调用方式 |
|---|---|---|
| Simple | 合并的需求/产品、工程、独立 QA；必要时设计/架构 | 默认每阶段 0–1 个子 Agent |
| Standard | 需求、产品、设计、技术、独立 QA | 每阶段最小角色；通常 1 个，安全只读时最多 2 个 |
| Complex | 全部专业职责和必要 Worker 在生命周期内可用 | 仍按关卡逐个/分波次激活，不一次全开 |

角色可以合并，但职责不能消失；独立最终 QA 不能与开发合并。

预览不会启动任何 Agent；确认后加 `--write` 写入当前计划：

```bash
python3 scripts/route_roles.py /path/to/project --stage DISCOVERY --quota economy
python3 scripts/route_roles.py /path/to/project --stage DISCOVERY --quota economy --write
```

`economy` 默认最多 1 个子 Agent；`balanced` 和 `quality_first` 最多 2 个，并且只有显式 `parallel_safe` 的独立只读任务能进入同一波次。Reviewer 等 Owner 交付后再调用；批准输入指纹未变化时复用质量结论，不重复启动审查角色。

`required_now` 只表示当前第一个未完成波次；`deferred_sequence` 只是后续预告。当前角色把交付物和 handoff 写入任务包、将其标记为 `COMPLETED` 并退出后，Orchestrator 使用 `--completed-role ROLE --completed-task ROLE=tasks/TASK.yaml --write` 对同一阶段重新路由。路由器会核对任务 owner、阶段、上一份计划指纹、派发 READY 凭证、模型/能力路由、成功结论和真实本地证据，下一波才获得启动许可。`--write` 还会同步项目状态里的额度模式和最大活动数，切到更小额度前必须先关闭超额会话。

多波次的完成角色会在同一个 `routing_cycle_id` 中累计；例如 Requirements 完成后调用 Quality Governor，Quality Governor 完成后本关卡清空，不会重新回到 Requirements。带完成证明推进时，阶段、复杂度、额度模式和 signals 必须与当前周期完全一致；主动改变这些输入会开启新周期并清空旧完成记录。

一个活动角色只能对应一个活动任务；即使 `balanced` 还有空槽，也不能重复启动第二个 Requirements、Architect 或 Engineering Lead。第二槽只用于路由器明确生成的不同只读角色，或 Engineering Lead + 1 个受控 Worker。

开发阶段如确需 Worker，使用 `balanced/quality_first + --signal implementation_workers`。计划会允许 Engineering Lead 同时带 1 个受限 Worker；`economy` 下 Engineering Lead 直接实现，避免父 Agent + Worker 超过 1 个活动槽位。

Skill 能确定性减少和阻止不必要的角色调度，但不能读取、预留或保证宿主账户的剩余额度；实际用量仍由 Codex 运行时和被启动的任务决定。

### 产品思维与质量责任

三道质量子门禁不会被省略，但独立角色是按需的：Problem Quality 在需求批准前、Solution Challenge 在开发前、Release Evidence 在发布准备前。Simple 低风险项目可由 Orchestrator 按清单内联完成；Complex、`quality_first` 或证据冲突/高影响/安全等信号会调用独立只读 Quality Governor。

产品理论采用“核心问题 + 按需透镜”：JTBD、Opportunity Solution Tree、Service Blueprint、价值主张、第一性原理、指标护栏和 Responsible Product 只在会改变决策时选 1–2 个，不要求用户先配置。

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

生成器始终创建 `status: DRAFT`，不会直接启动角色。先填写具体的 `business_context.value`、`input_documents`、`scope`、`deliverables`、带 Given/When/Then/证据的 `AC-*`、写任务的 `allowed_files`，以及命令或人工验证；Quality Governor 任务还要填写独立审查字段。Orchestrator 审核后把顶层状态改为 `READY_FOR_DISPATCH`，再用 `--record-ready` 运行下面的执行预检。若合同、角色、模型、运行时或能力仍有缺口，预检会返回 `BLOCKED_*` 且不生成凭证；只有产生 `evidence/dispatch/TASK-ID.ready.json` 并报告 `READY` 才能启动。

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
  --record-ready \
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

`software-project-orchestrator` is a reusable Codex Skill for governing software delivery from discovery to independent QA. It installs a complete role library but activates only the current gate's minimum role set, defaults to one spawned Agent, keeps final QA independent, routes each task to Luna, Terra or Sol, and adds on-demand adversarial problem/solution/release evidence review.

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
