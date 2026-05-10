# Parallel AI Collaboration Protocol
# 多 AI 并行协作协议与任务分工

> **Project**: 2026 ZJU Hackathon - Knowledge Integration Agent (KIA)
> **Strategy**: 模块化解耦 + 接口契约化开发

---

## 1. 任务分工 (Task Division)

### **AI Group A: 数据专家 (Data Specialist)**
- **职责**: 负责 P0 级多格式加载与 P1 级单本知识图谱提取。
- **重点**: 
    - 实现 `multimodal_loader.py`（支持 PDF, MD, Word, Excel）。
    - 运行 `kg_extractor.py`，从 1295 个语义切片中提取四种核心关系。
- **交付**: 结构化的 `knowledge_base.json`。

### **AI Group B: 核心引擎 (Core Engine - Antigravity)**
- **职责**: 负责赛题核心难点：跨教材对齐、30% 提纯算法、整合理由生成。
- **重点**:
    - 开发 `merger_agent.py`（对齐、冲突检测、重组）。
    - 撰写核心文档：`docs/Agent 架构说明.md`、`docs/需求分析.md`。
- **交付**: 整合后的“精华本”语料及审计日志。

### **AI Group C: 全栈前端 (Full-stack UI)**
- **职责**: 负责科研美学风格的 Web 界面与图谱可视化。
- **重点**:
    - 初始化 Next.js 项目。
    - 实现 `Interactive_KG_Canvas`（基于 react-force-graph 或 AntV G6）。
    - 建立“教师反馈”对话接口。
- **交付**: 可直接访问的 Web 应用原型。

---

## 2. 接口协议 (Interface Contracts)

为确保模块集成，各组必须严格遵守以下 JSON 格式约定：

### **2.1 知识图谱标准格式**
```json
{
  "nodes": [
    {
      "id": "entity_id",
      "label": "知识点名称",
      "source": ["教材A", "教材B"],
      "type": "Concept",
      "metadata": {
        "essence": "30%提纯后的描述文本",
        "reasoning": "为什么保留此描述的逻辑依据",
        "references": [{"book": "A", "page": 12}, {"book": "B", "page": 45}]
      }
    }
  ],
  "edges": [
    {
      "source": "id1",
      "target": "id2",
      "type": "Prerequisite | Parallel | Inclusion | Application"
    }
  ]
}
```

### **2.2 整合决策协议**
每一条整合操作（Merge/Drop/Replace）必须记录：
- `action`: 操作类型
- `input_sources`: 参与合并的原始节点
- `output_node`: 产生的精华节点
- `logic`: 决策理由文本（对应赛题 F5 要求）

---

## 3. 同步节奏 (Sync Cadence)
- **Repo 共享**: 所有代码统一提交至 `main` 分支。
- **文档优先**: 架构说明文档由 Group B 牵头，Group A/C 补充技术细节。

---
*Created by Antigravity for Zizhou Han @ 2026-05-10*
