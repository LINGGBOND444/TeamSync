"""TeamSync — 会议记录转 Jira 任务，基于 Streamlit + DeepSeek API。"""

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from llm_client import generate_tasks
from prompt_engine import EXAMPLE_TRANSCRIPT, SYSTEM_PROMPT, build_user_prompt

load_dotenv()

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def save_result(tasks: list[dict], metadata: dict) -> str:
    """将生成结果保存到 results/ 目录，返回文件路径。

    文件名格式：teamsync_YYYY-MM-DD_HH-MM-SS_P0{n}-P1{n}-P2{n}_T{total}.json
    """
    p0 = sum(1 for t in tasks if t.get("priority") == "P0")
    p1 = sum(1 for t in tasks if t.get("priority") == "P1")
    p2 = sum(1 for t in tasks if t.get("priority") == "P2")
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"teamsync_{ts}_P0{p0}-P1{p1}-P2{p2}_T{len(tasks)}.json"
    filepath = RESULTS_DIR / filename
    payload = {"generated_at": ts, "model": metadata.get("model", ""), "tasks": tasks}
    filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(filepath)

st.set_page_config(
    page_title="TeamSync - 会议记录转Jira任务",
    page_icon="🔄",
    layout="wide",
)

st.title("🔄 TeamSync")
st.caption("粘贴会议记录，AI 自动提取结构化 Jira 任务")


# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 配置")

    env_key = os.getenv("DEEPSEEK_API_KEY", "")

    api_key = st.text_input(
        "DeepSeek API Key",
        type="password",
        value=env_key,
        placeholder="sk-...",
        help="在 https://platform.deepseek.com/api_keys 获取。也可写入 .env 文件免去每次输入。",
    )
    if api_key:
        os.environ["DEEPSEEK_API_KEY"] = api_key

    model = st.selectbox(
        "模型选择",
        options=["deepseek-v4-flash", "deepseek-v4-pro"],
        index=0,
        help="deepseek-v4-flash 推荐日常使用（快）；deepseek-v4-pro 质量最高（较慢）。",
    )

    st.divider()
    st.header("💡 使用说明")
    st.caption(
        "1. 粘贴会议记录到左侧文本框\n"
        "2. 点击「生成任务」按钮\n"
        "3. 检查并编辑生成的任务\n"
        "4. 下载 JSON/CSV 文件，导入 Jira"
    )
    st.caption("示例会议记录已内置，点击文本框下方的按钮即可填入。")

    st.divider()
    st.header("⚠️ 注意事项")
    st.caption("会议记录会发送至 DeepSeek 服务器处理，请勿包含敏感信息。")
    st.caption("AI 可能偶尔出错，请在导入 Jira 前人工核对任务列表。")


# ── Session State 初始化 ─────────────────────────────────────────────
defaults = {
    "transcript": "",
    "tasks": [],
    "metadata": {},
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ── 两列布局 ─────────────────────────────────────────────────────────
left, right = st.columns([1, 1])

# ── 左栏：输入区 ─────────────────────────────────────────────────────
with left:
    st.subheader("📝 会议记录")

    if st.button("📋 填入示例会议记录", use_container_width=True):
        st.session_state.transcript = EXAMPLE_TRANSCRIPT

    transcript = st.text_area(
        "粘贴你的会议记录",
        value=st.session_state.transcript,
        height=420,
        placeholder=(
            "在此粘贴会议记录...\n\n"
            "支持任何格式：逐字稿、会议纪要、聊天记录等。\n"
            "AI 会自动识别其中的待办事项和行动项。"
        ),
        key="transcript_area",
        label_visibility="collapsed",
    )
    st.session_state.transcript = transcript

    c1, c2 = st.columns([1, 1])
    c1.caption(f"已输入 {len(transcript)} 字符")
    if transcript:
        c2.caption(f"约 {len(transcript) // 2} 个中文词")

    can_generate = bool(transcript.strip() and api_key)
    if st.button("🚀 生成任务", type="primary", use_container_width=True, disabled=not can_generate):
        with st.spinner("AI 正在分析会议记录..."):
            try:
                tasks, metadata = generate_tasks(
                    transcript,
                    SYSTEM_PROMPT,
                    build_user_prompt,
                    model=model,
                    max_retries=2,
                )
                st.session_state.tasks = tasks
                st.session_state.metadata = metadata
                saved_path = save_result(tasks, metadata)
                st.success(f"成功生成 {len(tasks)} 个任务（已保存至 {saved_path}）")
            except Exception as exc:
                st.error(f"生成失败：{exc}")


# ── 右栏：结果区 ─────────────────────────────────────────────────────
with right:
    st.subheader("📋 生成的任务")

    tasks = st.session_state.tasks
    metadata = st.session_state.metadata

    if tasks:
        # 统计
        p0 = sum(1 for t in tasks if t.get("priority") == "P0")
        p1 = sum(1 for t in tasks if t.get("priority") == "P1")
        p2 = sum(1 for t in tasks if t.get("priority") == "P2")
        stats = st.columns(4)
        stats[0].metric("总计", len(tasks))
        stats[1].metric("P0 紧急", p0)
        stats[2].metric("P1 核心", p1)
        stats[3].metric("P2 优化", p2)

        # 数据编辑器
        df = pd.DataFrame(tasks)
        col_order = [
            "title", "description", "assignee",
            "priority", "due_date", "confirmation_notes",
        ]
        df = df[[c for c in col_order if c in df.columns]]

        edited = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "title": st.column_config.TextColumn("标题", width="medium"),
                "description": st.column_config.TextColumn("描述", width="large"),
                "assignee": st.column_config.TextColumn("负责人", width="small"),
                "priority": st.column_config.SelectboxColumn(
                    "优先级",
                    options=["P0", "P1", "P2"],
                    width="small",
                ),
                "due_date": st.column_config.TextColumn("截止日", width="small"),
                "confirmation_notes": st.column_config.TextColumn("待确认项", width="medium"),
            },
            height=420,
            hide_index=True,
        )

        st.session_state.tasks = edited.to_dict("records")

        # 导出
        st.divider()
        st.subheader("📤 导出")

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_bytes = json.dumps(
            st.session_state.tasks, ensure_ascii=False, indent=2
        ).encode("utf-8")

        btn_cols = st.columns(3)
        btn_cols[0].download_button(
            "⬇ 下载 JSON",
            data=json_bytes,
            file_name=f"teamsync_tasks_{now}.json",
            mime="application/json",
            use_container_width=True,
        )
        csv_bytes = pd.DataFrame(st.session_state.tasks).to_csv(index=False).encode("utf-8-sig")
        btn_cols[1].download_button(
            "⬇ 下载 CSV",
            data=csv_bytes,
            file_name=f"teamsync_tasks_{now}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        # 复制 JSON（展示在代码块中，自带复制按钮）
        with btn_cols[2].popover("📋 复制 JSON"):
            st.code(json.dumps(st.session_state.tasks, ensure_ascii=False, indent=2), language="json")
            st.caption("选中全部文本后 Ctrl+C 复制")

        # Token 用量
        if metadata:
            st.caption(
                f"模型：{metadata.get('model', '-')} | "
                f"输入 Token：{metadata.get('input_tokens', '-')} | "
                f"输出 Token：{metadata.get('output_tokens', '-')} | "
                f"重试次数：{metadata.get('attempts', 1) - 1}"
            )
    else:
        st.info(
            "👈 在左侧粘贴会议记录后点击「生成任务」，"
            "AI 会自动提取结构化的 Jira 任务清单。"
        )

# ── Footer ───────────────────────────────────────────────────────────
st.divider()
st.caption("TeamSync MVP — 基于 Streamlit + DeepSeek API 构建")
