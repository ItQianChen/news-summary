import os
from pathlib import Path

import dotenv
import ruamel.yaml
import streamlit as st

st.set_page_config(page_title="NewsSummary 可视化工具", layout="wide", page_icon="📈")

yaml = ruamel.yaml.YAML()
yaml.preserve_quotes = True

def load_settings():
    settings_path = Path("config/settings.yaml")
    if not settings_path.exists():
        st.error(f"配置文件未找到: {settings_path}")
        return {}
    with open(settings_path, "r", encoding="utf-8") as f:
        return yaml.load(f)

def save_settings(data):
    settings_path = Path("config/settings.yaml")
    with open(settings_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

st.title("📈 NewsSummary 新闻抓取与总结系统")

env_path = ".env"
env_vars = {}
if os.path.exists(env_path):
    env_vars = dotenv.dotenv_values(env_path)
else:
    if os.path.exists(".env.example"):
        env_vars = dotenv.dotenv_values(".env.example")

settings = load_settings()

if not settings:
    st.stop()

collector_cfg = settings.get("collector", {})
ai_cfg = settings.get("ai", {})

with st.sidebar:
    st.header("⚙️ 系统配置")
    
    with st.expander("🤖 AI 配置", expanded=True):
        openai_api_key = st.text_input("OPENAI_API_KEY", value=env_vars.get("OPENAI_API_KEY", ""), type="password")
        openai_base_url = st.text_input("OPENAI_BASE_URL", value=env_vars.get("OPENAI_BASE_URL", ""))
        model_name = st.text_input("MODEL_NAME", value=env_vars.get("MODEL_NAME", "gpt-4o-mini"))
        embedding_model = st.text_input("EMBEDDING_MODEL", value=env_vars.get("EMBEDDING_MODEL", ""), help="可选。用于热点标题向量化聚类；不填写时，事件聚类退回规则模式。")
    
    with st.expander("🕵️ 抓取平台配置", expanded=True):
        platforms = list(collector_cfg.get("platforms", {}).keys())
        if not platforms: 
            platforms = ["weibo", "douyin", "bilibili", "toutiao", "x", "youtube"]
        
        # Currently enabled platforms
        enabled_platforms = collector_cfg.get("enabled_platforms")
        if enabled_platforms is None:
            enabled_platforms = platforms
        
        selected_platforms = []
        st.write("选择要抓取的平台：")
        for p in platforms:
            if st.checkbox(p, value=(p in enabled_platforms)):
                selected_platforms.append(p)
                
    with st.expander("📊 抓取数量限制", expanded=True):
        top_limit = st.number_input("排行抓取数量 (每个平台)", min_value=1, value=collector_cfg.get("top_limit", 30))
        comment_limit = st.number_input("评论抓取数量 (每个事件)", min_value=1, value=collector_cfg.get("comment_limit", 20))
        focus_limit = st.number_input("最终报告关注事件数", min_value=1, value=settings.get("report", {}).get("focus_limit", 10))

    with st.expander("⚡ 并发配置", expanded=True):
        concurrent_platforms = st.checkbox("并发爬取多个平台", value=collector_cfg.get("concurrent_platforms", True))
        max_platform_workers = st.number_input("平台爬虫最大并发数", min_value=1, value=collector_cfg.get("max_platform_workers", 3))
        
        concurrent_summaries = st.checkbox("并发进行 AI 总结", value=ai_cfg.get("concurrent_event_summaries", True))
        max_summary_workers = st.number_input("AI 总结最大并发数", min_value=1, value=ai_cfg.get("max_summary_workers", 10))

    st.markdown("---")
    run_btn = st.button("🚀 保存配置并运行流水线", type="primary", use_container_width=True)

if run_btn:
    # Save Env vars
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f: 
            f.write("")
    
    dotenv.set_key(env_path, "OPENAI_API_KEY", openai_api_key)
    if openai_base_url:
        dotenv.set_key(env_path, "OPENAI_BASE_URL", openai_base_url)
    if model_name:
        dotenv.set_key(env_path, "MODEL_NAME", model_name)
    if embedding_model:
        dotenv.set_key(env_path, "EMBEDDING_MODEL", embedding_model)
    else:
        dotenv.set_key(env_path, "EMBEDDING_MODEL", "")
    
    # Save Settings
    # We must properly initialize dicts if they don't exist
    if "collector" not in settings: settings["collector"] = {}
    if "ai" not in settings: settings["ai"] = {}
    if "report" not in settings: settings["report"] = {}
    
    settings["collector"]["enabled_platforms"] = selected_platforms
    settings["collector"]["top_limit"] = top_limit
    settings["collector"]["comment_limit"] = comment_limit
    settings["collector"]["concurrent_platforms"] = concurrent_platforms
    settings["collector"]["max_platform_workers"] = max_platform_workers
    
    settings["ai"]["concurrent_event_summaries"] = concurrent_summaries
    settings["ai"]["max_summary_workers"] = max_summary_workers
    
    settings["report"]["focus_limit"] = focus_limit
    
    save_settings(settings)
    st.session_state["run_pipeline"] = True
    st.rerun()

st.header("📄 抓取与总结结果")
if st.session_state.get("run_pipeline", False):
    with st.spinner("流水线运行中，正在抓取数据并调用大模型进行分析，请耐心等待..."):
        try:
            # Import and run here to avoid loading main pipeline until needed
            from src.main import run_pipeline
            # This triggers the standard workflow. It reads from config/settings.yaml and .env 
            # which we just saved.
            report_path = run_pipeline("manual")
            st.session_state["report_path"] = str(report_path)
            st.session_state["run_pipeline"] = False
            st.success("运行成功！")
        except Exception as e:
            st.error(f"运行发生错误: {str(e)}")
            st.session_state["run_pipeline"] = False

# 读取本地历史生成的 md 文件
import datetime
reports_dir = Path(settings.get("report", {}).get("output_dir", "data/reports"))
md_files = []
if reports_dir.exists():
    md_files = sorted(reports_dir.glob("*.md"), key=os.path.getmtime, reverse=True)

if not md_files:
    st.info("👈 暂无生成的历史报告。请在左侧边栏配置参数后，点击【保存配置并运行流水线】按钮。")
else:
    # 确定默认选中的索引 (如果刚刚生成了新报告，则默认选中该报告)
    default_index = 0
    if "report_path" in st.session_state and st.session_state["report_path"]:
        curr_path = Path(st.session_state["report_path"]).resolve()
        for i, f in enumerate(md_files):
            if f.resolve() == curr_path:
                default_index = i
                break
                
    st.markdown("### 📜 历史报告记录")
    selected_file = st.selectbox(
        "选择要查看的报告文件：", 
        md_files, 
        index=default_index, 
        format_func=lambda f: f"{f.name}  (生成时间: {datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime('%Y-%m-%d %H:%M:%S')})"
    )

    if selected_file and selected_file.exists():
        with open(selected_file, "r", encoding="utf-8") as f:
            content = f.read()
            
        import re
        toc = []
        for line in content.split('\n'):
            match = re.match(r'^(#{1,6})\s+(.*)', line)
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
                # Streamlit automatically creates anchor links for headers
                anchor = re.sub(r'[^\w\s-]', '', title).strip().lower().replace(' ', '-')
                # 使用标准的 4 个空格作为缩进，确保 Markdown 正确解析为嵌套的层级大纲
                indent = '    ' * (level - 1)
                toc.append(f"{indent}* [{title}](#{anchor})")
        
        # 注入 CSS 强制要求文字和代码块折行，防止撑破页面导致横向滚动
        
        st.markdown("""
        <style>
        .stMarkdown p, .stMarkdown div, .stMarkdown li {
            word-break: break-word;
            white-space: normal;
        }
        .stMarkdown pre, .stMarkdown code {
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # 判断是否有目录数据
        has_toc = bool(toc)
        
        # 判断是否有目录数据
        has_toc = bool(toc)
        
        if has_toc:
            # ==== 核心修复：直接在正文中埋入具备绝对定位特征的 HTML 锚点 ====
            # 放弃猜测 Streamlit 的不可靠 ID 生成器，自己为每个标题注入完美的 ID。
            new_content_lines = []
            html_toc_items = []
            toc_idx = 0
            
            for line in content.split('\n'):
                match = re.match(r'^(#{1,6})\s+(.*)', line)
                if match:
                    level = len(match.group(1))
                    title = match.group(2).strip()
                    anchor_id = f"custom-anchor-{toc_idx}"
                    
                    # 生成针对原生已知锚点的链接
                    html_toc_items.append(f"<li style='margin-left: {(level-1)*15}px; margin-bottom: 8px;'><a href='#{anchor_id}' target='_self' style='text-decoration:none; color:inherit; font-size:14px; display:block;'>{title}</a></li>")
                    
                    # 将锚点以内联 span 的形式直接插入到标题行内部，确保 Markdown 解析器仍然将其作为正常级层标题处理
                    new_line = f"{match.group(1)} <span id='{anchor_id}' style='position:relative; top:-70px; display:inline-block; height:0;'></span>{title}"
                    new_content_lines.append(new_line)
                    toc_idx += 1
                else:
                    new_content_lines.append(line)
                    
            # 用嵌入了原生锚点的新内容替换 content
            content = '\n'.join(new_content_lines)
            html_toc = "<ul style='list-style:none; padding-left:0;'>" + "\n".join(html_toc_items) + "</ul>"

            drawer_html = f"""
<style>
/* 隐藏原生checkbox */
#right-drawer-toggle {{
    display: none;
}}
/* 右侧触发按钮 */
.right-drawer-btn {{
    position: fixed;
    top: 4rem;
    right: 0;
    background: #f0f2f6;
    color: #31333F;
    padding: 10px 5px 10px 10px;
    border: 1px solid #d4d6db;
    border-right: none;
    border-radius: 8px 0 0 8px;
    cursor: pointer;
    z-index: 999999;
    font-size: 1.2rem;
    transition: right 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
    box-shadow: -2px 0 5px rgba(0,0,0,0.05);
}}
/* 抽屉本体 */
.right-drawer {{
    position: fixed;
    top: 0;
    right: -350px;
    width: 350px;
    height: 100vh;
    background: white;
    border-left: 1px solid #d4d6db;
    box-shadow: -4px 0 15px rgba(0,0,0,0.1);
    z-index: 999998;
    transition: right 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
    padding: 4.5rem 1.5rem 2rem 1.5rem;
    overflow-y: auto;
}}
/* 展开状态：抽屉划入 */
#right-drawer-toggle:checked ~ .right-drawer {{
    right: 0;
}}
/* 展开状态：按钮跟着向左移动 */
#right-drawer-toggle:checked ~ .right-drawer-btn {{
    right: 350px;
}}
/* 按钮图标切换：为了简化，这里用原生颜色 */
.right-drawer-btn:hover {{
    background: #e0e2e6;
}}
/* 适配暗黑模式 */
@media (prefers-color-scheme: dark) {{
    .right-drawer-btn, .right-drawer {{
        background-color: #262730;
        color: #fafafa;
        border-color: #3b3c43;
    }}
}}
.right-drawer a:hover {{
    color: #ff4b4b !important;
}}
</style>

<input type="checkbox" id="right-drawer-toggle">
<label for="right-drawer-toggle" class="right-drawer-btn" title="边缘滑动目录">
    <span>◀</span>
</label>
<div class="right-drawer">
    <h3 style="margin-top:0;">📑 页面导航</h3>
    <hr>
    {html_toc}
</div>
"""
            st.markdown(drawer_html, unsafe_allow_html=True)

        # 全尺寸释放主屏幕用于展示报告正文
        st.markdown(content, unsafe_allow_html=True)
    else:
        st.warning("所选报告文件不存在或已删除。")
