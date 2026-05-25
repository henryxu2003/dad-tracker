import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai

# 针对移动端优化页面配置 (Mobile-optimized page configuration)
st.set_page_config(
    page_title="爸爸的健康打卡", 
    layout="centered", 
    page_icon="☀️",
    initial_sidebar_state="collapsed"
)

# 隐藏Streamlit自带的无用菜单
hide_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

# 配置 Gemini API 密钥 (Ensure GEMINI_API_KEY is added to your Streamlit Advanced Secrets)
# --- API KEY 配置验证 ---
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    except Exception as e:
        st.error(f"遭遇接口配置错误: {e}")
else:
    st.warning("⚠️ 未检测到 API 密钥，AI 动态报告生成功能暂未启用。请在 Streamlit Secrets 中配置 GEMINI_API_KEY。")
    # 打印出当前系统能看到的键，帮助排查是不是拼写错误
    st.write("当前系统内检测到的密钥键名有:", list(st.secrets.keys()))
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.warning("⚠️ 未检测到 API 密钥，AI 动态报告生成功能暂未启用。请在 Streamlit Secrets 中配置 GEMINI_API_KEY。")

# 建立与 Google Sheets 的连接
conn = st.connection("gsheets", type=GSheetsConnection)

# 读取核心打卡数据 (Log 标签页)
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

# --- AI 动态指南报告生成函数 ---
def generate_ai_report(latest_metrics, weight_loss_pct):
    context = f"""
    患者状态背景：
    - 放疗类型：口腔癌放疗 (Stage 1-2 Oral Cancer)
    - 当前累计放疗剂量：{latest_metrics['Weight']} Gy
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
            tools=[{"google_search_retrieval": {}}]
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"🚨 今日基础报告已生成，但无法连接远程医学指南数据库进行深度动态预测。请对照历史看板和医生下发的纸质指南核对指标。"

# --- 页面导航标签 ---
tab1, tab2, tab3 = st.tabs(["📝 今日打卡", "📊 趋势看板", "🚨 预警历史"])

# ==========================================
# TAB 1: 每日数据登记与报告生成
# ==========================================
with tab1:
    st.subheader("☀️ 爸爸放疗护理每日登记")
    
    # 用于存储刚刚提交成功的数据，供页面即时渲染报告
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
        notes = st.text_area("日常备注 (例如：吃了什么、心情、特殊不适等)")
        submit = st.form_submit_button("💾 保存并生成今日报告", use_container_width=True)

    # 处理提交逻辑与智能预警触发
    if submit:
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 计算7天体重变化
        weight_loss_pct = 0.0
        if not df.empty:
            one_week_ago = datetime.now() - timedelta(days=7)
            past_entries = df[df['Date'] <= one_week_ago]
            if not past_entries.empty:
                baseline_weight = float(past_entries['Weight'].iloc[-1])
                weight_loss_pct = ((baseline_weight - float(weight)) / baseline_weight) * 100

        # 1. 保存打卡Log数据
        new_entry = pd.DataFrame([{
            'Date': current_time_str, 'Weight': float(weight), 'Fluids': int(fluids),
            'Dose': float(dose), 'Pain': int(pain), 'Saliva': int(saliva), 'Notes': str(notes)
        }])
        
        # 复制一份当前输入的数据字典作为报告入参
        report_metrics = {'Weight': weight, 'Fluids': fluids, 'Dose': dose, 'Pain': pain, 'Saliva': saliva, 'Notes': notes}
        
        if not df.empty:
            df['Date'] = df['Date'].dt.strftime('%Y-%m-%d %H:%M:%S')
        updated_df = pd.concat([df, new_entry], ignore_index=True)
        conn.update(worksheet="Log", data=updated_df)
        
        # 2. 传统静态警报审计与存储 (存入 Alerts 标签页)
        new_alerts = []
        if weight_loss_pct >= 2.0:
            new_alerts.append({'Date': current_time_str, 'Type': '🚨 体重危机', 'Message': f'体重周下滑{weight_loss_pct:.1f}%。'})
        if fluids < 1500:
            new_alerts.append({'Date': current_time_str, 'Type': '💧 饮水不足', 'Message': f'饮水量仅{fluids}mL，未达安全线。'})
        if pain >= 7:
            new_alerts.append({'Date': current_time_str, 'Type': '🛑 重度疼痛', 'Message': f'咽喉疼痛达到{pain}级。'})
        if saliva >= 7 or dose >= 30.0:
            new_alerts.append({'Date': current_time_str, 'Type': '👅 黏膜高危', 'Message': f'累计剂量{dose}Gy或口干达{saliva}级。'})
            
        if new_alerts:
            alert_df_new = pd.DataFrame(new_alerts)
            if not df_alerts.empty:
                df_alerts['Date'] = df_alerts_display = df_alerts['Date'].dt.strftime('%Y-%m-%d %H:%M:%S')
            updated_alerts = pd.concat([df_alerts, alert_df_new], ignore_index=True)
            conn.update(worksheet="Alerts", data=updated_alerts)
            
        # 3. 触发 AI 深度报告生成并缓存到会话状态中
        with st.spinner("🚀 正在结合 MASCC 最新临床指南，为您生成独家定制护理报告..."):
            st.session_state.latest_report = generate_ai_report(report_metrics, weight_loss_pct)
            st.session_state.just_submitted = True
            
        st.success("🎉 今日数据保存成功！报告已在下方生成。")

    # --- 报告展示区域 ---
    if st.session_state.just_submitted:
        st.markdown("---")
        st.subheader("📋 今日定制家属护理报告")
        st.info(st.session_state.latest_report)
        st.caption("💡 提示：您可以直接长按复制上方的整段文字，直接发到家庭微信群里，让所有人同步进度。")

# ==========================================
# TAB 2: 趋势看板 (CHARTS & TRENDS)
# ==========================================
with tab2:
    st.subheader("📊 身体指标趋势变化")
    
    if df.empty:
        st.info("暂无历史数据，请先进行每日打卡。")
    else:
        df_sorted = df.sort_values('Date')
        min_date = df_sorted['Date'].min().date()
        max_date = df_sorted['Date'].max().date()
        default_start = max(min_date, max_date - timedelta(days=7))
        
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
        
        st.markdown("**📉 体重 (lbs) 与 饮水量 (mL) 变化**")
        chart_data1 = filtered_df[['Weight', 'Fluids']]
        chart_data1.columns = ['体重 (lbs)', '饮水量 (mL)']
        st.line_chart(chart_data1, use_container_width=True)
        
        st.markdown("**📊 痛感与口干严重程度 (0-10)**")
        chart_data2 = filtered_df[['Pain', 'Saliva']]
        chart_data2.columns = ['疼痛级别', '口干级别']
        st.line_chart(chart_data2, use_container_width=True)
        
        st.markdown("**⚡ 累计放疗剂量增长曲线 (Gy)**")
        chart_data3 = filtered_df[['Dose']]
        chart_data3.columns = ['当前总剂量 (Gy)']
        st.line_chart(chart_data3, use_container_width=True)

# ==========================================
# TAB 3: 预警历史记录列表 (ALERT HISTORY)
# ==========================================
with tab3:
    st.subheader("🚨 历次触发的智能预警记录")
    
    if df_alerts.empty:
        st.success("✅ 至今为止没有任何异常预警，爸爸状态保持得很棒！")
    else:
        df_alerts_display = df_alerts.sort_values('Date', ascending=False).copy()
        df_alerts_display['Date'] = df_alerts_display['Date'].dt.strftime('%m月%d日 %H:%M')
        df_alerts_display.columns = ['触发时间', '预警类型', '护理及应对建议说明']
        st.dataframe(df_alerts_display, use_container_width=True, hide_index=True)
