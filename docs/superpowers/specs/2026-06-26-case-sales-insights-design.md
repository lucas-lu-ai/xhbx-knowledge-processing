# 案例级销售策略与销售话术提取方案

## 1. 背景

当前项目负责将保险绩优案例素材解析、研判、整理为可向量化的 Markdown 知识单元，并输出
`meta.json` 与 `provenance.json`。这些产物适合支撑通用问答、课程推荐、组卷和剧本陪练，
但对“销售策略”和“销售话术”的支持还不够精细。

销售策略通常贯穿完整案例，而不是只存在于某一节。例如一个案例可能从售前触达、需求面谈、
异议处理到促成成交，连续体现同一套方法论。销售话术也依赖上下文：同一句话术在售前吸引、
需求挖掘、异议处理或促成环节的作用不同。因此新增能力应以“案例级整合”为主，而不是只按
单节孤立提取。

## 2. 目标

新增一条销售洞察提取链路，用于从完整绩优案例中提取可被 AI 教练调用的销售策略、销售话术、
异议处理和客户旅程信息。

目标包括：

- 从完整案例视角识别贯穿多节的销售策略与执行路径。
- 保留单节证据，确保每条策略、话术、异议处理建议都能回溯到原始素材或整理稿。
- 将话术按销售阶段、客户状态、使用场景、目标和合规边界结构化。
- 支持下游 AI 教练按“阶段 / 场景 / 异议 / 策略名称”检索并生成回答。
- 为全库策略归并预留结构，例如将多个案例中的相似方法统一归入“5S销售法”“风险唤醒”等策略目录。

## 3. 非目标

本方案不直接实现 embedding、向量库写入或线上 AI 教练问答服务。

本方案也不把销售策略强行归类到未经业务确认的固定方法论中。模型可以识别“疑似体现某策略”，
但需要标记 `inferred=true` 与置信度，避免把个案经验包装成已确认的公司标准打法。

## 4. 核心设计结论

推荐采用“三层提取”：

1. 节级证据采集：从每节素材或整理稿中抽取原始话术、客户信号、销售动作、异议、转折点。
2. 案例级销售洞察：整合一个案例下所有节级证据，提炼完整客户旅程、策略路径和场景化话术。
3. 全库策略归并：在多个案例产物基础上合并相似策略，形成可复用的策略目录与话术库。

不要直接让一个 agent 对整案原文做一次性总结。整案上下文很重要，但直接长文本总结容易丢失
细节、弱化话术原文、难以溯源。更稳妥的方式是“节级证据保真 + 案例级归纳抽象”。

## 5. 现有系统接入点

现有流水线如下：

```text
SourceGroup
  -> RawSection
  -> 视觉增强
  -> AssessorAgent
  -> ExtractorAgent
  -> ReviewerAgent / ReviserAgent
  -> write_section_output
  -> <节>.md / <节>.meta.json / <节>.provenance.json
```

新增链路建议接在 `<节>.md` 与 `<节>.provenance.json` 写出之后：

```text
每节标准产物
  -> SectionSalesEvidenceAgent
  -> <节>.sales_evidence.json
同一案例下所有 sales_evidence
  -> CaseSalesInsightAgent
  -> case.sales_insights.json
  -> case.sales_playbook.md
全库 case.sales_insights
  -> StrategyNormalizerAgent
  -> sales_playbook/strategies.jsonl
  -> sales_playbook/scripts.jsonl
  -> sales_playbook/objections.jsonl
```

这样可以保持当前主链路稳定，同时把销售洞察作为新的 sidecar 产物扩展。

## 6. 数据粒度

### 6.1 节级证据

节级证据只负责“采集可复用证据”，不做过度抽象。它回答：

- 这一节出现了哪些客户背景或客户信号？
- 销售人员采取了哪些动作？
- 出现了哪些原始话术？
- 客户有哪些异议、犹豫或决策障碍？
- 哪些表达可能支撑后续总结为策略？

节级证据的价值在于保真和溯源，不在于生成漂亮的方法论。

### 6.2 案例级洞察

案例级洞察负责把一个案例下的所有节级证据串起来，形成完整销售链路。它回答：

- 这个案例整体的客户旅程是什么？
- 销售人员在不同阶段的目标、动作、话术分别是什么？
- 哪些动作体现了可复用销售策略？
- 话术适用于什么场景，不适用于什么场景？
- 有哪些异议处理模式和促成节点？

### 6.3 全库策略目录

全库策略目录负责归并多个案例中重复出现或高度相似的策略。它回答：

- 哪些案例都体现了同一销售方法？
- 同一策略有哪些别名和表达方式？
- 该策略适合哪些阶段、客户状态和销售目标？
- 哪些话术是该策略下的代表话术？

## 7. Agent 设计

### 7.1 SectionSalesEvidenceAgent

职责：从单节整理稿和来源引用中抽取销售证据。

输入：

- `RawSection` 或已写出的 `<节>.md`
- `<节>.provenance.json`
- `<节>.meta.json`

输出：

- `<节>.sales_evidence.json`

关键约束：

- 优先保留素材中真实出现的话术原文。
- 不把个案背景直接泛化成普遍建议。
- 对不确定的策略归因只做候选标记，不做最终结论。
- 每条证据必须有来源引用。

### 7.2 CaseSalesInsightAgent

职责：整合同一案例下全部节级证据，提炼案例级销售洞察。

输入：

- 同一案例下所有 `<节>.sales_evidence.json`
- 同一案例下所有 `<节>.md`
- 可选：同一案例下所有 `<节>.provenance.json`

输出：

- `case.sales_insights.json`
- `case.sales_playbook.md`

关键约束：

- 从完整案例视角归纳，不以单节为边界割裂销售链路。
- 策略必须能被一个或多个证据支持。
- 话术必须标注适用阶段、场景、客户状态和销售目标。
- 对“教练推荐话术”与“原始话术”分开保存。
- 任何涉及收益、理赔、产品条款、监管要求的内容都必须保留合规边界。

### 7.3 SalesInsightReviewerAgent

职责：审核销售洞察产物的保真、结构完整性和合规风险。

检查项：

- 策略是否有证据支持。
- 话术是否忠于原始素材。
- 是否把模型推断包装成确定事实。
- 是否存在不合规表达，例如承诺收益、保证理赔、夸大保障、贬损竞品。
- 字段是否完整，是否适合下游检索。

### 7.4 StrategyNormalizerAgent

职责：全库归并策略和话术标签。

输入：

- 所有 `case.sales_insights.json`

输出：

- `sales_playbook/strategies.jsonl`
- `sales_playbook/scripts.jsonl`
- `sales_playbook/objections.jsonl`

关键约束：

- 合并相似策略时保留所有来源案例。
- 不强行把所有策略塞进固定框架。
- 支持人工维护 canonical strategy name。
- 为“业务待确认”的策略保留状态字段。

## 8. 数据契约建议

### 8.1 节级证据结构

```json
{
  "case_name": "案例A",
  "section_name": "第1节",
  "customer_signals": [
    {
      "signal": "客户对保险必要性感知弱",
      "evidence": "客户表达暂时不需要保险",
      "source_refs": []
    }
  ],
  "sales_actions": [
    {
      "action": "用家庭责任引导风险意识",
      "stage_hint": "售前",
      "evidence": "销售人员围绕家庭责任继续追问",
      "source_refs": []
    }
  ],
  "script_quotes": [
    {
      "quote": "原始话术",
      "speaker": "sales",
      "stage_hint": "售前",
      "scenario_hint": "客户保险意识弱",
      "source_refs": []
    }
  ],
  "objections": [
    {
      "objection": "我现在不需要保险",
      "response_evidence": "销售人员先接纳，再引导客户思考家庭责任",
      "source_refs": []
    }
  ],
  "strategy_candidates": [
    {
      "name": "风险唤醒",
      "reason": "销售动作围绕家庭责任和风险缺口展开",
      "confidence": "mid",
      "inferred": true,
      "source_refs": []
    }
  ]
}
```

### 8.2 案例级销售洞察结构

```json
{
  "case_name": "案例A",
  "case_summary": "本案例围绕某类客户的保障需求唤醒与成交推进展开。",
  "customer_journey": [
    {
      "stage": "售前",
      "customer_state": "保障意识弱",
      "sales_goal": "引发风险关注",
      "key_actions": ["场景提问", "家庭责任引导"],
      "evidence_refs": []
    }
  ],
  "strategies": [
    {
      "name": "风险唤醒式需求面谈",
      "aliases": ["风险唤醒", "保障缺口引导"],
      "definition": "通过生活场景和家庭责任，引导客户意识到保障缺口。",
      "applicable_stages": ["售前", "需求面谈"],
      "steps": ["场景切入", "风险追问", "缺口确认", "方案承接"],
      "do": ["先接纳客户现状", "用问题引导客户自己说出担忧"],
      "dont": ["不要直接恐吓客户", "不要承诺收益或理赔结果"],
      "confidence": "high",
      "inferred": true,
      "evidence_refs": []
    }
  ],
  "scripts": [
    {
      "stage": "售前",
      "scenario": "客户保险意识弱",
      "customer_trigger": "客户认为现在不需要保险",
      "goal": "吸引客户进入需求沟通",
      "source_quote": "案例中的原始话术",
      "coach_wording": "可复用的教练推荐话术",
      "strategy_names": ["风险唤醒式需求面谈"],
      "follow_up_questions": ["您现在最担心家庭哪方面风险？"],
      "compliance_notes": ["不得承诺收益、理赔结果或夸大保障范围"],
      "evidence_refs": []
    }
  ],
  "objection_handling": [
    {
      "objection": "我现在不需要保险",
      "diagnosis": "客户未感知风险或认为保险优先级低",
      "recommended_response": "先接纳，再用家庭责任或真实场景引导风险意识。",
      "related_strategy_names": ["风险唤醒式需求面谈"],
      "related_script_ids": [],
      "evidence_refs": []
    }
  ]
}
```

### 8.3 全库策略结构

```json
{
  "strategy_id": "strategy_risk_awareness_001",
  "canonical_name": "风险唤醒式需求面谈",
  "aliases": ["风险唤醒", "保障缺口引导"],
  "definition": "通过生活场景、家庭责任和保障缺口问题，引导客户主动意识到风险。",
  "applicable_stages": ["售前", "需求面谈"],
  "representative_cases": ["案例A", "案例B"],
  "representative_script_ids": ["script_001", "script_017"],
  "status": "needs_business_review"
}
```

## 9. 产物目录

建议新增以下产物：

```text
output/
├── <案例>/
│   ├── <节>.md
│   ├── <节>.meta.json
│   ├── <节>.provenance.json
│   ├── <节>.sales_evidence.json
│   ├── case.sales_insights.json
│   └── case.sales_playbook.md
└── sales_playbook/
    ├── strategies.jsonl
    ├── scripts.jsonl
    └── objections.jsonl
```

`case.sales_playbook.md` 面向人工审阅，`case.sales_insights.json` 面向程序和 RAG 入库。
全库 `jsonl` 面向下游统一 embedding、索引和检索。

## 10. AI 教练调用方式

AI 教练回答用户问题时，应先识别用户意图，再选择检索资产。

典型路由：

| 用户问题 | 推荐检索对象 | 检索条件 |
| --- | --- | --- |
| 售前怎么吸引客户？ | `scripts.jsonl` | `stage=售前`，按 scenario 向量召回 |
| 客户说没必要买保险怎么办？ | `objections.jsonl` | objection 语义匹配 |
| 这个案例用了什么销售方法？ | `case.sales_insights.json` | case_name 精确过滤 |
| 5S 销售法有哪些案例？ | `strategies.jsonl` | strategy name / alias 匹配 |
| 给我一个可练习的话术剧本 | `scripts.jsonl` + `case.sales_insights.json` | stage、scenario、customer_state 联合召回 |

回答结构建议：

```text
适用场景：
推荐话术：
为什么这样说：
背后的销售策略：
追问建议：
合规提醒：
参考案例：
```

这样 AI 教练不会只返回泛泛建议，而是能给出“可直接练习”的话术和“为什么这么说”的策略解释。

## 11. 合规与安全边界

销售洞察链路必须遵守以下边界：

- 不生成或保留客户个人身份信息。
- 不承诺收益、分红、理赔结果或核保结果。
- 不使用恐吓式、误导式、夸大式表达。
- 不将未经验证的个案经验包装成公司标准流程。
- 产品条款、保障责任、免责条款等内容必须以原素材为准，并提示核对正式条款。
- 话术可以做“教练版改写”，但必须保留原始话术和来源，方便人工复核。

## 12. 实施阶段建议

### 阶段一：案例级洞察最小闭环

- 增加 `SectionSalesEvidence`、`CaseSalesInsights` 等 pydantic 模型。
- 增加 `SectionSalesEvidenceAgent` 和 `CaseSalesInsightAgent`。
- 新增单案例命令，例如：

```bash
uv run insurance-coach-md sales-insights "<案例>"
```

- 产出 `<节>.sales_evidence.json` 和 `case.sales_insights.json`。

### 阶段二：质检与人工审阅

- 增加 `SalesInsightReviewerAgent`。
- 生成 `case.sales_playbook.md`，方便业务人员审阅。
- 在 manifest 中记录案例级洞察状态、评分和问题。

### 阶段三：全库归并

- 增加全库命令，例如：

```bash
uv run insurance-coach-md sales-playbook
```

- 读取所有 `case.sales_insights.json`。
- 输出 `strategies.jsonl`、`scripts.jsonl`、`objections.jsonl`。
- 为每条策略保留 `status`，支持后续人工确认。

## 13. 测试建议

需要覆盖以下测试：

- 节级证据 agent 能返回结构化模型。
- 案例级 agent 能整合多个节的证据。
- 同一案例下节顺序稳定，不因文件系统顺序导致输出混乱。
- JSON sidecar 能原子写入。
- 合规风险表达能被 reviewer 标记。
- 空案例、无话术案例、只有通用知识的案例能优雅降级。
- fake 模型测试不调用真实 API。

## 14. 待确认问题

- 是否已有公司内部定义的标准销售方法论清单，例如 5S 销售法、SPIN、FABE 等。
- AI 教练最终是否需要严格使用公司标准策略名称，还是允许先生成“候选策略”。
- 话术是否需要区分“原始话术”“标准化话术”“陪练话术”三个版本。
- 业务侧是否需要在入库前人工审核 `case.sales_playbook.md`。
- 下游向量库是否支持结构化字段过滤，例如 `stage`、`scenario`、`strategy_id`。
