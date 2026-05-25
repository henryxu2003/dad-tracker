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

# 隐藏Streamlit自带的无用菜单
hide_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
"""
st.markdown(hide_style, unsafe_allow_html=True)

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

# --- 页面导航标签 (TAB NAVIGATION FOR MOBILE) ---
tab1, tab2, tab3 = st.tabs(["📝 今日打卡", "📊 趋势看板", "🚨 预警记录"])

# ==========================================
# TAB 1: 每日数据登记表单
# ==========================================
with tab1:
    st.subheader("☀️ 爸爸放疗护理每日登记")
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
        notes = st.text_area("日常备注 (例如：吃了什么、心情等)")
        submit = st.form_submit_button("💾 保存并分享给家人", use_container_width=True)

    # 处理提交逻辑与智能预警触发
    if submit:
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 1. 保存打卡Log数据
        new_entry = pd.DataFrame([{
            'Date': current_time_str, 'Weight': float(weight), 'Fluids': int(fluids),
            'Dose': float(dose), 'Pain': int(pain), 'Saliva': int(saliva), 'Notes': str(notes)
        }])
        if not df.empty:
            df['Date'] = df['Date'].dt.strftime('%Y-%m-%d %H:%M:%S')
        updated_df = pd.concat([df, new_entry], ignore_index=True)
        conn.update(worksheet="Log", data=updated_df)
        
        # 2. 实时运算预警逻辑并保存触发的警报
        new_alerts = []
        
        # 计算7天体重变化
        if not df.empty:
            df_temp = pd.concat([df, new_entry], ignore_index=True)
            df_temp['Date'] = pd.to_datetime(df_temp['Date'])
            one_week_ago = datetime.now() - timedelta(days=7)
            past_entries = df_temp[df_temp['Date'] <= one_week_ago]
            if not past_entries.empty:
                baseline_weight = float(past_entries['Weight'].iloc[-1])
                weight_loss_pct = ((baseline_weight - float(weight)) / baseline_weight) * 100
                if weight_loss_pct >= 2.0:
                    new_alerts.append({'Date': current_time_str, 'Type': '🚨 体重危机', 'Message': f'体重周下滑{weight_loss_pct:.1f}%，请增加高热量流食并联系营养科。'})
        
        if fluids < 1500:
            new_alerts.append({'Date': current_time_str, 'Type': '💧 饮水不足', 'Message': f'饮水量仅{fluids}mL，未达1500mL安全线，存在脱水及黏膜恶化风险。'})
        if pain >= 7:
            new_alerts.append({'Date': current_time_str, 'Type': '🛑 重度疼痛', 'Message': f'咽喉疼痛达到{pain}级。进食前30分钟请务必使用止痛漱口水。'})
        if saliva >= 7 or dose >= 30.0:
            new_alerts.append({'Date': current_time_str, 'Type': '👅 黏膜高危', 'Message': f'累计剂量{dose}Gy或口干达{saliva}级。督促每日苏打水漱口4-6次并开加湿器。'})
            
        if new_alerts:
            alert_df_new = pd.DataFrame(new_alerts)
            if not df_alerts.empty:
                df_alerts['Date'] = df_alerts['Date'].dt.strftime('%Y-%m-%d %H:%M:%S')
            updated_alerts = pd.concat([df_alerts, alert_df_new], ignore_index=True)
            conn.update(worksheet="Alerts", data=updated_alerts)
            
        st.success("🎉 数据保存成功！")
        st.rerun()

# ==========================================
# TAB 2: 趋势看板 (CHARTS & TRENDS)
# ==========================================
with tab2:
    st.subheader("📊 身体指标趋势变化")
    
    if df.empty:
        st.info("暂无历史数据，请先进行每日打卡。")
    else:
        df_sorted = df.sort_values('Date')
        
        # 默认日期滑动条范围配置
        min_date = df_sorted['Date'].min().date()
        max_date = df_sorted['Date'].max().date()
        
        # 默认展示过去 7 天
        default_start = max(min_date, max_date - timedelta(days=7))
        
        # 日期筛选滑动条 (手机端可以拖拽自由缩放或滚动查看历史)
        start_date, end_date = st.slider(
            "📅 选择查看的日期范围:",
            min_value=min_date,
            max_value=max_date,
            value=(default_start, max_date),
            format="MM月DD日"
        )
        
        # 过滤数据
        filtered_df = df_sorted[
            (df_sorted['Date'].dt.date >= start_date) & 
            (df_sorted['Date'].dt.date <= end_date)
        ].copy()
        
        filtered_df = filtered_df.set_index('Date')
        
        # 图表 1: 体重与饮水量趋势
        st.markdown("**📉 体重 (lbs) 与 饮水量 (mL) 变化**")
        chart_data1 = filtered_df[['Weight', 'Fluids']]
        chart_data1.columns = ['体重 (lbs)', '饮水量 (mL)']
        st.line_chart(chart_data1, use_container_width=True)
        
        # 图表 2: 副作用严重程度趋势
        st.markdown("**📊 痛感与口干严重程度 (0-10)**")
        chart_data2 = filtered_df[['Pain', 'Saliva']]
        chart_data2.columns = ['疼痛级别', '口干级别']
        st.line_chart(chart_data2, use_container_width=True)
        
        # 图表 3: 放疗剂量积累累计
        st.markdown("**⚡ 累计放疗剂量增长曲线 (Gy)**")
        chart_data3 = filtered_df[['Dose']]
        chart_data3.columns = ['当前总剂量 (Gy)']
        st.line_chart(chart_data3, use_container_width=True)

# ==========================================
# TAB 3: 预警历史记录列表 (ALERT HISTORY)
# ==========================================
with tab3:
    st.subheader("🚨 历次触发的智能预警记录")
    st.write("这里记录了系统根据每日打卡数据自动识别出的所有健康风险提示：")
    
    if df_alerts.empty:
        st.success("✅ 至今为止没有任何异常预警，爸爸状态保持得很棒！")
    else:
        # 按最新时间倒序排列，方便第一眼看到最近发生的警告
        df_alerts_display = df_alerts.sort_values('Date', ascending=False).copy()
        df_alerts_display['Date'] = df_alerts_display['Date'].dt.strftime('%m月%d日 %H:%M')
        
        # 改成美观易读的表格表头展示
        df_alerts_display.columns = ['触发时间', '预警类型', '护理及应对建议说明']
        
        st.dataframe(df_alerts_display, use_container_width=True, hide_index=True)
