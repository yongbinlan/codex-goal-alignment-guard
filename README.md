# Goal Alignment Guard · 全过程目标对齐

A lightweight agent skill for aligning goals before work, rechecking consequential changes, and verifying alignment before delivery.

让 Agent 围绕**当前目标**工作，而不是只抓最后一句话的关键词。实质性任务从开始就核对目标、模式、修改边界及验收条件，不等出错才触发；关键变化时复核，交付前对照结果。普通明确的小任务轻量处理，不增加仪式感。

**不是自动拦截器，不保证零错误，也没有经过实测的返工降低百分比。** 它补充专业技能和结果验收，不取代它们。

## 直接安装到 Codex

把下面这一句发给 Codex（需要可用的 `skill-installer`）：

```text
使用 $skill-installer 安装 https://github.com/yongbinlan/codex-goal-alignment-guard/tree/main/skills/goal-alignment-guard
```

安装后在下一轮检查技能是否可见；若没有出现，重新启动当前 Codex 会话并确认宿主的技能发现配置。不同版本的发现目录可能不同，不要通过修改其他 Agent 的目录来绕过隔离规则。

显式使用：

```text
使用 $goal-alignment-guard，开始前核对目标、修改边界和验收条件，关键变化时复核，交付前检查结果。目标清楚就直接执行，只有实质性歧义才问我。
```

标准目录内包含 `SKILL.md` 和 `agents/openai.yaml`；不依赖 API Key、第三方服务或模型调用脚本。其他兼容 Agent Skills 的宿主可按其安装方式使用，尚未逐个平台验证。

## 希望跨任务进行轻量检查？再启用全局规则

**全局可安装 ≠ 每次必然自动调用。** 技能按需加载；基础检查和实质性任务的前置调用规则可以经授权加入 Codex 的全局 `AGENTS.md`。不默认篡改你的全局设置。检查不等于提问：目标明确且授权充足时直接执行。

推荐直接把下面这段发给 Codex：

```text
安装上述 goal-alignment-guard 技能后，检查当前 Codex 全局指令及覆盖关系。
我授权你备份并把该技能 references/global-anchor.md 的通用检查规则合并到全局 AGENTS.md，保留全部其他规则。
先预览 scripts/global_anchor.py 的变更，再使用 --apply 写入并回读验证。
如存在冲突、有效 AGENTS.override.md 或非标准配置位置，先反馈，不自动绕过。
不要把我的任务内容、私人对话或业务资料写入全局规则。
```

手动使用脚本需要 Python 3.10+。在**已安装的技能文件夹**内运行：

```sh
python scripts/global_anchor.py                 # 只预览，不写入
python scripts/global_anchor.py --apply         # 明确同意后应用
python scripts/global_anchor.py --remove        # 预览移除该技能的规则块
python scripts/global_anchor.py --remove --apply
```

脚本使用现有 `CODEX_HOME`，未配置时使用当前用户的 `.codex`；空白值会被拒绝，不把工作目录误当配置目录。可用 `--codex-home` 显式指定已存在的配置目录；不会自动创建配置目录，不改写环境变量。写入前备份、重复执行不重复追加；遇到非空 `AGENTS.override.md`、链接路径或损坏标记时停止。移除只触及受管规则块，不删除技能或其他规则。备份可能包含原有私人配置，留在本地，不要上传。

备份在 POSIX 上以 `0600` 创建；Windows 文件使用所在目录的继承 ACL，不保证复制原文件的自定义 ACL。若使用自定义文件权限，应由管理员用系统工具备份和合并。应用期间不要同时编辑全局规则：脚本会检查并发变更，但不是跨进程锁。

更新全局规则后建议开启新会话，核对实际加载情况。项目规则、覆盖文件及上下文长度限制仍可能影响有效指令；不能只凭文件存在宣称已强制生效。

## 它具体处理什么

| 情况 | 应有行为 |
|---|---|
| 首次收到实质性任务，尚无错误 | 先核对结果、任务模式、边界及验收，再选择方案 |
| 进入执行、采用替代方案或准备交付 | 复核受影响的约束和证据，不重复完整问卷 |
| 仅改变描述方式 | 保留未被修改的目标与工作模式 |
| 明确改变目标 | 跟随新目标，不死守旧要求 |
| 术语有歧义且影响交付 | 问一个具体问题，不带着免责声明交付错误版本 |
| 用户只要求诊断 | 不擅自修改、发布或花费 |
| Agent 自己的输出有矛盾 | 自行修正并交付合并后的完整版本 |
| 信息不足以证明原因 | 区分证据、假设和待验证事项 |
| 简单改字或明确小任务 | 直接完成，不强制目标表或追问 |

## 价值、证据与限制

见 [实用价值评估](docs/VALUE.md)、[验证记录](docs/VALIDATION.md) 和 [公开合成案例](evals/cases.json)。案例不含真实客户素材或私人对话。

目标是减少**可避免的范围偏差**。不能保证外部生成模型遵循提示词，也不能证明媒体、代码或业务结果合格。真实返工率、额外追问率和时间成本需要后续使用数据，不能从几条通过的测试推导出来。

## 本地测试

已有 v0.1.0 用户更新技能后，如曾启用全局规则，也需在授权范围内预览并重新应用配置助手；仅更新技能文件不会自动改写旧的全局区块。v0.1.0 标签保留不动，便于回退。

从仓库根目录运行：

```sh
python -m unittest discover -s tests -v
```

测试覆盖配置助手的预览、备份、幂等、移除及拒绝危险输入；不是语义理解测试。评估行为需另行使用 `evals/cases.json`，按 `evals/RUBRIC.md` 人工审核实际回答。

## 隐私与授权

技能本身不联网、不收集遥测、不创建长期记忆，不自动修改文件或提交付费任务。任务目标默认只留在当前会话；更改全局规则必须单独授权。

MIT License。欢迎复用、修改、提交问题；本项目并非 OpenAI 官方技能。

参考：[官方 Skills 文档](https://learn.chatgpt.com/docs/build-skills) · [官方全局指令文档](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
