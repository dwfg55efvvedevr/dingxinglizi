# Software Project Orchestrator v2 — 使用手册

仓库名是 `dingxinglizi`，稳定 Skill 调用名是 `$software-project-orchestrator`。v2 提供统一命令入口，同时保留原有单功能脚本以兼容现有流程。

## 1. 安装与诊断

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/lizi-product-studio/dingxinglizi.git \
  ~/.agents/skills/software-project-orchestrator

export SPO_SKILL="$HOME/.agents/skills/software-project-orchestrator"
python3 "$SPO_SKILL/scripts/orchestrator.py" version
python3 "$SPO_SKILL/scripts/orchestrator.py" doctor
```

要求 Python 3.9+。Skill 的运行时核心不依赖第三方 Python 包。`doctor` 只检查，不会修改被诊断项目；首次 `run` 才创建项目的 run ledger。

当前官方 USER 级本地发现路径是 `~/.agents/skills`；项目专用 Skill 可放在仓库的 `.agents/skills/`。如果安装后未出现，重启 Codex。路径规则见 [OpenAI Build skills](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)。`doctor` 只验证包和项目合同，不证明宿主已加载 Skill；请以 Codex 的 Skill 列表或 `$software-project-orchestrator` 实际出现为准。

更新已安装版本：

```bash
git -C "$SPO_SKILL" pull --ff-only
python3 "$SPO_SKILL/scripts/orchestrator.py" doctor
```

## 2. 在 Codex 中调用

```text
$software-project-orchestrator 初始化这个项目，建立业务事实，判断复杂度，只调用当前阶段必要角色，并要求独立 QA 证据后才完成。
```

恢复已有项目：

```text
$software-project-orchestrator 检查这个项目上次运行记录，安全恢复；如果输入或路由变化则重新规划，不要重复启动不确定的 Agent。
```

Skill 可自动匹配 substantial 软件交付任务；如果环境中有多个相似 Skill，显式写出稳定调用名最可靠。

## 3. 初始化新项目

先预览：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" init /path/to/project \
  --project-name "Acme CRM" \
  --domain "CRM" \
  --complexity Standard \
  --domain-pack crm \
  --dry-run
```

确认后去掉 `--dry-run`。初始化器是非覆盖式的：任何目标合同文件已存在都会在写入前停止。已有仓库不要再次初始化，按第 11 节迁移。

可用领域包：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" domains list
python3 "$SPO_SKILL/scripts/orchestrator.py" domains inspect ecommerce
python3 "$SPO_SKILL/scripts/orchestrator.py" domains apply /path/to/project ecommerce --dry-run
python3 "$SPO_SKILL/scripts/orchestrator.py" domains apply /path/to/project ecommerce
```

领域包是候选清单，不是事实注入器。应用后审阅 `docs/domain-pack.md`，再把有证据的内容写入权威项目文档。

## 4. 建立唯一事实源

初始化后依次完善：

1. `docs/00-project-context.md`：目标、问题、商业模式、角色、对象、流程、状态机、规则、权限、资金、通知、后台运营、范围、限制、指标、未知问题；
2. `docs/01-domain-rules.md`：带 ID、来源、版本和可测试结果的领域规则；
3. `docs/02-glossary.md`：统一术语；
4. `docs/03-role-journey-matrix.md`：角色与旅程；
5. `docs/04-prd.md`：需求与验收意图；
6. `docs/05-state-permission-matrix.md`：对象状态、动作和权限；
7. `docs/06`–`10`：UX、设计系统、系统设计、API/数据契约、测试计划；
8. `docs/checklists/product-completeness.md`：每项 `REQUIRED / NOT_APPLICABLE / DEFERRED`，并记录覆盖状态。

事实只能标为 `CONFIRMED`、`EVIDENCE_INFERRED`、`DEFAULT_ASSUMPTION`、`NOT_APPLICABLE` 或 `BLOCKING_UNKNOWN`。聊天记录、领域包和行业惯例都不能自动升级为 `CONFIRMED`。

## 5. 诊断、路由与创建运行

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" doctor /path/to/project

python3 "$SPO_SKILL/scripts/orchestrator.py" transition /path/to/project \
  --target DISCOVERY

python3 "$SPO_SKILL/scripts/orchestrator.py" plan /path/to/project \
  --quota economy

python3 "$SPO_SKILL/scripts/orchestrator.py" plan /path/to/project \
  --quota economy --write

python3 "$SPO_SKILL/scripts/orchestrator.py" run /path/to/project
```

`transition` 会先校验门禁再原子写入状态，不能跨级跳转。先预览角色计划再 `--write`；省略 `--stage` 会自动使用已落盘的当前状态，避免计划与运行记录错位。`required_now` 是当前允许启动的角色，`execution_waves` 是顺序计划，`deferred_available` 不是启动许可。

额度模式：

- `economy`：默认最多 1 个活动子 Agent；
- `balanced`：最多 2 个，但只允许明确可并行的不同只读角色，或 Engineering Lead + 一个 Worker；
- `quality_first`：并发边界同 balanced，更积极启用独立质量挑战。

Complex 只代表完整职责在生命周期内可用，不代表现在启动全部角色。

## 6. 验证运行时模型并创建 Task Package

Orchestrator 必须从当前运行时获得真实模型信息，并更新：

```text
.codex/orchestration/runtime-inventory.json
```

至少记录 `status: VERIFIED`、精确模型 slug、`available_skills`、`available_mcp_servers`、验证时间和证据来源；能获得时同时记录 runtime/host/version。静态文档里的模型名、磁盘上的 Skill 目录或单独一段 MCP 配置都不构成运行时可用性证据。

创建 DRAFT 任务包：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" task /path/to/project \
  --task-id TASK-001 \
  --owner requirements \
  --reviewer product_auditor \
  --stage DISCOVERY \
  --task-type requirements \
  --objective "确认首个可交付版本的角色、对象、流程、规则和验收边界"
```

生成器会写入路由策略版本、当前 role-plan 指纹、输入指纹、模型/思考强度、失败升级记录和能力需求。它故意停在 `DRAFT`。

生成器会自动绑定当前唯一的 `OPEN` run。人工或 Orchestrator 必须补全：

- business context 和输入文档；
- scope / out_of_scope；
- deliverables；
- 可观察的 Given/When/Then/evidence 验收标准；
- 写任务的 allowed files；
- validation 与 evidence locations；
- 风险、依赖和 return target。

审阅完成后把顶层状态改为 `READY_FOR_DISPATCH`，不要手改自动生成的路由字段。

## 7. 能力解析与派发前检查

Agent 只声明能力需求；Orchestrator 统一解析：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" capabilities /path/to/project \
  --required github-read
```

默认是只读计划。只有项目信任策略允许的固定 commit、哈希匹配、许可允许、无需凭据、项目本地且权限不超限的候选，才可加 `--apply`。未知社区代码、浮动版本、安装脚本、OAuth、凭据、写权限、全局安装和生产访问必须阻塞或取得相应授权。

`--apply` 成功后返回 `PROVISIONED_PENDING_RUNTIME` 和阻塞退出码是正常现象：它只表示制品或配置已安全准备。Orchestrator 随后启动新 Agent 会话，从真实宿主核实能力发现情况，并更新 `runtime-inventory.json`。只有能力 ID 出现在相应的 `available_skills` 或 `available_mcp_servers` 列表里，结果才会变成 `SATISFIED`。用户不需要手动给每个角色装一遍，但系统也不会把“文件存在”伪装成“当前会话可调用”。

派发前：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" preflight /path/to/project \
  tasks/TASK-001.yaml \
  --available-model gpt-5.6-luna \
  --available-model gpt-5.6-terra \
  --available-model gpt-5.6-sol \
  --record-ready
```

只有 `READY` 加匹配的 dispatch receipt 才允许实际 Codex 运行时启动角色。CLI 负责合同和证据，不会自己创建 Agent 会话。

## 8. 模型路由与失败处理

不要在角色 TOML 中永久写死模型。每个 Task Package 独立路由：

- 低风险提取、扫描、机械任务优先 Luna；
- 常规分析、设计、实现优先 Terra；
- 架构、安全、权限、迁移、并发、高影响审查和复杂推理优先 Sol；
- 有效质量失败先提高 reasoning effort，再提高模型能力；
- 网络、auth、permission、missing input、tool unavailable 等环境失败不升级模型；
- 到达最大尝试次数返回阻塞；
- 高风险 Sol 下限不可用时失败关闭，不能静默降级。

运行时真正启动 Agent 时，必须显式使用任务包中的 `selected_model` 和 `model_reasoning_effort`。如果宿主不支持该组合，返回 Orchestrator 重路由或阻塞。

## 9. 完成一波并推进下一波

Owner 完成后：

1. 写入其拥有的交付物；
2. 在 Task Package handoff 中记录结论、输入、artifact、测试/截图/日志等证据、偏差和下游决定；
3. 把任务设为 `COMPLETED`；
4. Orchestrator 写入检查点；
5. 释放文件所有权并关闭该角色会话；
6. Orchestrator 用已验证完成包重新路由。

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" checkpoint /path/to/project \
  --event HANDOFF_PERSISTED \
  --task-id TASK-001 \
  --conclusion COMPLETE \
  --artifact docs/04-prd.md \
  --evidence evidence/AC-001.txt
```

Artifact/evidence 必须是项目内已存在的文件；路径逃逸会被拒绝。`TASK_BLOCKED` 必须写明阻塞原因，`RUN_COMPLETED` 只允许项目已经 `DONE`、没有活动任务/会话且独立 QA 结论为 `PASS` 或 `PASS_WITH_ACCEPTED_RISKS`。

示例：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" plan /path/to/project \
  --stage DISCOVERY \
  --quota economy \
  --completed-role requirements \
  --completed-task requirements=tasks/TASK-001.yaml \
  --write
```

Reviewer 只能在 Owner handoff 之后激活。开发自测是证据，不是独立验收。

## 10. 门禁、状态与完成

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" validate /path/to/project \
  --target READY_FOR_BUILD

python3 "$SPO_SKILL/scripts/orchestrator.py" status /path/to/project
```

`READY_FOR_BUILD` 至少要求角色—页面、页面—功能、功能—状态、前台—后台、权限和验收矩阵，以及适用的 Requirements/Product/UX/UI/Architecture 批准证据。

`DONE` 至少要求：所有适用验收有证据；必须测试通过；无未接受 P0/P1；项目文档反映真实行为；独立 QA 为 `PASS` 或获明确授权的 `PASS_WITH_ACCEPTED_RISKS`；公开发布/生产部署等外部动作拥有单独授权。

缺陷按源头打回：业务规则→Requirements；漏页面/功能/状态/后台→Product Auditor；流程→UX；视觉/文案→UI；API/数据/权限设计→Architect；实现→Engineering Lead；测试不足→QA。

## 11. 中断恢复与 v1.x 迁移

中断后先恢复，不要直接新建 run：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" doctor /path/to/project
python3 "$SPO_SKILL/scripts/orchestrator.py" resume /path/to/project
python3 "$SPO_SKILL/scripts/orchestrator.py" report /path/to/project
```

可能结果：

- `RESUME_SAFE`：输入和路由未变，可从检查点继续；
- `REPLAN_REQUIRED`：项目输入或 route fingerprint 变化；
- `RECONCILIATION_REQUIRED`：仍有不确定活动会话，禁止启动重复角色；
- `BLOCKED`：核心证据缺失或损坏；
- `DONE`：读取/生成报告即可。

现有 v1.x 项目不要覆盖式初始化。先备份/提交，再安装 v2、运行 doctor，并按 [references/migration.md](references/migration.md) 合并缺失合同。内部路由策略版本与产品版本独立，不要为了显示 v2 而机械修改未变化的 policy version。

## 12. 切换行业

保留流程，替换业务事实层：目标、术语、对象、生命周期、规则、权限、完整性适用性、架构、测试和风险。

- 家政：服务者、地址、预约、派单、履约证据、取消、投诉、结算；
- 电商：SPU/SKU、库存、购物车、订单、优惠、支付、物流、退款、售后；
- CRM：租户、线索、客户/联系人、商机、活动、归属、数据范围、导入导出；
- SaaS：组织、成员、套餐、权益、订阅、账单、计量、审计、租户隔离；
- 拼团：团、成团条件、库存锁定、支付、失败退款、履约、团长/自提点；
- AI Agent：模型/供应商、提示词、工具、知识检索、审批、运行状态、评测、成本、隐私。

## 13. 自检与贡献

```bash
SPO_SKILL="${SPO_SKILL:-$HOME/.agents/skills/software-project-orchestrator}"

python3 -m py_compile "$SPO_SKILL/scripts/"*.py
python3 -m unittest discover -s "$SPO_SKILL/scripts/tests" -v
python3 "$SPO_SKILL/scripts/orchestrator.py" eval
python3 "$SPO_SKILL/scripts/orchestrator.py" doctor
```

修改角色或模型路由、恢复状态、Task Package 合同或领域包后，必须补测试/评测。离线 eval 只证明确定性控制规则，不证明真实项目质量。

## 14. 命令索引

```text
orchestrator.py version
orchestrator.py doctor [PROJECT]
orchestrator.py init PROJECT ...
orchestrator.py plan PROJECT ...
orchestrator.py run PROJECT
orchestrator.py checkpoint PROJECT ...
orchestrator.py resume PROJECT [--run-id RUN]
orchestrator.py report PROJECT [--run-id RUN]
orchestrator.py validate PROJECT [--target STATE]
orchestrator.py status PROJECT [--target STATE]
orchestrator.py transition PROJECT --target STATE
orchestrator.py task PROJECT ...
orchestrator.py preflight PROJECT TASK ...
orchestrator.py capabilities PROJECT ...
orchestrator.py eval [--suite FILE]
orchestrator.py domains list|inspect|apply ...
```

每个子命令支持 `--help`。
