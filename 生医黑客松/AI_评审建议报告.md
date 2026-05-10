# AI 全栈极速黑客松 · AI 评审建议报告

> 选手：周子涵
> GitHub：https://github.com/hunmingtianzi-boop/zju-hackathon-2026-zzh
> 当前得分：**78.5/100**（基础 56/62 · 进阶 17.5/28 · F 创新 5/10）

---

## 各维度得分

### A. 文档完整性（13.5/15）

| 子项 | 基础分 | 进阶分 | 得分 | 扣分原因 | 改进建议 |
|---|---|---|---|---|---|
| README 可复现性 | 3/3 | 0/1 | 3 | 四项要素齐全，有线上 Vercel 演示链接；但无 Docker 一键部署命令 | 在 README 顶部加"Docker 一键启动"节，写 Dockerfile + docker-compose.yml，加 `docker compose up` 一行（30 分钟 · +1 分） |
| 需求分析文档 | 3/3 | 1/1 | 4 | 四个子问题全部覆盖，RAG 分块依据有 1295 chunks 数据支撑 | ✅ 已满档 |
| 系统设计文档 | 3/3 | 1/1 | 4 | 架构 + 数据流 + 技术选型齐全，API 接口表含完整请求/响应示例 | ✅ 已满档 |
| 整合报告 | 2/2 | 0.5/1 | 2.5 | 案例详解偏概括，缺少三元组级别 case study | 追加"心功能不全"端到端案例：列出 5-8 个原始三元组、合并决策 ID、最终压缩输出（20 分钟 · +0.5 分） |

### B. 功能实现（19/25）

| 子项 | 基础分 | 进阶分 | 得分 | 扣分原因 | 改进建议 |
|---|---|---|---|---|---|
| 多格式文件解析 | 2/2 | 1/1 | 3 | PDF/MD/DOCX/XLSX 四种格式全部实现 | ✅ 已满档 |
| 知识点提取与图谱构建 | 4/4 | 0/1 | 4 | 4 种关系类型齐全，但规则抽取无 LLM few-shot 实证 | 用 `llm_client.py` 写 `llm_triple_extractor.py`，对 1-2 个 chunk 跑 few-shot 抽取并写入 `llm_sample.json`（45 分钟 · +1 分） |
| 知识图谱交互 | 2/2 | 0/0 | 2 | 节点点击 + 缩放拖拽 + 频次全部实现 | ✅ 已满档（无 bonus 项） |
| 跨教材整合算法 | 5/5 | 0.5/1 | 5.5 | 双重对齐具备，21.1% 压缩比达标；但整合前后可视化对比在前端没显式呈现 | 在"整合报告"tab 顶部加 `nodesBefore → nodesAfter` 对比卡 + 条形图（20 分钟 · +0.5 分） |
| RAG 问答功能 | 4/4 | 1/1 | 5 | BM25+FAISS+DeepSeek+引用全链路打通 | ✅ 已满档 |
| 多轮对话与迭代 | 3/3 | 0.5/1 | 3.5 | /api/feedback 已写 merge_decisions.json，但前端反馈后没显式刷新图谱 | `submitFeedback()` 成功后 `router.refresh()` + toast 提示（10 分钟 · +0.5 分） |

### C. 可视化（9.5/13）

| 子项 | 基础分 | 进阶分 | 得分 | 扣分原因 | 改进建议 |
|---|---|---|---|---|---|
| 视觉实现 | 3/3 | 1/1 | 4 | 专业库 + 颜色大小映射 + merged 发光效果 | ✅ 已满档 |
| 交互功能 | 3/3 | 1/1 | 4 | 点击+缩放+搜索+关系筛选+悬停 tooltip | ✅ 已满档 |
| 创新元素 | 0/0 | 1.5/3 | 1.5 | 多视图切换在 visual_prototype 有但主前端没集成 | 加布局切换按钮组 + 节点形状维度（六边形 vs 圆形）（30 分钟 · +1.5 分） |

### D. Agent 架构（18/20）

| 子项 | 基础分 | 进阶分 | 得分 | 扣分原因 | 改进建议 |
|---|---|---|---|---|---|
| 架构总览与清晰度 | 3/3 | 1/1 | 4 | Mermaid 流程图 + 文件名标注 + 数据流 | ✅ 已满档 |
| 设计决策论证 | 5/5 | 1/1 | 6 | 4 个决策各有量化对比表 | ✅ 已满档 |
| RAG Pipeline 设计 | 4/4 | 0.5/1 | 4.5 | 分块策略+embedding+检索完整，但缺不同分块大小效果对比数据 | 追加 chunk size=300/500/800/1200 的 top-5 命中率对比表（30 分钟 · +0.5 分） |
| Prompt 工程 | 1/2 | 0.5/1 | 1.5 | 文档有 few-shot 建议但代码层 system prompt 太弱 | 把 few-shot 模板写成实际可运行的 `prompts/triple_extraction.py` 模块（45 分钟 · +1 分） |
| 已知局限与改进 | 1/1 | 1/1 | 2 | 5 条局限各有改进方案 | ✅ 已满档 |

### E. 代码质量（13/17）

| 子项 | 基础分 | 进阶分 | 得分 | 扣分原因 | 改进建议 |
|---|---|---|---|---|---|
| 目录结构 | 3/3 | 0.5/1 | 3.5 | 前后端分离，但根目录 10 个 .py 扁平化 | 新建 `kia/` 子包归类，2 小时内不建议做 |
| 依赖管理 | 2/2 | 1.5/1 | 3.5 | requirements.txt 有版本约束但没用 `==` 严格 pin | 生成 `requirements.lock` 把 transitive deps pin 死（10 分钟 · +0.5 分） |
| 代码规范 | 3/3 | 1/1 | 4 | 类型注解 + dataclass + docstring，14 项测试 | ✅ 已满档 |
| 部署配置 | 2/2 | 0/2 | 2 | 有 Vercel 链接 + CLI，但无 Dockerfile | 补 Dockerfile + docker-compose.yml（40 分钟 · +2 分） |

### F. 创新与额外亮点（5/10）

**发现的创新点：**

1. **PageRank + 度中心性 + 聚类系数三因子自动分级（Tier 1-4）**（+2 分）
   - `essence_compressor.py` 中用 NetworkX 图算法在缺乏教学大纲时自动评估知识点重要性。Tier 1 与人工直觉吻合。

2. **严格预算二次压缩（strict-essence）**（+1 分）
   - `kia_agent.py` 的 `write_strict_essence()` 在原始精华版基础上做行级预算控制 + Markdown 结构折叠，82.3% → 21.1%。

3. **统一 Markdown 中间表示作为格式适配层**（+1 分）
   - 所有输入格式统一转 Markdown 后再下游处理。工程上优雅的解耦设计。

4. **RAG 双通路融合（图谱节点匹配 + 语义块检索互补）**（+1 分）
   - `kia_agent.query()` 同时跑 Pathway A（图节点字符串匹配）+ Pathway B（FAISS 语义检索），超越单一向量检索。

**点评**：创新分布在算法/工程/产品三个维度，少而精。如果再加 1-2 个方向能轻松上 7-8 分：① 流式输出（DeepSeek API 加 `stream=True`，前端 EventSource 逐字渲染，约 30 分钟 +2 分）；② 教师反馈训练队列（累积后自动重跑合并，体现 Agent 闭环学习，约 40 分钟 +2 分）。

---

## Top 5 改进优先级

### 1. [预计 +2 分 | 约 40 分钟] 补 Dockerfile + docker-compose.yml 一键部署

- **当前状况**：E 维度部署配置 bonus 0/2，README 也因此扣 0/1 进阶分
- **具体做法**：写 Dockerfile + docker-compose.yml（backend + frontend），README 加 `docker compose up` 一行

### 2. [预计 +2 分 | 约 30 分钟] 加流式输出（streaming RAG）

- **当前状况**：F 维度 5/10 还有 5 分空间；当前 RAG 答案是一次性返回
- **具体做法**：`llm_client.py` 加 `chat_stream()`，`/api/rag` 改为 SSE 流式回传，前端逐字渲染

### 3. [预计 +1.5 分 | 约 30 分钟] GraphCanvas 加布局切换 + 节点形状维度

- **当前状况**：C 维度三个子项都有进阶空间
- **具体做法**：加 `dagMode` 切换（td/lr/null）+ merged 节点画六边形

### 4. [预计 +1 分 | 约 45 分钟] 实际接入 LLM 三元组抽取（few-shot）

- **当前状况**：D-Prompt 工程 base 1/2，bonus 0.5/1；B-知识点提取 bonus 0/1
- **具体做法**：新建 `llm_triple_extractor.py`，写 few-shot prompt，对 1-2 chunk 跑出样例

### 5. [预计 +1 分 | 约 25 分钟] 移植 visual_prototype 右键菜单到主前端

- **当前状况**：C-交互 bonus 1/2；visual_prototype 有右键菜单但主前端没用
- **具体做法**：`GraphCanvas.tsx` 加 `onNodeRightClick` → 渲染右键菜单

---

## 整体评价

**当前阶段**：总分 78.5 分，P0/P1 完成度较高。所有 P0 基础功能几乎全部满档，多项 P1 进阶也已落地。

**亮点**：
1. 文档质量在所有评审维度里最强——四份文档几乎是参考答案级别
2. RAG pipeline 端到端通，BM25+FAISS+DeepSeek+引用全链路打通

**最大短板**：E 维度 Docker 完全缺失（但已补），D 维度 Prompt 工程代码层薄弱

**剩余方向**：按 Top 5 第 1 条优先做——补 Docker 一键部署（40 分钟 +2 分），ROI 最高。

---

*此报告由 AI 自动生成，仅供参考。最终评审由评委打分。*
*浙江大学未来学习中心 · AI 生态*
