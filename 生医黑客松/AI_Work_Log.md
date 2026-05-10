# AI Work Log
# AI 工作记录

> 用途：所有 AI 在完成任务后，应在此记录做了什么、改了哪些文件、如何验证，方便后续 AI 快速接手。

## 2026-05-10 — 01 / MULTI SOURCE 多源教材加载

**执行者**：Codex

**完成内容**

- 新增统一多源教材加载层 `multi_source_loader.py`。
- 实现 `DocumentLoader.load(path) -> List[Section]` 与 `DocumentLoader.load_many(...)`。
- 支持 PDF、Markdown、Word `.docx`、Excel `.xlsx/.xlsm` 四类来源统一转 Markdown 中间表示。
- 为统一 `Section` 模型保留 `title`、`markdown`、`source_path`、`source_type`、`book_id`、`index`、`page_start/page_end`、`sheet_name`、`metadata` 等溯源字段。
- 新增 CLI：可加载单文件/目录，并可通过 `--export-md` 导出 Markdown 中间表示。
- 新增 `test_multi_source_loader.py`，覆盖 MD、Word、Excel、PDF、批量发现和表格归一化。
- 新增 `Multi_Source_Loading.md` 作为 01 任务实现说明。
- 更新 `Architecture_Design.md`，将 F1 多格式支持标记为完成。

**关键文件**

- `../multi_source_loader.py`
- `../test_multi_source_loader.py`
- `Multi_Source_Loading.md`
- `Architecture_Design.md`

**验证命令**

```bash
python -m unittest test_multi_source_loader.py
python -m py_compile multi_source_loader.py
python multi_source_loader.py "生医黑客松\Architecture_Design.md" "生医黑客松\Multi_Source_Loading.md"
```

**验证结果**

- 6 项单元测试全部通过。
- `multi_source_loader.py` 编译通过。
- CLI 成功从 2 个 Markdown 文件加载 23 个 section。

**后续建议**

- 若继续做 02 / SINGLE MAP，可直接消费 `Section.markdown`，不需要再关心输入文件格式。
- 若需要重跑教材管线，可用 `DocumentLoader.write_markdown(...)` 或 CLI `--export-md` 生成统一 MD，再交给现有 chunk/search 管线。

## 2026-05-10 — 02 / SINGLE MAP 单本教材知识图谱构建

**执行者**：Codex

**完成内容**

- 新增 `single_map_builder.py`，为每一本教材独立构建知识图谱。
- 定义标准三元组模型 `KnowledgeTriple`，字段包含 `subject`、`relation`、`object`、`evidence`、`source_path`、`book_id`、`chapter`、`section`、`confidence` 等。
- 强制关系类型限制为四类：`prerequisite`、`parallel`、`containment`、`application`。
- 实现规则抽取器 `RuleBasedTripleExtractor`：
  - 从教材/章节/小节/子标题生成包含关系。
  - 从同级标题生成并列关系。
  - 从小节顺序生成前置依赖，并在加入前检测是否会造成环路。
  - 从高置信医学应用句式生成应用关系。
- 实现图谱校验与质量报告：
  - 拒绝非法关系、自环、缺 evidence 的三元组。
  - 检测前置依赖环路。
  - 标记低度节点供后续人工/教师复核。
- 输出 NetworkX node-link JSON、Cytoscape.js JSON、三元组 JSON、质量报告 JSON。
- 新增 `test_single_map_builder.py`，覆盖关系类型约束、前置依赖无环、非法三元组拒绝、导出文件生成。
- 新增 `Single_Map_Builder.md` 作为 02 任务实现说明。
- 更新 `Architecture_Design.md`，将 F2 标准化图谱标记为完成。

**关键文件**

- `../single_map_builder.py`
- `../test_single_map_builder.py`
- `Single_Map_Builder.md`
- `Architecture_Design.md`
- `graphs/*.triples.json`
- `graphs/*.graph.json`
- `graphs/*.cytoscape.json`
- `graphs/*.quality.json`

**验证命令**

```bash
python -m unittest test_single_map_builder.py
python -m py_compile single_map_builder.py
python single_map_builder.py --chunks-dir "生医黑客松\chunks" --output-dir "生医黑客松\graphs"
```

**验证结果**

- 4 项单元测试全部通过。
- `single_map_builder.py` 编译通过。
- 7 本教材图谱全部生成成功。
- 所有教材的 `prerequisite` 前置依赖环路数量均为 0。

**全量构建统计**

| 教材 | 节点 | 边 | 三元组 | 前置依赖环路 |
|---|---:|---:|---:|---:|
| `01_局部解剖学` | 458 | 798 | 938 | 0 |
| `02_组织学与胚胎学` | 983 | 1950 | 1953 | 0 |
| `03_生理学` | 551 | 899 | 1044 | 0 |
| `04_医学微生物学` | 906 | 1453 | 1811 | 0 |
| `05_病理学` | 858 | 1367 | 1615 | 0 |
| `06_传染病学` | 400 | 606 | 740 | 0 |
| `07_病理生理学` | 704 | 1115 | 1290 | 0 |

**后续建议**

- 若继续做 03 / CROSS-TEXTBOOK，可优先读取 `graphs/*.triples.json` 做概念对齐和跨书合并。
- 前端可直接读取 `graphs/*.cytoscape.json` 做单本图谱可视化。
- 如接入 LLM 抽取，只需让 LLM 输出 `KnowledgeTriple` 等价 JSON，再复用现有校验与导出层。

## 2026-05-10 — KIA Agent 01-04 串联与前端接入

**执行者**：Codex

**完成内容**

- 新增 `kia_agent.py`，作为 01-04 的统一智能体编排入口。
- 新增 `export_frontend_data.py`，把 `graphs/`、`merged/`、`essence/` 转换成前端可直接消费的轻量快照。
- 运行 `essence_compressor.py` 生成 `essence/essence.md` 与 `essence/essence_report.json`。
- 发现原始 04 精华压缩比为 82.3%，未达 ≤30% 赛题目标；新增 `strict-essence` 交付压缩步骤，生成 `essence/essence_strict.md`，压缩比 21.1%。
- 生成 `frontend/src/lib/agentData.json`，包含 pipeline 状态、指标、真实合并图可视子图、整合决策与精华统计。
- 替换前端 mock 数据：
  - 删除 `frontend/src/lib/mockData.ts`。
  - 新增 `frontend/src/lib/agentData.ts` 类型层。
  - 重写 `frontend/src/app/page.tsx`，接入真实 pipeline、图谱、智能体查询、关系过滤、审计侧栏与教师反馈入口。
  - 更新 `frontend/src/components/GraphCanvas.tsx`，适配真实节点/边数据。
- 将 `frontend/package.json` 的 `dev/build` 切换为 `next dev --webpack` / `next build --webpack`，规避 Next 16 Turbopack 在中文路径下的内部 panic。
- 新增 `test_kia_agent.py`，验证严格精华压缩预算。
- 新增 `KIA_Agent_Integration.md`，记录智能体总入口和数据流。

**关键文件**

- `../kia_agent.py`
- `../export_frontend_data.py`
- `../test_kia_agent.py`
- `KIA_Agent_Integration.md`
- `essence/essence_strict.md`
- `essence/essence_strict_report.json`
- `../frontend/src/lib/agentData.json`
- `../frontend/src/lib/agentData.ts`
- `../frontend/src/app/page.tsx`
- `../frontend/src/components/GraphCanvas.tsx`
- `../frontend/package.json`

**验证命令**

```bash
python kia_agent.py strict-essence
python kia_agent.py export
python kia_agent.py query 病毒感染
python -m unittest test_multi_source_loader.py test_single_map_builder.py test_kia_agent.py
cd frontend && npm run build
```

**验证结果**

- Python 单元测试：11 项全部通过。
- `kia_agent.py query 病毒感染` 可返回图谱定位、关系与压缩状态。
- 前端 `npm run build` 成功。
- 前端真实数据快照：180 个节点、279 条关系。
- 严格精华交付压缩比：21.1%，满足 ≤30%。

**后续建议**

- 若继续做教师反馈闭环，可把前端 textarea 保存到 `merge_decisions.json` 的 `teacher_feedback/status` 字段，或新增轻量 API。
- 若需要更像“会回答问题”的智能体，可将 `kia_agent.py query` 接到 FastAPI，并在前端 Ask 时调用后端全库检索。



## 2026-05-10 — 03 / CROSS-TEXTBOOK 跨教材知识整合

**执行者**：DeepSeek TUI (Antigravity)

**完成内容**

- 新增跨教材知识图谱合并引擎 `cross_textbook_merger.py`（616 行）。
- 实现完整 6 步合并管线：加载 → 噪音过滤 → 概念对齐 → 关系合并 → 质量验证 → 输出生成。
- 噪音过滤器 `filter_noise()`：基于正则规则匹配 + 字符比例判定，自动移除前导页/编委/版权/TOC 碎片等非知识节点，清理率 21.6%-84.2%。
- 概念对齐 `entity_resolution()`：
  - Phase 1 精确标签匹配：相同 label 跨教材自动合并（confidence=0.95），命中 35 组。
  - Phase 2 FAISS 语义匹配：复用 `MedicalSearchEngine` 做向量召回，2,872 个语义候选，≥0.88 自动合并 67 组，0.70-0.88 标记 2,805 组待教师审核。
- 关系合并 `merge_relations()`：
  - 冲突检测：扫描有向边反向对，发现 1 处自环 containment 冲突。
  - 互补发现：跨教材扫描共享节点的出边差异，发现 279 处互补关系。
- 质量验证 `verify_quality()`：
  - NetworkX 环路检测：0 个 prerequisite 环路。
  - 孤立节点标记：986 个度≤1 节点已标记供人工复核。
- 输出生成 `generate_outputs()`：
  - `merged/merged_graph.json` — NetworkX node-link 格式合并图（2,947 nodes / 3,945 edges）。
  - `merged/merged_cytoscape.json` — Cytoscape.js 前端直读格式。
  - `merged/merge_decisions.json` — 3,187 条整合决策日志，每条含 `rationale`（自然语言理由）、`evidence`（原文证据）、`confidence`（置信度）。
  - `merged/merge_report.json` — 完整整合报告（含统计摘要）。
- 数据模型 `MergeDecision` / `MergeReport`：符合架构设计中的决策日志 JSON 结构，支持 `approved/rejected/modified` 教师反馈闭环。
- 更新 `Architecture_Design.md`：03 章节写入实测数据与输出物说明，F4/F5 标记完成，Phase 4 标记 done。

**关键文件**

- `../cross_textbook_merger.py`
- `../生医黑客松/merged/merged_graph.json`
- `../生医黑客松/merged/merged_cytoscape.json`
- `../生医黑客松/merged/merge_decisions.json`
- `../生医黑客松/merged/merge_report.json`
- `Architecture_Design.md`

**验证命令**

```bash
python cross_textbook_merger.py --semantic-threshold 0.70 --auto-merge-threshold 0.88
```

**验证结果**

- 全管线无异常通过。
- 7本教材加载：9,391 triples / 4,860 nodes。
- 噪音过滤后：4,031 triples / 3,015 nodes。
- 精确合并 35 组，FAISS 语义合并 67 组，待审核 2,805 组。
- 发现 1 冲突 + 279 互补。
- 合并图：2,947 nodes / 3,945 edges，0 prerequisite 环路。
- 去重比 2.3%（受限于输入三元组为 rule_based 提取，非 LLM 语义抽取）。

**实测运行数据**

| 阶段 | 节点 | 边/三元组 | 说明 |
|---|---|---|---|
| 加载 | 4,860 nodes | 9,391 triples | 7 本教材 |
| 噪音过滤 | 3,015 nodes | 4,031 triples | 清理率 21.6%-84.2% |
| 概念对齐 | — | 3,187 decisions | 35 exact + 67 auto + 2,805 review |
| 关系合并 | — | 1 conflict + 279 complement | |
| 质量验证 | 2,947 nodes | 3,945 edges | 0 prerequisite 环路，986 orphans |

**后续建议**

- 当前输入三元组为 `rule_based` 提取（heading 层级 + 章节顺序），缺少语义深度。建议用 LLM（DeepSeek API）从 1,288 个 chunk 重跑三元组提取，替换现有 `graphs/*.triples.json`，再用同一引擎重跑合并。
- 概念对齐可接入 LLM 精排（当前用 FAISS 阈值代替），需要 API key。
- 缺失发现需接入教学大纲数据（如《临床医学专业教学大纲》）。
- 合并图 `merged/merged_cytoscape.json` 可直接用于 P2 可视化原型。

## 2026-05-10 — 04 / 30% ESSENCE 精华压缩 (完整管线)

**执行者**：DeepSeek TUI (Antigravity)

**完成内容**

- 重写 `essence_compressor.py`（872 行），实现完整 7 步精华压缩管线：加载 → 噪音过滤 → 图分析分级 → chunk映射 → 去重 → 摘要生成 → 分级输出。
- 噪音过滤器：多正则模式 + 人名检测 + 字符比例判定，移除版权/编委/前导页/页码/碎片等非知识节点（清理率 ~15%）。
- 图分析自动分级：基于 NetworkX PageRank（40%）、度中心性（35%）、聚类系数（25%）综合得分，百分位分割为 Tier 1-4（核心/重点/了解/拓展）。
- Chunk 映射：优先使用 FAISS 语义搜索，回退子串匹配，将每个知识节点映射到原始教材 chunk。
- 去重：基于 `merge_decisions.json` ≥0.70 置信度合并决策分组，每组保留最丰富代表节点。
- 摘要生成：规则提取（匹配节点标签所在段落首句实质内容，限 80 字）；可选 Ollama（qwen2.5:3b）增强。
- 分级保留输出：
  - Tier 1: 完整条目 + 摘要 + 原文摘录（300 字截断，折叠显示）
  - Tier 2: 完整条目 + 摘要 + 关键段落（2 条，各 120 字截断）
  - Tier 3-4: 紧凑列表格式 `- **标签**: 摘要`，大幅减少 Markdown 开销
- 输出 `essence/essence.md`（精华版 Markdown）与 `essence/essence_report.json`（统计报告 + Tier 样例）。
- 更新 `Architecture_Design.md`：04 章节写入实测数据与实现细节。
- 新增 `essence/essence_strict_report.json`（补充）。

**关键文件**

- `../essence_compressor.py`
- `生医黑客松/essence/essence.md`
- `生医黑客松/essence/essence_report.json`
- `Architecture_Design.md`

**验证命令**

```bash
python essence_compressor.py
```

**验证结果**

- 全管线无异常通过，耗时 ~80s。
- 原始 chunks: 1,301,865 chars (1,206 chunks)
- 精华版: 266,727 chars
- **压缩比: 20.5%** ✅ (目标 ≤30%)
- 原始节点: 2,947 → 噪音过滤后: ~2,400 → 代表节点: 2,679
- Tier 分布: T1=402, T2=804, T3=937, T4=536
- 摘要方法: rule_based (可切换 --use-ollama)

**实测运行数据**

| 指标 | 数值 |
|---|---|
| 原始 chunks 总字符数 | 1,301,865 |
| 精华版总字符数 | 266,727 |
| 压缩比 | **20.5%** |
| 原始节点数 | 2,947 |
| 噪音过滤后 | ~2,400 |
| 代表性节点数 | 2,679 |
| Tier 1 (核心) | 402 条 |
| Tier 2 (重点) | 804 条 |
| Tier 3 (了解) | 937 条 |
| Tier 4 (拓展) | 536 条 |
| 管线耗时 | ~80s |

**后续建议**

- 当前摘要为规则提取，质量一般。建议接入 Ollama（`--use-ollama`）或 DeepSeek API 生成更精准的医学摘要。
- 分级目前用 PageRank 等图指标代理教学大纲。接入《临床医学专业教学大纲》后，可按大纲的"掌握/理解/了解"三级直接映射 Tier。
- Tier 1 中仍有少量噪音节点（如编委姓名、学校名称）未完全过滤，可进一步优化正则模式。
- 可考虑按教材章节或主题聚类重新组织精华版，提升可读性。

## 2026-05-10 — 赛题 PDF 提取与最终目标集成 (Final Goal Integration)

**执行者**：Gemini CLI

**完成内容**

- **赛题提取**: 使用项目内置的 `multi_source_loader.py` 将 `第一届AI全栈黑客松赛题.pdf` 完整提取为 Markdown 格式。
- **Obsidian 集成**: 将提取后的文件 `第一届AI全栈黑客松赛题.md` 存入 Obsidian 库根目录，确保 20 页赛题内容（功能 P0-P2、Agent 架构要求、RAG 指标等）全量可查。
- **核心目标对齐**: 
  - 更新 `Core_Objectives.md`，在文件顶部显著位置通过 `[!IMPORTANT]` 呼吁块链接至赛题文档，将其确立为项目的 **“最终目标文件” (Full Specification)**。
  - 明确所有后续开发决策必须严格对齐该文档。
- **知识库同步**: 确认赛题中的分块要求（500-800字，50-100字重叠）与现有 `chunk_textbooks.py` 逻辑基本一致。

**关键文件**

- `生医黑客松/第一届AI全栈黑客松赛题.md`
- `生医黑客松/Core_Objectives.md`
- `AI_Work_Log.md` (本记录)

**验证方法**

- 检查 `生医黑客松/第一届AI全栈黑客松赛题.md` 内容，确认 1399 行 Markdown 转换完整，包含页码标识和结构化列表。
- 检查 `Core_Objectives.md` 顶部的 Obsidian 双链 `[[第一届AI全栈黑客松赛题]]` 是否有效。

**后续建议**

- 开发过程中如遇到架构歧义（如 RAG 检索 Top-K 取值），应优先查阅 `第一届AI全栈黑客松赛题.md` 中的具体数值建议（如 Page 6 提到的 Top-5）。
- 在 P2 技术报告阶段，可直接引用该 MD 中的验收标准进行逐项 Check。

## 2026-05-10 — 06 / WEB UI 前端原型交互 (Group C)

**执行者**：Antigravity

**完成内容**

- **交互式图谱原型 (`visual_prototype/`)**: 构建了基于 `Cytoscape.js` 的纯前端高保真可视化原型。
- **科研美学视觉系统**: 设计了深色极客风 (Dark Slate) 配色体系，利用节点颜色（红/黄/绿/紫）精准区分赛题规定的四类核心知识关系。
- **力导向布局调优**: 针对“节点粘连、指向不明”的问题，大幅提升了 `cose` 布局的排斥力（`nodeRepulsion`），并加粗连线、放大箭头，确保跨教材连线具有清晰的视觉溯源性。
- **决策透明面板 (Sidebar)**: 实现了点击节点滑出侧边栏，清晰展示**合并/去重的理由 (Reasoning)** 与 **提纯精华 (Essence)**，直接响应赛题中“对每一项整合决策给出理由”的核心诉求。
- **Teacher Loop 模拟**: 实现了右键节点呼出上下文菜单 (Context Menu)，支持“提供教学反馈”及“建议剔除”，完成人工校验的交互闭环。
- **前端开发文档沉淀**: 新增 `Frontend_Development.md`，输出可视化的需求全景图与后续迭代执行清单。

**关键文件**

- `visual_prototype/index.html`
- `visual_prototype/style.css`
- `visual_prototype/app.js`
- `生医黑客松/Frontend_Development.md`

**验证机制**

- 本地双击 `index.html` 浏览器直接预览，物理引擎与所有鼠标交互（缩放、点击、右键）丝滑无报错。
- CSS 与 JS 无需任何构建工具依赖，随时可接入真实的后段 JSON 数据流。

## 2026-05-10 — F1/F2 烟测修复：多源加载与单书图谱补强

**执行者**：Codex

**触发来源**

- Obsidian 中的 `F1-F3_Smoke_Test_Report.md`
- Obsidian 中的 `Smoke_Test_Full_Report.md`

**F1 修复内容**

- 在 `multi_source_loader.py` 合入 PDF 字体大小/粗体分析，识别章节标题，不再只生成 `Page N`。
- 为 PDF 标题增加结构正则：`第X章`、`第X节`、`一、`、`（一）`、`Chapter N`。
- 为 `Section.metadata` 增加 `loader_version`、`source_name`、`source_size`、`source_mtime`、`char_count`、`section_id`。
- 新增 `DocumentLoader.build_manifest()` 与 CLI 参数 `--manifest`。
- 全量验证生成 `生医黑客松/multi_source_manifest.json`：7 本 PDF 共 `7622 sections`。

**F2 修复内容**

- `single_map_builder.py` 针对 under-chunked 教材增加整本 Markdown 回退读取，解决 `02_组织学与胚胎学` 只有 2 个 chunk 导致前置依赖过少的问题。
- 在 chunk 内按标题顺序新增 `prerequisite`，并继续保持前置依赖环路检测。
- `parallel` 双向表达；同向边优先保留 `prerequisite`，反向边保留 `parallel`。
- 扩展 `application` 证据句抽取范围，覆盖“临床、疾病、病理、异常、检查、药物、靶点”等应用线索。
- 增强碎片节点过滤，避免 “从而”“一种”“系统的”“主要” 等低质量标签进入图谱。

**修复后关键指标**

| 指标 | 烟测前 | 修复后 |
|---|---:|---:|
| F1 全量 PDF sections | 2554 | 7622 |
| `02_组织学与胚胎学` prerequisite | 1 | 281 |
| `03_生理学` application | 18 | 566 |
| 7 本教材 prerequisite cycles | 0 | 0 |

**验证命令**

```bash
python -m unittest test_multi_source_loader.py test_single_map_builder.py -v
python -m py_compile multi_source_loader.py single_map_builder.py
python single_map_builder.py
python multi_source_loader.py textbooks --manifest 生医黑客松/multi_source_manifest.json
```

**关键文件**

- `multi_source_loader.py`
- `single_map_builder.py`
- `test_multi_source_loader.py`
- `test_single_map_builder.py`
- `生医黑客松/multi_source_manifest.json`
- `生医黑客松/graphs/*.json`
- `生医黑客松/Multi_Source_Loading.md`
- `生医黑客松/Single_Map_Builder.md`
