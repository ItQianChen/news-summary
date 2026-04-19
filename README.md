# News Summary (聚合新闻摘要生成器)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.33%2B-FF4B4B.svg)](https://streamlit.io/)

News Summary 是一个用于聚合多平台新闻热榜、筛选代表评论并通过大语言模型（LLM）生成结构化 Markdown 日报的轻量级可拓展应用架构。

## 🌟 核心特性 (Features)

- **🖥️ 现代化 Web 界面**：基于 Streamlit 构建了傻瓜式可视化管控面板，支持配置修改、流水线一键触发、历史报告记录管理，内置全屏原生侧滑目录，提供最高级的沉浸式阅读体验。
- **🌐 多平台网络爬虫**：内置针对抖音、微博、Bilibili、X (Twitter)、YouTube 等主流平台的热榜与搜索采集器（包含网络异常自动降级回退机制）。
- **🧠 智能语义去重 (Dedupe)**：突破简单的关键字字面量匹配限制，引入高级语义聚类算法，自动将多平台的同一现象级热点事件进行合并。
- **🤖 LLM 摘要引擎**：支持接入完整的 OpenAI 兼容 API 阵列，通过专业 Prompt 自动深度提炼热点背景、争议焦点与多方观点，生成高价值行业洞察。
- **⚡ 高并发调度架构**：支持在平台采集层和事件分析层实施配置化多线程并发运作，极大地加速数据漏斗与日报生成速度。

---

## 🚀 快速开始 (Quick Start)

### 1. 环境准备

确保您的本地环境已安装 Python 3.8+。拉取本仓库及安装后端运行组件与 UI 依赖：

```bash
pip install -r requirements.txt
```

### 2. 初始化核心变量

复制环境变量模版文件，并在生成的 `.env` 中填入你的大模型 API 凭证：

```bash
cp .env.example .env  # 并在其中编辑以下必须字段
```

**✅ 必填环境变量 (`.env`):**
- `OPENAI_API_KEY`: 服务商提供的 API 校验密钥
- `OPENAI_BASE_URL`: 模型代理或协议中转地址（例如: `https://api.openai.com/v1`）
- `MODEL_NAME`: 接入的模型名称（例如: `gpt-4o`, `deepseek-chat` 等）

### 3. 启动应用

对于一般使用者及开发者，强烈建议通过 Web UI 模式运作并管理本项目：

```bash
streamlit run app.py
```
*启动后浏览器将进入本机仪表板（`http://localhost:8501`）。您可以在左侧面板中实时调整所有技术参数，并点击运行，实现“一键爬取 > 一键生成 > 可视化流畅阅读”。*

#### 其他可用运行模式：
**命令行纯净触发流（适用于部署测试）**:
```bash
python -m src.main
```
**启动本机定时任务调度器**:
```bash
python -m src.scheduler
```

---

## ⚙️ 系统配置说明 (Configuration)

除了环境秘钥外的业务参数控制，可以在 Web UI 中配置，或修改位于 `config/settings.yaml` 下的原生设定：

### 📡 采集器设定 (Collector)
* `enabled_platforms`: 启用的抓取节点平台阵列（默认推荐: weibo, douyin, bilibili）
* `top_limit`: 限定每个采集支路最大所能收集的热榜条目量（默认: 30）
* `concurrent_platforms`: 是否打开多站并发访问，加快拉取速度
* `max_platform_workers`: 网络并发连接的工作线程资源总数

### 🤖 人工智能设定 (AI)
* `concurrent_event_summaries`: 是否允许大语言模型对多篇合并后的热点启动并发概括
* `max_summary_workers`: 向大模型发起高并发请求的限制阈值（请根据所使用厂商的请求 QPS 限流要求适当控制）

---

## 📂 项目结构体系 (Architecture)

```text
NewsSummary/
├── app.py                  # 🌟 Streamlit 视图应用与前端交互入口
├── config/                 # 总体功能参控与 Prompt 中枢 (settings.yaml 等)
├── data/                   # SQLite 载荷节点与持久化 Markdown 日志保存
├── src/                    # 引擎源程序及流水线节点调度模块
│   ├── main.py             # 无头控制台入口
│   ├── scheduler.py        # 任务调度触发
│   ├── ai/                 # LLM 通讯链路与并发拼装工厂
│   ├── collectors/         # 网络爬取数据源 (douyin, weibo, bilibili 等策略)
│   ├── dedupe/             # 广义事件提取与融合聚类计算
│   ├── models/             # PyDantic 强制类型输入模型定义结构
│   ├── normalizers/        # 内容文本清洗与正则剥壳归一化适配器
│   ├── selectors/          # 过滤劣质评论与垃圾内容的清洗分类系统
│   └── storage/            # 数据入库策略与报告落地写出管控器
└── requirements.txt        # 环境依赖装载清单
```

---

## 📑 运行时数据流转说明

当发起数据生成动作时，应用的底层计算将经历以下五步周期性链路：
1. **多路抓取**：按预设的最高采集阀值及线程数拉取全网平台热门信息。
2. **重塑清洗**：使杂乱的特定平台内容向数据模型（Pydantic）抽象归拢对齐。
3. **聚合去重**：通过文本关联及内插的词向量对跨越同一网络维度的相似独立话题进行自动归类合并汇编。
4. **模型透析**：调控投喂速度，由 LLM 生成标准化背景、正反对立面提炼。
5. **视图载出**：在文件流产出复合型 Markdown 文档日志，并最终渲染于应用前端 UI之上。

---

## 🤝 贡献参与 (Contributing)

对于想要协助丰富更多媒体信息源抓取扩展，或具有更为强劲模型 Prompt 调度方案的朋友，欢迎您任何时候提交 Bug 反馈、开立 PR 并与社群一同完善此项目！

## 📄 许可协议 (License)

本项目基于 [MIT License](LICENSE) 协议开源。
