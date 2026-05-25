import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai

# ==========================================================
# 1. 移动端与界面配置 (MOBILE & INTERFACE CONFIGURATION)
# ==========================================================
st.set_page_config(
    page_title="爸爸的健康打卡", 
    layout="centered", 
    page_icon="☀️",
    initial_sidebar_state="collapsed"
)

# 彻底隐藏开发人员菜单、页眉、页脚以及右下角的 Manage App 按钮 (全屏体验)
hide_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display:none !important;}
    button[data-testid="stActionButton"] {display: none !important;}
    </style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# ==========================================================
# 2. API 密钥配置验证 (API KEY VERIFICATION)
# ==========================================================
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    except Exception as e:
        st.error(f"遭遇接口配置错误: {e}")
else:
    st.warning("⚠️ 未检测到 API 密钥，AI 动态报告生成功能暂未启用。请在 Streamlit Secrets 中配置 GEMINI_API_KEY。")

# ==========================================================
# 3. 数据库连接与读取 (DATA RETRIEVAL FROM GOOGLE SHEETS)
# ==========================================================
conn = st.connection("gsheets", type=GSheetsConnection)

# 读取打卡主数据 (Log 标签页)
try:
    df = conn.read(worksheet="Log", ttl="0m")
    df = df.dropna(subset=['Date'])
    df['Date'] = pd.to_datetime(df['Date'])
except Exception as e:
    df = pd.DataFrame(columns=['Date', 'Weight', 'Fluids', 'Dose', 'Pain', 'Saliva', 'Notes'])

# 读取历史预警数据 (Alerts 标签页)
try:
    df_alerts = conn.read(worksheet="Alerts", ttl="0m")
    df_alerts = df_alerts.dropna(subset=['Date'])
    df_alerts['Date'] = pd.to_datetime(df_alerts['Date'])
except Exception as e:
    df_alerts = pd.DataFrame(columns=['Date', 'Type', 'Message'])

# ==========================================================
# 4. AI 动态医疗指南报告生成器 (AI RAG ENGINE WITH SEARCH)
# ==========================================================
def generate_ai_report(latest_metrics, weight_loss_pct):
    context = f"""
    患者状态背景：
    - 放疗类型：口腔癌放疗 (Stage 1-2 Oral Cancer)
    - 当前累计放疗剂量：{latest_metrics['Dose']} Gy
    - 今日体重：{latest_metrics['Weight']} lbs (过去一周体重变化率：{weight_loss_pct:.1f}%)
    - 今日饮水量：{latest_metrics['Fluids']} mL
    - 口腔疼痛级别 (0-10)：{latest_metrics['Pain']}
    - 唾液黏稠/口干级别 (0-10)：{latest_metrics['Saliva']}
    - 今日看护备注：{latest_metrics['Notes']}
    """
    
    prompt = f"""
    你是一位专门从事头颈部癌症支持治疗的临床护理专家。
    请根据以下患者今日录入的数据，结合MASCC（癌症支持治疗多国协会）和ASCO最新的临床看护指南进行联网检索，并生成一份结构化的【今日护理日报】。
    
    {context}
    
    请严格以下列格式输出（使用简洁的简体中文，方便家属在微信/手机群聊中转发阅读）：
    
    核心指标摘要：
    - 📅 报告日期：{datetime.now().strftime('%m月%d日')}
    - ⚖️ 今日体重：{latest_metrics['Weight']} lbs (对比上周：{'下滑' if weight_loss_pct > 0 else '变化'}{abs(weight_loss_pct):.1f}%)
    - 💧 今日饮水：{latest_metrics['Fluids']} mL
    - ⚡ 累计剂量：{latest_metrics['Dose']} Gy
    
    🚨 智能风险预警与预测：
    [请根据当前放疗剂量阶段及指标变化，指出接下来2-3天最需要防范的并发症预测和警告]
    
    🛠️ 今日核心护理行动方案 (基于权威指南)：
    [请基于MASCC/ASCO最新指南，给出具体的行动指令。例如：特定成分漱口水频率、饮食质地建议、止痛药时间安排、睡眠加湿等]
    
    ⚠️ 紧急就医红线提醒：
    [列出家属今明两天需要严密监控的危险症状，一旦超过必须立即联系主管医生或看护护士]
    """
    try:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            tools=[{"google_search_retrieval": {}}] # 开启实时医学数据库检索
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"🚨 今日基础数据已成功保存。但由于远程医学指南数据库连接超时，动态AI预测暂不可用。请参照趋势看板和医院下发的纸质医嘱核对指标。"

# ==========================================================
# 5. 页面多标签页导航 (APP TABS FOR PHONE SCREENS)
# ==========================================================
tab1, tab2, tab3 = st.tabs(["📝 今日打卡", "📊 趋势看板", "🚨 预警历史"])

# ----------------------------------------------------------
# TAB 1: 每日数据登记与实时报告
# ----------------------------------------------------------
with tab1:
    st.subheader("☀️ 爸爸放疗护理每日登记")
    
    if 'just_submitted' not in st.session_state:
        st.session_state.just_submitted = False
        st.session_state.latest_report = ""

    with st.form(key="log_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            last_weight = float(df['Weight'].iloc[-1]) if not df.empty else 150.0
            weight = st.number_input("体重 (lbs)", min_value=0.0, step=0.1, value=last_weight)
        with col2:
            fluids = st.number_input("今日饮水量 (mL)", min_value=0, step=50, value=2000)
        with col3:
            last_dose = float(df['Dose'].iloc[-1]) if not df.empty else 0.0
            dose = st.number_input(
                "累计放疗剂量 (Gy)", 
                min_value=0.0, 
                step=2.0, 
                value=last_dose,
                help="每次放疗后，请把医生当天给的放疗剂量叠加到昨天的数字上（通常每次增加约 2.0 Gy）。"
            )
            
        st.markdown("---")
        st.markdown("**症状严重程度分级 (0 = 无症状, 10 = 极度严重)**")
        pain = st.slider("口腔/咽喉疼痛感", 0, 10, 0)
        saliva = st.slider("唾液黏稠度 / 口干程度", 0, 10, 0)
        
        st.markdown("---")
        notes = st.text_area("日常备注 (例如：吃了什么、心情、特殊情况等)")
        submit = st.form_submit_
