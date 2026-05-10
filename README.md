# KIA — Knowledge Integration Agent

> 2026 ZJU 黑客松 Track 02 · 学科知识整合智能体  
> 将 7 本临床医学教材整合为不到 2.1 本精华的知识引擎

## 快速启动

### Docker 一键启动（推荐）

```bash
# 设置 API Key
export DEEPSEEK_API_KEY=sk-your-key

# 一键启动后端 + 前端
docker compose up -d

# 访问
# 前端: http://localhost:3000
# 后端: http://localhost:8000
```

### 本地启动

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 构建知识索引（首次运行）

```bash
# 若 FAISS 索引文件不存在，先生成
python search_engine.py
```

### 3. 运行全管线

```bash
# 查看各阶段状态
python kia_agent.py status

# 查询医学概念
python kia_agent.py query 心功能不全

# 导出前端数据快照
python kia_agent.py export

# 全管线重建（跳过昂贵步骤）
python kia_agent.py rebuild --skip-expensive
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:3000`

## 功能

- **多格式加载**：PDF / Markdown / Word / Excel → 统一结构化数据
- **知识图谱**：7 本教材独立 KG（4 种关系：前置依赖 / 并列 / 包含 / 应用）
- **跨教材整合**：语义对齐 + 自动合并 + 冲突检测 + 互补发现
- **30% 精华压缩**：去重 → 摘要 → 分级保留（实测 21.1%）
- **RAG 问答**：BM25 + FAISS 混合检索，答案带原文引用
- **教师反馈闭环**：多轮对话优化整合决策

## 项目结构

```
├── kia_agent.py              # 总编排器
├── multi_source_loader.py    # 01 多源加载
├── single_map_builder.py     # 02 单本图谱
├── cross_textbook_merger.py  # 03 跨教材合并
├── essence_compressor.py     # 04 精华压缩
├── search_engine.py          # BM25 + FAISS 检索
├── export_frontend_data.py   # 前端数据导出
├── docs/                     # 交付文档
│   ├── Agent架构说明.md
│   ├── 需求分析.md
│   ├── 系统设计.md
│   └── 整合报告.md
├── frontend/                 # Next.js 16 前端
├── test_*.py                 # 单元测试
└── 生医黑客松/               # 数据目录 (chunks / graphs / merged / essence)
```

## 测试

```bash
python -m unittest test_multi_source_loader.py test_single_map_builder.py test_kia_agent.py -v
```

## 引用开源项目

| 项目 | 用途 | 许可 |
|---|---|---|
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDF 解析 | AGPL |
| [python-docx](https://github.com/python-openxml/python-docx) | Word 解析 | MIT |
| [openpyxl](https://openpyxl.readthedocs.io/) | Excel 解析 | MIT |
| [jieba](https://github.com/fxsjy/jieba) | 中文分词 | MIT |
| [rank_bm25](https://github.com/dorianbrown/rank_bm25) | BM25 检索 | Apache 2.0 |
| [sentence-transformers](https://www.sbert.net/) | 语义向量 | Apache 2.0 |
| [FAISS](https://github.com/facebookresearch/faiss) | 向量检索 | MIT |
| [NetworkX](https://networkx.org/) | 图计算 | BSD |
| [Next.js](https://nextjs.org/) | 前端框架 | MIT |
| [react-force-graph-2d](https://github.com/vasturiano/react-force-graph) | 力导向图 | MIT |
| [lucide-react](https://lucide.dev/) | 图标库 | ISC |
| [framer-motion](https://www.framer.com/motion/) | 动画 | MIT |

## 许可证

MIT
## 线上演示  
  
https://frontend-one-iota-gga5wfadvx.vercel.app 
