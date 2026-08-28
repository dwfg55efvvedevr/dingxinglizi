# Software Project Orchestrator v3.0 — 使用手册

仓库名是 `dingxinglizi`，稳定 Skill 调用名是 `$software-project-orchestrator`。v3 将项目事实与编排状态平台中立化，并为 Codex、Cursor、Claude Code、OpenCode 生成各自原生配置。

## 1. 检测和安装

要求 Python 3.9+。先克隆仓库并检测本机宿主：

```bash
git clone https://github.com/lizi-product-studio/dingxinglizi.git /tmp/dingxinglizi
export SPO_SKILL=/tmp/dingxinglizi
python3 "$SPO_SKILL/scripts/orchestrator.py" version
python3 "$SPO_SKILL/scripts/orchestrator.py" platform detect
```

`detect` 只执行 PATH 查找和 `<executable> --version`，不认证账户，也不猜模型库存。若检测到多个宿主，显式选择一个。

用户级安装默认只预览：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" platform install --platform cursor --scope user
python3 "$SPO_SKILL/scripts/orchestrator.py" platform install --platform cursor --scope user --apply
```

OpenCode 的 V1/V2 原生权限格式不同。若本机版本可由 `opencode --version` 明确识别，默认 `auto` 会选择对应格式；离线生成或版本未知时要显式选择：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" platform install --platform opencode \
  --scope user --opencode-schema v2
python3 "$SPO_SKILL/scripts/orchestrator.py" platform install --platform opencode \
  --scope user --opencode-schema v2 --apply
```

V1 改为 `--opencode-schema v1`。未来未知主版本不会被当成 V2，命令会先阻塞，等待适配器核验更新。

项目级安装需要目标目录：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" platform install /path/to/project \
  --platform claude-code --scope project
python3 "$SPO_SKILL/scripts/orchestrator.py" platform install /path/to/project \
  --platform claude-code --scope project --apply
```

安装器特性：

- 一次只生成所选平台；
- 默认不写，`--apply` 才写；
- 默认不覆盖，`--update` 才更新不同内容；
- 冲突时整体停止，不做部分安装；
- 拒绝平台目录中的符号链接路径；
- 不联网、不登录、不读凭据、不调用包管理器。

更新 Git 克隆版可用 `git pull --ff-only`。非 Git 安装可重新执行源仓库中的 `platform install ... --apply --update`，先保留备份并查看预览。

## 2. 在 Agent 宿主中调用

```text
$software-project-orchestrator 初始化这个项目，建立唯一业务事实源，判断复杂度，只调用当前阶段最少必要角色，质疑未经证实的需求，并要求独立 QA 后才完成。
```

如果宿主没有自动列出 Skill，重启宿主并用 `platform doctor` 检查结构。结构可用不等于宿主已经在当前会话加载它。

## 3. 初始化新项目

先预览：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" init /path/to/project \
  --project-name "Acme CRM" \
  --domain "CRM" \
  --complexity Standard \
  --platform cursor \
  --domain-pack crm \
  --dry-run
```

初始化 OpenCode 项目时同样追加 `--opencode-schema v1|v2`；只有已安装版本可明确识别时才可依赖默认 `auto`。

确认后去掉 `--dry-run`。初始化器非覆盖式；任一合同文件存在都会在写入前停止。`--platform auto` 只在恰好发现一个宿主时自动选择；发现多个时要求显式选择。一个都未发现时会生成向后兼容的 Codex 配置并警告，但不会声称 Codex 已安装。

新项目结构：

```text
project/
├── AGENTS.md
├── docs/
├── tasks/
├── evidence/
├── .dingxinglizi/
│   ├── orchestration/
│   ├── runs/
│   └── evolution/
└── <selected-host>/agents/
```

其中 `<selected-host>` 是 `.codex`、`.cursor`、`.claude` 或 `.opencode`。宿主配置不是业务事实源。

## 4. 建立唯一事实源

依次完善：

1. `docs/00-project-context.md`：目标、问题、商业模式、角色、对象、流程、状态机、规则、权限、资金、通知、后台、范围、限制、指标、未知；
2. `docs/01-domain-rules.md`：带 ID、来源、版本和可测试结果的领域规则；
3. `docs/02-glossary.md`：统一术语；
4. `docs/03-role-journey-matrix.md`：角色—页面、页面—功能、前台—后台矩阵；
5. `docs/04-prd.md`：需求与验收意图；
6. `docs/05-state-permission-matrix.md`：功能—状态、对象动作与权限；
7. `docs/06`–`10`：UX、设计系统、系统设计、API/数据契约、测试计划；
8. `docs/checklists/product-completeness.md`：每项标记 `REQUIRED / NOT_APPLICABLE / DEFERRED`。

事实只能标为 `CONFIRMED`、`EVIDENCE_INFERRED`、`DEFAULT_ASSUMPTION`、`NOT_APPLICABLE` 或 `BLOCKING_UNKNOWN`。聊天、行业包、用户措辞和模型常识都不能自动升级为 `CONFIRMED`。

## 5. 诊断、生命周期和按需角色

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" doctor /path/to/project
python3 "$SPO_SKILL/scripts/orchestrator.py" transition /path/to/project --target DISCOVERY
python3 "$SPO_SKILL/scripts/orchestrator.py" plan /path/to/project --quota economy
python3 "$SPO_SKILL/scripts/orchestrator.py" plan /path/to/project --quota economy --write
python3 "$SPO_SKILL/scripts/orchestrator.py" run /path/to/project
```

`required_now` 才是当前允许启动的角色；`execution_waves` 是顺序计划；`deferred_available` 不是启动许可。

- `economy`：最多 1 个活动子 Agent；
- `balanced`：最多 2 个，仅限明确独立读任务或 Engineering Lead + 一个 Worker；
- `quality_first`：并发边界相同，更积极触发独立质量挑战。

只有 Orchestrator 管理专业角色；Engineering Lead 只管理实现 Worker；Worker 不得继续委派；Engineering Lead 与最终 QA 不同时执行。

## 6. 运行时模型证据

v3 Task Package 请求逻辑能力档，具体模型从 `.dingxinglizi/orchestration/runtime-manifest.json` 解析。准备模型库存文件：

```json
{
  "models": [
    {
      "id": "vendor/model-a",
      "provider": "vendor",
      "capability_tier": "ADVANCED",
      "reasoning_efforts": ["medium", "high"]
    },
    {
      "id": "vendor/model-b",
      "provider": "vendor",
      "capability_tier": "EXPERT",
      "reasoning_efforts": ["high", "xhigh"]
    }
  ]
}
```

捕获清单：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" platform runtime-manifest \
  --platform opencode \
  --project-dir /path/to/project \
  --models-file /path/to/models.json \
  --models-verified \
  --evidence-source "OpenCode provider model list checked 2026-08-28"
```

不加 `--update` 不会覆盖现有清单。`--models-verified` 必须同时提供文件和命名证据来源。原始库存文件必须保留为普通单链接文件；派发前会重新验证 SHA-256、规范化模型字段、当前 executable/version 和 24 小时时效。它仍不证明真实执行。

单独验证解析：

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" platform model-resolve \
  /path/to/project/.dingxinglizi/orchestration/runtime-manifest.json \
  --tier EXPERT --reasoning high --risk-level high --risk security
```

高风险下，运行时和模型库存都必须验证，模型必须满足或高于能力下限并支持请求的 reasoning。无证据就阻塞，不静默降级。策略 `2.0.0` 不允许用 Task/Preflight 的 `--available-model` 参数绕过清单验证；该参数仅保留给仍使用策略 `1.2.0` 的 v2 兼容项目。缺少 manifest 时任务仍可保存为草稿，但平台、供应商和模型保持未解析，派发前检查必定阻塞。

## 7. Task Package 与派发前检查

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" task /path/to/project \
  --task-id TASK-001 \
  --owner requirements \
  --reviewer product_auditor \
  --stage DISCOVERY \
  --task-type requirements \
  --objective "确认首个可交付版本的角色、对象、流程、规则和验收边界"
```

生成器故意写成 `DRAFT`。必须人工或由 Orchestrator 补全 business context、输入文档、scope、out of scope、deliverables、Given/When/Then/evidence 验收、allowed files、validation、evidence locations、风险、依赖和 return target，再改为 `READY_FOR_DISPATCH`。

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" preflight /path/to/project \
  tasks/TASK-001.yaml --record-ready
```

preflight 会重新计算角色计划、输入指纹、模型解析和能力状态。CLI 生成 READY receipt，但实际宿主启动后仍需记录真实 provider/model/reasoning/runtime 的 execution receipt；模板在 `assets/platforms/common/execution-receipt.template.json`。

## 8. 平台兼容等级

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" platform doctor /path/to/project \
  --platform cursor --scope project \
  --manifest /path/to/project/.dingxinglizi/orchestration/runtime-manifest.json
```

诊断 OpenCode 离线安装时也应传与生成时相同的 `--opencode-schema v1|v2`，否则无法从运行时确认 schema 时会拒绝比较。

- L1：Skill 可发现；
- L2：portable core 可用；
- L3：原生 profiles、宿主 executable、已验证模型库存可用；
- L4：本地 native execution 声明通过精确 schema、SHA-256 指纹以及 provider/model/reasoning/runtime 清单一致性检查。

只生成 profile 不能升级为 L4。L4 也是无签名本地声明，不是独立第三方或密码学执行证明；拥有完整本地写权限的人可以协调重写相关文件。

Doctor 默认用于诊断，达到 L1 即返回成功。CI 或发布门禁必须追加 `--require-level L2|L3|L4`；实际等级低于目标时返回退出码 3。OpenCode 的只读审查角色同时禁用 edit 与 V1 bash/V2 shell；需要执行命令的测试交给写入权分离的 Test Worker，再由 QA 读取证据。

## 9. 能力与 MCP

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" capabilities /path/to/project \
  --required github-read
```

默认只规划。`--apply` 只允许：

- allowlist 仓库；
- 固定 40 位 commit；
- 匹配 archive SHA-256；
- 允许的许可证；
- 无可执行代码；
- 项目本地安装；
- 权限不超过策略。

安全准备后的 Skill 会放入当前平台的项目 Skill 目录，但仍返回 `PROVISIONED_PENDING_RUNTIME`，直到新宿主会话证明发现它。

Codex 可自动管理无凭据、只读 HTTPS MCP 的受管配置块。其他三个平台当前不自动写 MCP 配置；请使用宿主官方配置/授权流程，再把真实发现结果写入运行时清单。OAuth、API key、私有服务、STDIO 包、写权限、数据库凭据和部署访问保持阻塞，除非获得单独授权并使用宿主支持的流程。

## 10. 中断恢复

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" checkpoint /path/to/project \
  --event HANDOFF_PERSISTED --task-id TASK-001 \
  --artifact docs/04-prd.md --evidence evidence/TASK-001-review.md
python3 "$SPO_SKILL/scripts/orchestrator.py" resume /path/to/project
python3 "$SPO_SKILL/scripts/orchestrator.py" report /path/to/project
```

恢复结论只有 `RESUME_SAFE`、`REPLAN_REQUIRED`、`RECONCILIATION_REQUIRED`、`BLOCKED`、`DONE`。工具不会假设一个中断 Agent 还活着，也不会静默清理不确定会话。

## 11. 从 v2 迁移

v2 项目无需迁移就能继续使用；只要 `.dingxinglizi/` 不存在，控制层会整体选择旧 `.codex` 状态，绝不混读。

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" migrate /path/to/v2-project
python3 "$SPO_SKILL/scripts/orchestrator.py" migrate /path/to/v2-project --apply
```

迁移是原子、非破坏复制。若还要复制 Evolution：先把 `.dingxinglizi/evolution/` 加到有效 `.gitignore` 并确认未跟踪，再加 `--include-evolution`。迁移后的项目仍保留复制来的模型策略 `1.2.0`；迁移命令不执行策略升级，也不自动启用跨供应商路由。不要在没有备份和核验时删除旧 `.codex`。

## 12. 领域切换

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" domains list
python3 "$SPO_SKILL/scripts/orchestrator.py" domains inspect ecommerce
python3 "$SPO_SKILL/scripts/orchestrator.py" domains apply /path/to/project ecommerce --dry-run
python3 "$SPO_SKILL/scripts/orchestrator.py" domains apply /path/to/project ecommerce
```

从家政切到电商、CRM、SaaS 或 AI Agent 时，不换主流程；更换/审阅领域候选，更新项目事实、对象、状态机、权限、资金、运营、合规和验收。领域包不会自动覆盖已有事实或锁。

## 13. 受监督改进

```bash
python3 "$SPO_SKILL/scripts/orchestrator.py" evolution init /path/to/project
python3 "$SPO_SKILL/scripts/orchestrator.py" evolution collect /path/to/project --run-id RUN-ID
python3 "$SPO_SKILL/scripts/orchestrator.py" evolution retrospect /path/to/project
python3 "$SPO_SKILL/scripts/orchestrator.py" evolution propose /path/to/project --retrospective RET-ID.json
python3 "$SPO_SKILL/scripts/orchestrator.py" evolution eval-candidates /path/to/project --proposal PRP-ID.json
```

Evolution 数据位于当前有效控制目录的 `evolution/`。候选始终 `DRAFT + REVIEW_REQUIRED`，不能自动改 Skill、项目事实、正式 eval、保护门禁、Git 或外部系统。

## 14. 完整验证

```bash
python3 -m py_compile "$SPO_SKILL"/scripts/*.py
python3 -m unittest discover -s "$SPO_SKILL/scripts/tests" -v
python3 "$SPO_SKILL/scripts/orchestrator.py" eval
python3 "$SPO_SKILL/scripts/orchestrator.py" doctor
```

发布包中的四平台配置经过静态/合同测试，不代表所有宿主都在当前机器完成真实会话验证。以 `platform doctor` 返回等级和对应证据为准。
