import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# 针对移动端优化页面配置 (Mobile-optimized page configuration)
st.set_page_config(
    page_title="爸爸的健康打卡", 
    layout="centered", 
    page_icon="☀️",
    initial_sidebar_state="collapsed"
)

# 隐藏Streamlit自带的右上角菜单和底部水印
hide_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

st.title("☀️ 爸爸放疗护理每日登记")
st.write("请每天填写以下指标，帮助全家随时掌握爸爸的状态并提早应对副作用。")

# 建立与 Google Sheets 的连接
conn = st.connection("gsheets", type=GSheetsConnection)

# 读取数据 (设置 0m 缓存，确保全家人在不同手机上能实时看到最新更新)
try:
    df = conn.read(worksheet="Log", ttl="0m")
    df = df.dropna(subset=['Date'])
    df['Date'] = pd.to_datetime(df['Date'])
except Exception as e:
    df = pd.DataFrame(columns=['Date', 'Weight', 'Fluids', 'Dose', 'Pain', 'Saliva', 'Notes'])

# --- 1. 每日打卡表单 (DAILY LOG FORM) ---
with st.form(key="log_form", clear_on_submit=True):
    st.subheader("📝 今日数据登记")
    
    # 移动端优化：在一行内紧凑显示核心数字输入
    col1, col2, col3 = st.columns(3)
    with col1:
        # 默认体重单位统一为 lbs
        last_weight = float(df['Weight'].iloc[-1]) if not df.empty else 150.0
        weight = st.number_input("体重 (lbs)", min_value=0.0, step=0.1, value=last_weight)
    with col2:
        fluids = st.number_input("今日饮水量 (mL)", min_value=0, step=50, value=2000)
    with col3:
        last_dose = float(df['Dose'].iloc[-1]) if not df.empty else 0.0
        # 添加带问号的悬停提示 (help 参数会自动在手机端右侧生成一个带问号的提示图标)
        dose = st.number_input(
            "累计放疗剂量 (Gy)", 
            min_value=0.0, 
            step=2.0, 
            value=last_dose,
            help="累计放疗剂量（单位：格雷 Gy）。每次放疗后，请把医生当天给的放疗剂量叠加到昨天的数字上（通常每次增加约 2.0 Gy）。"
        )
        
    st.markdown("---")
    st.markdown("**症状严重程度分级 (0 = 无症状, 10 = 极度严重)**")
    
    pain = st.slider("口腔/咽喉疼痛感", 0, 10, 0, help="吞咽或静止时的痛感")
    saliva = st.slider("唾液黏稠度 / 口干程度", 0, 10, 0, help="唾液是否变黏稠、拉丝或完全没有唾液")
    
    st.markdown("---")
    notes = st.text_area("日常备注 (例如：吃了什么、心情、医生交代的注意事项等)")
    
    submit = st.form_submit_button("💾 保存并分享给家人", use_container_width=True)

# --- 2. 提交数据处理 (SUBMIT HANDLING) ---
if submit:
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    new_entry = pd.DataFrame([{
        'Date': current_time,
        'Weight': float(weight),
        'Fluids': int(fluids),
        'Dose': float(dose),
        'Pain': int(pain),
        'Saliva': int(saliva),
        'Notes': str(notes)
    }])
    
    if not df.empty:
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d %H:%M:%S')
    updated_df = pd.concat([df, new_entry], ignore_index=True)
    
    conn.update(worksheet="Log", data=updated_df)
    st.success("🎉 数据保存成功！正在刷新看护看板...")
    st.rerun()

# --- 3. 智能预警与护理建议系统 (PREDICTIVE INSIGHTS) ---
if not df.empty:
    st.markdown("---")
    st.subheader("🚨 智能护理提醒")
    
    df = df.sort_values('Date')
    latest = df.iloc[-1]
    
    # 计算过去 7 天的体重变化率
    one_week_ago = datetime.now() - timedelta(days=7)
    past_entries = df[df['Date'] <= one_week_ago]
    
    if not past_entries.empty:
        baseline_weight = float(past_entries['Weight'].iloc[-1])
        weight_loss_pct = ((baseline_weight - float(latest['Weight'])) / baseline_weight) * 100
    else:
        weight_loss_pct = 0.0

    alert_triggered = False
    
    # 1. 体重预警
    if weight_loss_pct >= 2.0:
        st.error(f"⚠️ **体重严重下滑警告：** 爸爸的体重在过去一周内下降了 {weight_loss_pct:.1f}%。请考虑逐步增加高热量流食（如营养奶昔、恩敏舒等），并及时联系医院营养科医生。")
        alert_triggered = True
        
    # 2. 饮水预警
    if int(latest['Fluids']) < 1500:
        st.warning(f"💧 **饮水量不足提醒：** 今日饮水量仅为 {latest['Fluids']}mL（目标至少 2000mL）。水分不足会加重口腔黏膜溃疡。请督促爸爸尝试每小时小口小口地喝水、电解质水或清汤。")
        alert_triggered = True
        
    # 3. 疼痛预警
    if int(latest['Pain']) >= 7:
        st.error("🛑 **重度疼痛警告：** 爸爸反馈咽喉/口腔疼痛严重。请严格遵医嘱，在准备进食前 **30分钟** 使用利多卡因漱口水（如康复新液、重组人表皮生长因子或医院配制的止痛漱口水），帮助他顺利吞咽。")
        alert_triggered = True
        
    # 4. 放疗剂量累计与口腔黏膜预警
    if int(latest['Saliva']) >= 7 or float(latest['Dose']) >= 30.0:
        st.info("👅 **黏膜炎与口干高发期提示：** 累计放疗剂量已达高危期，或唾液已显著变稠。请务必监督爸爸坚持每天使用小苏打水/淡盐水含漱 4-6 次。同时在爸爸卧室里整晚开启空气加湿器，缓解夜间口干。")
        alert_triggered = True

    # 5. 状态良好提示
    if not alert_triggered:
        st.success("✅ 目前各项监测指标均在安全基线范围内，请继续保持细致看护！")

# --- 4. 历史记录预览 (HISTORY PREVIEW) ---
if not df.empty:
    st.markdown("---")
    st.subheader("📊 近期打卡历史")
    
    display_df = df.copy()
    display_df['Date'] = display_df['Date'].dt.strftime('%m月%d日')
    
    # 手机端只显示核心几列，避免横向滚动条太长
    mobile_display = display_df[['Date', 'Weight', 'Fluids', 'Dose', 'Pain', 'Saliva']].tail(7)
    
    # 将表格表头改为中文并将体重单位标注为 lbs
    mobile_display.columns = ['日期', '体重(lbs)', '饮水(mL)', '累计剂量(Gy)', '痛感', '口干']
    
    st.dataframe(mobile_display, use_container_width=True, hide_index=True)
