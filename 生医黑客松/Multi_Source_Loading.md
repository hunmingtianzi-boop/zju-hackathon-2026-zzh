# 01 / MULTI SOURCE — 多源教材加载实现说明

> 状态：已实现统一加载层，可接入现有 Markdown chunk 与检索管线。

## 能力范围

`multi_source_loader.py` 提供统一接口：

```python
from multi_source_loader import DocumentLoader

loader = DocumentLoader()
sections = loader.load("textbooks/01_局部解剖学.pdf")
```

支持格式：

| 格式 | 扩展名 | 解析策略 |
|---|---|---|
| PDF | `.pdf` | PyMuPDF 提取页面文本块，输出 Markdown，并保留 page metadata |
| Markdown | `.md`, `.markdown` | 直接读取，按标题切分 Section |
| Word | `.docx` | python-docx 解析标题、段落、表格，统一为 Markdown |
| Excel | `.xlsx`, `.xlsm` | openpyxl 按 worksheet 转 Markdown 表格，每个 sheet 作为 Section |

## 统一数据模型

每个输入源会被规范为 `List[Section]`：

```python
Section(
    title="章节或工作表标题",
    markdown="Markdown 中间表示",
    source_path="原始文件绝对路径",
    source_type="pdf/md/docx/xlsx",
    book_id="文件名",
    index=0,
    page_start=1,
    page_end=1,
    sheet_name=None,
    metadata={}
)
```

下游模块只需要消费 `section.markdown`，无需关心原始文件格式。

## 命令行用法

加载单个文件并输出统计：

```bash
python multi_source_loader.py 生医黑客松/Architecture_Design.md
```

批量加载目录：

```bash
python multi_source_loader.py textbooks 生医黑客松
```

导出统一 Markdown 中间表示：

```bash
python multi_source_loader.py textbooks --export-md 生医黑客松/loaded_md
```

## 验证

已有测试覆盖 Markdown、Word、Excel、PDF 与目录批量发现：

```bash
python -m unittest test_multi_source_loader.py
```

## 2026-05-10 烟测修复

针对 `F1-F3_Smoke_Test_Report.md` 中 F1 的两个问题，已完成补强：

- PDF 解析不再固定输出 `Page N` 小节，而是通过 PyMuPDF 的 `dict` 文本块读取 span 字号、粗体标记和章节正则，识别 `第X章 / 第X节 / 一、 / （一） / Chapter N` 等标题层级。
- `process_all_textbooks.py` 中“字体分析 + 标题检测”的核心思路已合入统一加载器 `multi_source_loader.py`，避免两条 PDF 管线长期分裂。
- `Section.metadata` 增加 `loader_version / source_name / source_size / source_mtime / char_count / section_id`，方便下游智能体做溯源与审计。
- CLI 增加 `--manifest`，可输出多源加载清单 JSON。

本次验证：

```bash
python -m unittest test_multi_source_loader.py test_single_map_builder.py -v
python multi_source_loader.py textbooks --manifest 生医黑客松/multi_source_manifest.json
```

全量教材加载结果：7 本 PDF 共 `7622 sections`，相较烟测中的 `2554 sections`，章节语义粒度明显提升。
