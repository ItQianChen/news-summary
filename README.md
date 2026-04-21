# News Summary（聚合热点摘要生成器）

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)

News Summary 是一个面向多平台热点采集、事件聚类、评论筛选与 Markdown 日报生成的 Python 项目。当前实现支持从多个渠道抓取热榜数据，将跨平台相似话题聚类为事件，再结合评论与 LLM 生成结构化摘要，并将最终报告落盘到 [`data/reports`](data/reports)。

## 项目现状

当前主流程由 [`run_pipeline()`](src/main.py:134) 驱动，整体链路如下：

1. 通过 [`load_settings()`](src/main.py:30) 读取 [`config/settings.yaml`](config/settings.yaml)
2. 通过 [`build_collectors()`](src/main.py:36) 根据已启用平台创建采集器
3. 通过 [`_collect_all_platform_data()`](src/main.py:87) 并发抓取各平台热榜与评论
4. 使用 [`EventCluster`](src/main.py:146) 对跨平台热点进行聚类
5. 使用 [`CommentSelector`](src/main.py:151) 为每个事件筛选代表性评论
6. 使用 [`Summarizer`](src/ai/summarizer.py:12) 生成事件摘要与日报 Markdown
7. 通过 [`ReportFileManager.write_markdown()`](src/storage/files.py:13) 和 [`ReportFileManager.write_json()`](src/storage/files.py:19) 输出报告文件

## 当前支持的平台

平台采集器在 [`src/collectors/__init__.py`](src/collectors/__init__.py) 注册，当前代码已包含：

- toutiao
- weibo
- douyin
- bilibili
- x
- youtube

实际启用的平台由 [`config/settings.yaml`](config/settings.yaml) 中的 `collector.enabled_platforms` 控制，当前默认启用：

- toutiao
- weibo
- douyin
- bilibili

## 目录结构

```text
NewsSummary/
├── app.py
├── README.md
├── config/
│   ├── settings.yaml
│   └── prompts/
├── data/
│   ├── news_summary.db
│   ├── processed/
│   ├── raw/
│   └── reports/
├── src/
│   ├── main.py
│   ├── scheduler.py
│   ├── ai/
│   ├── collectors/
│   ├── dedupe/
│   ├── models/
│   ├── normalizers/
│   ├── selectors/
│   ├── storage/
│   └── utils/
└── requirements.txt
```

## 关键模块说明

### 入口与主流程

- [`app.py`](app.py)：Web 入口
- [`src/main.py`](src/main.py)：命令行主流程入口
- [`src/scheduler.py`](src/scheduler.py)：定时任务入口

### 采集层

- [`src/collectors/toutiao.py`](src/collectors/toutiao.py)：头条热榜与评论采集
- [`src/collectors/weibo.py`](src/collectors/weibo.py)：微博热搜与评论采集
- [`src/collectors/douyin.py`](src/collectors/douyin.py)：抖音热榜与评论采集
- [`src/collectors/bilibili.py`](src/collectors/bilibili.py)：B 站热门内容采集
- [`src/collectors/x.py`](src/collectors/x.py)：X 热点采集
- [`src/collectors/youtube.py`](src/collectors/youtube.py)：YouTube 热点采集

### 聚类与摘要层

- [`src/dedupe/event_cluster.py`](src/dedupe/event_cluster.py)：跨平台事件聚类
- [`src/selectors/comment_selector.py`](src/selectors/comment_selector.py)：评论筛选
- [`src/ai/client.py`](src/ai/client.py)：LLM 客户端
- [`src/ai/summarizer.py`](src/ai/summarizer.py)：事件摘要与日报生成

### 存储层

- [`src/storage/db.py`](src/storage/db.py)：SQLite 初始化
- [`src/storage/repositories.py`](src/storage/repositories.py)：榜单与评论持久化
- [`src/storage/files.py`](src/storage/files.py)：Markdown / JSON 报告写出

## 报告输出说明

最终日报由 [`Summarizer.summarize_daily()`](src/ai/summarizer.py:79) 生成。

当前版本已经完成日报结构改造：

- 一级标题固定为“今日热点摘要”
- 二级标题按渠道分组，格式为 `渠道：平台名`
- 每个渠道下先输出“今日 N 大焦点”
- 再输出该渠道自己的详细条目
- 同一个事件若命中多个平台，会分别出现在对应渠道下，但每个渠道块只展示本渠道条目
- **链接展示优化**：报告中的链接已统一格式化为 `[标题](真实URL)` 的短文本形式，避免超长 URL 影响阅读体验，同时在 Web 界面中支持直接点击跳转。AI 版报告也已通过 Prompt 约束保持一致的链接格式。

这意味着如果同时启用抖音和头条，最终 Markdown 不再把两个渠道混在同一个事件块里，而是按“抖音 → 头条”的方式分段输出。

报告文件默认输出到 [`data/reports`](data/reports)，文件名由时间戳与标签组成，具体由 [`ReportFileManager`](src/storage/files.py:8) 管理。

## 配置说明

核心配置位于 [`config/settings.yaml`](config/settings.yaml)。

### 采集配置

- `collector.top_limit`：每个平台抓取的热榜条数
- `collector.comment_limit`：每条热榜抓取的评论条数
- `collector.timeout_seconds`：采集超时时间
- `collector.allow_fallback_on_error`：采集失败时是否允许降级
- `collector.concurrent_platforms`：是否开启平台级并发采集
- `collector.max_platform_workers`：平台级并发数
- `collector.enabled_platforms`：启用的平台列表

### 评论筛选配置

- `selector.per_event_comment_limit`：每个事件保留的评论数
- `selector.min_text_length`：评论最小长度

### 聚类配置

- `dedupe.strong_similarity_threshold`：强相似阈值
- `dedupe.weak_similarity_threshold`：弱相似阈值

### AI 配置

- `ai.concurrent_event_summaries`：是否并发生成事件摘要
- `ai.max_summary_workers`：摘要并发数

### 报告配置

- `report.output_dir`：报告输出目录
- `report.write_json`：是否同时输出 JSON
- `report.focus_limit`：每个渠道的焦点数量上限

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 [`.env.example`](.env.example) 为 `.env`，并填写模型配置：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `MODEL_NAME`

### 3. 运行项目

命令行模式：

```bash
python -m src.main
```

Web 模式：

```bash
streamlit run app.py
```

定时任务模式：

```bash
python -m src.scheduler
```

## 适合继续改进的点

从当前代码结构看，后续最值得继续优化的是这几块：

1. 报告层：目前 Markdown 已按渠道分组，但 JSON 仍然是事件级结构，可考虑补充渠道级输出
2. 配置层：平台展示名仍直接使用内部标识，如 `douyin`、`toutiao`，可以补一层显示名映射
3. 验证层：当前缺少针对 [`Summarizer.summarize_daily()`](src/ai/summarizer.py:79) 的自动化测试
4. 文档层：如果 Web 界面已长期使用，建议补充 [`app.py`](app.py) 的操作说明与截图

## 许可证

本项目使用 [MIT License](LICENSE)。

