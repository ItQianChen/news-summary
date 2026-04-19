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

if "report_path" in st.session_state and st.session_state["report_path"]:
    report_file = Path(st.session_state["report_path"])
    if report_file.exists():
        with open(report_file, "r", encoding="utf-8") as f:
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
                indent = '&nbsp;&nbsp;&nbsp;&nbsp;' * (level - 1)
                toc.append(f"{indent}- [{title}](#{anchor})")
        
        if toc:
            with st.expander("📑 问题与事件目录", expanded=True):
                st.markdown('\n'.join(toc), unsafe_allow_html=True)
                
        # 增加换行：在普通换行处添加两个空格强制 Markdown 换行
        # 避免替换已经是两个空格的换行
        content = content.replace("  \n", "\n").replace("\n", "  \n")
        st.markdown(content, unsafe_allow_html=True)
    else:
        st.warning("报告文件未找到。")
else:
    st.info("👈 请在左侧边栏配置参数后，点击【保存配置并运行流水线】按钮。")
