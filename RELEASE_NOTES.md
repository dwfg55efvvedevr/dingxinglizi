# Software Project Orchestrator v2.0.0

这是 `dingxinglizi` 的第二代正式版本。稳定调用名继续保持为 `$software-project-orchestrator`。

## 本版重点

- 新增统一控制入口 `scripts/orchestrator.py`，支持项目初始化、诊断、状态迁移、角色规划、运行记录、中断恢复、报告与评测。
- 角色按当前阶段和风险按需启用，不会仅因项目复杂就一次启动全部 Agent；开发与最终 QA 始终分离。
- 每个任务包可按任务性质路由 Luna、Terra、Sol 与思考强度，并对普通质量失败、权限/网络失败和高风险任务采用不同升级策略。
- 新增项目本地 run ledger、原子化检查点、输入指纹、证据索引、重复运行保护和确定性恢复结论。
- 新增电商、CRM、SaaS、拼团、AI Agent、家政六个领域包，以及 Simple、Standard、Complex 三套可运行示例。
- 强化 READY_FOR_BUILD、READY_FOR_QA 与 DONE 门禁；手工修改状态不能绕过完整验证。
- Skill/MCP 的文件准备与当前运行时真实可用性明确分离，未验证能力会阻塞而不是虚报可用。

## 质量证据

- 68 项自动化测试通过。
- 18 个角色、模型、失败升级和安全路由评测通过。
- Python 3.9、3.11、3.13 GitHub Actions CI 全部通过。
- 独立 QA 与 Quality Governor 最终结论均为 PASS，P0/P1 缺陷为 0。
- 官方 Skill 包校验、全新归档安装、文档链接与敏感信息扫描均通过。

## 安装

```bash
mkdir -p ~/.agents/skills
git clone --branch v2.0.0 https://github.com/lizi-product-studio/dingxinglizi.git \
  ~/.agents/skills/software-project-orchestrator
python3 "$HOME/.agents/skills/software-project-orchestrator/scripts/orchestrator.py" doctor
```

然后在 Codex 中调用：

```text
$software-project-orchestrator 初始化这个项目，收集业务背景，判断复杂度，只调用当前阶段必要角色，并在独立 QA 通过后才判定完成。
```

## 诚实边界

本地控制脚本不会直接创建或恢复 Codex Agent 会话，不会读取账户剩余额度、绕过认证、信任未知社区代码，或在未经确认时执行生产写入和不可逆操作。

完整说明见仓库的 `README.md`、`USAGE.md` 与 `CHANGELOG.md`。
