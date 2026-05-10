# 🧪 F1–F3 烟测报告

> 测试执行：DeepSeek TUI 0.8.24
> 测试日期：2026-05-10
> 测试范围：Core_Objectives 定义的 F1/F2/F3 功能要求
> 目标读者：Codex (负责 F1/F2 后端) / Frontend AI (负责 F3 前端)

---

## 测试方法

```
F1: python -m unittest test_multi_source_loader -v   → 6 tests
     python _smoke_f1.py                             → 7本教材全量加载
F2: python -m unittest test_single_map_builder -v    → 4 tests
     读取 graphs/*.quality.json                      → 质量报告审计
F3: npm run build                                    → 构建验证
     tsc --noEmit                                    → 类型检查
     审查 src/app/ 文件结构                           → 完整性检查
```

---

## F1 — 多格式支持：72/100 ⚠️

### ✅ 通过项

| 测试 | 结果 |
|------|------|
| 6 项单元测试 | 全通过 (0.878s) |
| 7 本 PDF 全部加载 | 2554 sections |
| 有效 Section 率 | 99.9% (2552/2554) |
| page_start / page_end 元数据 | 100% 覆盖 |
| source_type / book_id 溯源 | 正确 |
| Word (.docx) 加载 | 测试覆盖 |
| Excel (.xlsx) 加载 | 测试覆盖 |
| Markdown 按标题切分 | 测试覆盖 |

### ❌ 问题

- [ ] **PDF Section 标题全是 `Page N`，无章节语义** —— `_pdf_to_markdown` 缺少字体分析标题检测
- [ ] `process_all_textbooks.py` 的字体分析逻辑未合入 `multi_source_loader.py`，两条 PDF 管线并存

### 🔧 修复建议

把 `process_all_textbooks.py` 的字体大小分析 + 标题检测逻辑移植到 `multi_source_loader.py` 的 `_pdf_to_markdown` 方法中，然后删除 `process_all_textbooks.py`。

---

## F2 — 标准化图谱：85/100 ✅

### ✅ 通过项

| 测试 | 结果 |
|------|------|
| 4 项单元测试 | 全通过 (0.034s) |
| 7 本教材图谱全部生成 | 4860 节点 / 8188 边 / 9391 三元组 |
| prerequisite 环路检测 | 全部 0 环 |
| 四种关系全覆盖 | containment / parallel / prerequisite / application |
| 非法三元组拒绝 | 仅 1 个自环被正确拒绝 |
| Cytoscape.js JSON 导出 | 每本 4 文件 (.triples / .graph / .cytoscape / .quality) |

### 各教材质量明细

| 教材 | 节点 | 边 | 三元组 | 前置依赖 | 并列 | 包含 | 应用 | 环路 |
|------|------|-----|--------|----------|------|------|------|------|
| 01_局部解剖学 | 458 | 798 | 938 | ✓ | ✓ | ✓ | ✓ | 0 |
| 02_组织学与胚胎学 | 983 | 1950 | 1953 | 1 | 968 | 974 | 7 | 0 |
| 03_生理学 | 551 | 899 | 1044 | 166 | 200 | 515 | 18 | 0 |
| 04_医学微生物学 | 906 | 1453 | 1811 | ✓ | ✓ | ✓ | ✓ | 0 |
| 05_病理学 | 858 | 1367 | 1615 | 272 | 279 | 770 | 46 | 0 |
| 06_传染病学 | 400 | 606 | 740 | ✓ | ✓ | ✓ | ✓ | 0 |
| 07_病理生理学 | 704 | 1115 | 1290 | ✓ | ✓ | ✓ | ✓ | 0 |

### ❌ 问题

- [ ] **application 关系严重稀疏**：03_生理学仅 18 条 / 1044 三元组 (1.7%)，大量隐含临床联系遗漏
- [ ] **02_组织学与胚胎学前置依赖仅 1 条**：明显偏少，可能是 chunk 结构导致规则抽取器失效
- [ ] **low_degree_nodes 混入文本碎片**："从而""一种""系统的" 等无意义片段应被 `clean_label` 过滤

### 🔧 修复建议

1. 接入 LLM 三元组抽取（输出 `KnowledgeTriple` schema 即可复用现有校验/导出层）
2. 在 `clean_label` 中增加最小长度阈值（< 4 字的节点过滤）
3. 检查 02_组织学 chunk 的小节顺序标记是否丢失

---

## F3 — 交互式可视化：40/100 ❌

### ✅ 通过项

| 测试 | 结果 |
|------|------|
| `visual_prototype/` 原型可独立运行 | ✅ Cytoscape.js CDN + 精美暗色主题 |
| `GraphCanvas.tsx` 组件存在 | ✅ react-force-graph-2d 封装 |
| `agentData.ts` 类型定义 | ✅ 完整的 TS 接口 |
| 原型交互功能 | ✅ 缩放/拖拽/节点点击/右键菜单/过滤器/布局切换 |

### ❌ 问题 (按严重程度排序)

- [ ] **`page.tsx` 入口文件缺失** —— Next.js 应用无法渲染任何页面，`src/app/` 下仅有 `layout.tsx`
- [ ] **import 路径断裂** —— 引用 `@/lib/mockData` 但实际文件是 `@/lib/agentData`
- [ ] **`npm run build` 失败** —— Turbopack 中文路径 bug (非代码问题，但需用英文路径或 webpack 回退)
- [ ] **`tsc --noEmit` 失败** —— 3 个类型错误
- [ ] **搜索框无实现** —— 仅装饰性 UI
- [ ] **Teacher Feedback 无回调逻辑** —— 只有 UI 壳
- [ ] **全部 mock 数据** —— 未对接 `生医黑客松/graphs/*.cytoscape.json`
- [ ] **两套前端分裂** —— `visual_prototype/` 用 Cytoscape.js，`frontend/` 用 react-force-graph，需二选一合并

### 🔧 修复建议

1. **立即**：创建 `frontend/src/app/page.tsx`，import `GraphCanvas` + `agentData`
2. **立即**：修正所有 `@/lib/mockData` → `@/lib/agentData`
3. **P1**：对接 `生医黑客松/graphs/*.cytoscape.json` 作为真实数据源（二选一：Cytoscape.js 或 react-force-graph）
4. **P1**：实现搜索框的节点/边搜索逻辑
5. **P2**：Teacher Feedback 提交 → 调用后端 API
6. **P2**：配置 `turbopack.root` 或迁移到无中文路径以绕过 Turbopack bug

---

## 📊 总结

```
F1  多格式加载         72/100  ⚠️ PDF提取质量需提升
F2  单本知识图谱        85/100  ✅ 结构可靠，应用关系需LLM补强
F3  交互式可视化        40/100  ❌ 缺少入口页面，未对接后端
──────────────────────────────────
加权平均              65.7/100
```

**赛道交付风险**：F3 当前不可演示。黑客松评审至少需要：一个可运行的前端 + 真实图谱数据 + 交互式浏览。

**最短修复路径**（预计 2 小时）：
1. 创建 `page.tsx` → 前端可渲染
2. 修正 import 路径 → 类型检查通过
3. 用 `agentData.json` 或 `graphs/*.cytoscape.json` 接入真实数据
4. 合并 visual_prototype 的交互细节到 Next.js 或反之
