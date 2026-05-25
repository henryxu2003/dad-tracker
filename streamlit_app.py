import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
from google import genai
from google.genai import types

# ==========================================================
# 1. 移动端与界面配置 (MOBILE & INTERFACE CONFIGURATION)
# ==========================================================
st.set_page_config(
    page_title="爸爸的健康打卡", 
    layout="centered", 
    page_icon="☀️",
    initial_sidebar_state="collapsed"
)

# 彻底隐藏开发人员菜单、页眉、页脚 (全屏看护体验)
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
# 2. 新版 API 客户端配置验证 (NEW GENAI CLIENT INITIALIZATION)
# ==========================================================
client = None
if "GEMINI_API_KEY" in st.secrets:
    try:
        # 使用 Google 2026 最新官方标准客户端初始化
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    except Exception as e:
        st.error(f"AI 接口初始化失败: {e}")
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
# 4. 新版 AI 动态医疗报告生成器 (UPGRADED AI SEARCH ENGINE)
# ==========================================================
def generate_ai_report(latest_metrics, weight_loss_pct):
    if client is None:
        return "🚨 AI 客户端未就绪，无法生成动态报告。"

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
        # 换用新版 SDK 联网搜索生成语法
        response = client.models.generate_content(
            model='gemini-1.5-flash-002',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())] # 开启谷歌官方实时医学检索功能
            )
        )
        return response.text
    except Exception as e:
        return f"🚨 调试模式显性错误捕捉: {str(e)}"

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
        submit = st.form_submit_button("💾 保存并生成今日报告", width='stretch')

    if submit:
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 计算过去 7 天体重变化趋势
        weight_loss_pct = 0.0
        if not df.empty:
            one_week_ago = datetime.now() - timedelta(days=7)
            past_entries = df[df['Date'] <= one_week_ago]
            if not past_entries.empty:
                baseline_weight = float(past_entries['Weight'].iloc[-1])
                weight_loss_pct = ((baseline_weight - float(weight)) / baseline_weight) * 100

        # 构建新打卡记录
        new_entry = pd.DataFrame([{
            'Date': current_time_str, 'Weight': float(weight), 'Fluids': int(fluids),
            'Dose': float(dose), 'Pain': int(pain), 'Saliva': int(saliva), 'Notes': str(notes)
        }])
        
        report_metrics = {'Weight': weight, 'Fluids': fluids, 'Dose': dose, 'Pain': pain, 'Saliva': saliva, 'Notes': notes}
        
        # 预清理历史数据的 Date 格式
        if not df.empty:
            df['Date'] = df['Date'].dt.strftime('%Y-%m-%d %H:%M:%S')
            
        # 合并并转换格式为纯文本，彻底防范类型解析崩溃
        updated_df = pd.concat([df, new_entry], ignore_index=True)
        updated_df = updated_df.astype(str)
        
        # 保存主打卡记录至 Google Sheets
        conn.update(worksheet="Log", data=updated_df)
        
        # 静态警报档案建立
        new_alerts = []
        if weight_loss_pct >= 2.0:
            new_alerts.append({'Date': current_time_str, 'Type': '🚨 体重危机', 'Message': f'体重周下滑{weight_loss_pct:.1f}%。'})
        if fluids < 1500:
            new_alerts.append({'Date': current_time_str, 'Type': '💧 饮水不足', 'Message': f'饮水量仅{fluids}mL，跌破安全线。'})
        if pain >= 7:
            new_alerts.append({'Date': current_time_str, 'Type': '🛑 重度疼痛', 'Message': f'咽喉疼痛剧烈达到{pain}级。'})
        if saliva >= 7 or dose >= 30.0:
            new_alerts.append({'Date': current_time_str, 'Type': '👅 黏膜高危', 'Message': f'累计放疗剂量已达{dose}Gy或口干达{saliva}级。'})
            
        if new_alerts:
            alert_df_new = pd.DataFrame(new_alerts)
            if not df_alerts.empty:
                df_alerts['Date'] = df_alerts['Date'].dt.strftime('%Y-%m-%d %H:%M:%S')
            updated_alerts = pd.concat([df_alerts, alert_df_new], ignore_index=True)
            updated_alerts = updated_alerts.astype(str)
            conn.update(worksheet="Alerts", data=updated_alerts)
            
        # 触发新版 RAG 智能看护指南生成
        if client is not None:
            with st.spinner("🚀 正在结合 MASCC / ASCO 最新临床指南生成今日护理报告..."):
                st.session_state.latest_report = generate_ai_report(report_metrics, weight_loss_pct)
                st.session_state.just_submitted = True
        
        st.success("🎉 数据保存成功！")
        st.rerun()

    # 显示今日即时看护报告
    if st.session_state.just_submitted:
        st.markdown("---")
        st.subheader("📋 今日定制家属护理报告")
        st.info(st.session_state.latest_report)

# ----------------------------------------------------------
# TAB 2: 趋势看板 (CHARTS & TRENDS VISUALIZATION)
# ----------------------------------------------------------
with tab2:
    st.subheader("📊 身体指标趋势变化")
    
    if df.empty:
        st.info("暂无历史数据，请先进行每日打卡。")
    else:
        df_sorted = df.sort_values('Date')
        min_date = df_sorted['Date'].min().date()
        max_date = df_sorted['Date'].max().date()
        
        # --- 修复核心：如果数据只有1天，强制把滑块下限挪到前一天，防止两值相等闪退 ---
        if min_date == max_date:
            min_date = min_date - timedelta(days=1)
            
        default_start = max(min_date, max_date - timedelta(days=7))
        
        # 可滑动日期滚轴
        start_date, end_date = st.slider(
            "📅 选择查看的日期范围:",
            min_value=min_date, max_value=max_date,
            value=(default_start, max_date), format="MM月DD日"
        )
        
        filtered_df = df_sorted[
            (df_sorted['Date'].dt.date >= start_date) & 
            (df_sorted['Date'].dt.date <= end_date)
        ].copy()
        
        filtered_df = filtered_df.set_index('Date')
        
        filtered_df['Weight'] = filtered_df['Weight'].astype(float)
        filtered_df['Fluids'] = filtered_df['Fluids'].astype(float)
        filtered_df['Pain'] = filtered_df['Pain'].astype(float)
        filtered_df['Saliva'] = filtered_df['Saliva'].astype(float)
        filtered_df['Dose'] = filtered_df['Dose'].astype(float)
        
        st.markdown("**跌幅与补水监测：体重 (lbs) 与 饮水量 (mL) 变化**")
        chart_data1 = filtered_df[['Weight', 'Fluids']]
        chart_data1.columns = ['体重 (lbs)', '饮水量 (mL)']
        st.line_chart(chart_data1)
        
        st.markdown("**症状监控：痛感与口干程度严重分级 (0-10)**")
        chart_data2 = filtered_df[['Pain', 'Saliva']]
        chart_data2.columns = ['疼痛级别', '口干级别']
        st.line_chart(chart_data2)
        
        st.markdown("**辐射积累：累计放疗总剂量增长曲线 (Gy)**")
        chart_data3 = filtered_df[['Dose']]
        chart_data3.columns = ['当前总剂量 (Gy)']
        st.line_chart(chart_data3)

# ----------------------------------------------------------
# TAB 3: 历史触发警报档案 (AUDITED ALERT HISTORY LOG)
# ----------------------------------------------------------
with tab3:
    st.subheader("🚨 历次触发的智能预警记录")
    
    if df_alerts.empty:
        st.success("✅ 至今为止没有任何异常预警，爸爸指标维持得很好！")
    else:
        df_alerts_display = df_alerts.sort_values('Date', ascending=False).copy()
        df_alerts_display['Date'] = df_alerts_display['Date'].dt.strftime('%m月%d日 %H:%M')
        df_alerts_display.columns = ['触发时间', '预警类型', '系统生成高危风险护理说明']
        st.dataframe(df_alerts_display, width='stretch', hide_index=True)
