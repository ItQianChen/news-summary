# News Summary MVP

一个用于聚合多平台新闻热榜、筛选代表评论并生成 Markdown 日报的 Python 基础架构。

## 目录结构

```text
NewsSummary/
├─ .env.example
├─ README.md
├─ requirements.txt
├─ config/
│  ├─ settings.yaml
│  └─ prompts/
│     ├─ daily_digest.txt
│     └─ event_summary.txt
├─ data/
│  ├─ processed/.gitkeep
│  ├─ raw/.gitkeep
│  └─ reports/.gitkeep
└─ src/
   ├─ main.py
   ├─ scheduler.py
   ├─ ai/
   │  ├─ __init__.py
   │  ├─ client.py
   │  ├─ prompts.py
   │  └─ summarizer.py
   ├─ collectors/
   │  ├─ __init__.py
   │  ├─ base.py
   │  ├─ douyin.py
   │  ├─ weibo.py
   │  ├─ x.py
   │  └─ youtube.py
   ├─ dedupe/
   │  ├─ __init__.py
   │  └─ event_cluster.py
   ├─ models/
   │  ├─ __init__.py
   │  ├─ comment.py
   │  ├─ event.py
   │  └─ ranking.py
   ├─ normalizers/
   │  ├─ __init__.py
   │  └─ event_normalizer.py
   ├─ selectors/
   │  ├─ __init__.py
   │  └─ comment_selector.py
   ├─ storage/
   │  ├─ __init__.py
   │  ├─ db.py
   │  ├─ files.py
   │  └─ repositories.py
   └─ utils/
      ├─ __init__.py
      ├─ logger.py
      ├─ retry.py
      └─ text.py
```

## 当前实现范围

当前代码实现的是“基础架构 + 最小可用抓取链路”，不是完整商业级产品：

- 定义了统一的数据模型
- 定义了采集器抽象接口，并提供抖音 / 微博 / Bilibili / X / YouTube 的真实网络抓取方案
- 实现了标准化、规则+相似度去重、评论筛选、摘要拼装的基础流程
- 提供 SQLite 初始化与基础 Repository
- 提供可配置的 OpenAI 兼容客户端
- 提供手动运行入口和 APScheduler 定时入口
- 提供配置文件、Prompt 模板和环境变量样例

## 快速开始

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 复制环境变量文件并按需修改

```bash
copy .env.example .env
```

3. 不配置 AI 也可以直接跑通基础流程

```bash
python -m src.main
```

4. 配置 AI 后再次执行，可得到模型生成的事件总结和日报

```bash
python -m src.main
```

5. 启动本地调度器

```bash
python -m src.scheduler
```

## 你需要配置的 AI 项

至少填写以下三个：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `MODEL_NAME`

可选增强：

- `EMBEDDING_MODEL`：用于更强的事件去重语义相似度
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_MAX_RETRIES`
- `OPENAI_TEMPERATURE`

## 配置说明

可在 [`config/settings.yaml`](config/settings.yaml) 中控制抓取平台、AI 并发与输出规模：

- [`collector.enabled_platforms`](config/settings.yaml)：决定本次运行启用哪些平台，例如只配置 `weibo` 和 `douyin` 就只抓这两个平台。
- [`collector.top_limit`](config/settings.yaml)：每个平台抓取的热榜条数，默认 `30`。
- [`collector.concurrent_platforms`](config/settings.yaml)：是否并发抓取已启用平台，默认 `true`。
- [`collector.max_platform_workers`](config/settings.yaml)：平台级最大并发数，默认 `3`。
- [`ai.concurrent_event_summaries`](config/settings.yaml)：是否并发生成事件级 AI 摘要，默认 `true`。
- [`ai.max_summary_workers`](config/settings.yaml)：事件级 AI 摘要最大并发数，默认 `3`。
- [`report.focus_limit`](config/settings.yaml)：日报焦点条数，默认 `10`。

当前默认启用平台为微博、抖音、Bilibili；如需恢复 X / YouTube，只需把对应平台名加入 [`collector.enabled_platforms`](config/settings.yaml)。

## 当前输出语义

当前实现不是“所有平台抓完后再硬截断成 30 条输出”，而是：

- 每个平台先按 [`collector.top_limit`](config/settings.yaml) 抓取，例如两个平台就是 `30 + 30` 条源数据。
- 已启用平台会在入口调度层并发执行；例如同时启用抖音和 Bilibili 时，两者会同时开始抓取。
- 所有平台源条目先做并集汇总，再对相同事件进行聚类合并。
- 聚类后的事件级 AI 摘要也可并发生成；默认会按 [`ai.max_summary_workers`](config/settings.yaml) 受控并发调用模型，但最终输出顺序仍保持与事件列表一致。
- 合并后的单个事件会保留其命中的全部平台条目，例如“事件 1”下同时展示微博、抖音、Bilibili 命中项。
- Markdown 与 JSON 都会输出完整事件并集，不再使用“最终事件数 30 条”的硬截断配置。

## 说明

- 抖音采集：优先使用 Douyin Web 热榜与搜索接口，失败时回退到页面镜像与搜索摘要。
- 微博采集：使用公开热搜接口 + 搜索结果帖子作为评论观点样本。
- Bilibili 采集：优先使用热门视频公开接口，失败时回退到页面镜像与搜索结果摘要。
- X 采集：使用 Trends24 获取趋势词，使用 Nitter RSS 获取讨论样本。
- YouTube 采集：使用 Invidious 公共接口获取趋势视频和评论样本。
- 如果第三方来源暂时不可访问，系统会自动降级为搜索摘要或占位数据，而不是直接崩溃。
