import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Dad's Care Dashboard", layout="centered", page_icon="☀️")

st.title("☀️ Dad's Treatment & Symptom Tracker")
st.write("Enter daily metrics below to keep the family aligned and spot trends early.")

# Establish connection with the Google Sheet
conn = st.connection("gsheets", type=GSheetsConnection)

# Read the data dynamically without caching so all family members see changes instantly
try:
    df = conn.read(worksheet="Log", ttl="0m")
    # Clean up any totally empty rows
    df = df.dropna(subset=['Date'])
    df['Date'] = pd.to_datetime(df['Date'])
except Exception as e:
    # Fallback structure if the sheet is freshly made or parsing fails
    df = pd.DataFrame(columns=['Date', 'Weight', 'Fluids', 'Dose', 'Pain', 'Saliva', 'Notes'])

# --- 1. DAILY LOG FORM ---
with st.form(key="log_form", clear_on_submit=True):
    st.subheader("📝 New Daily Entry")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        # Defaults to last recorded weight or 70 if empty
        last_weight = float(df['Weight'].iloc[-1]) if not df.empty else 70.0
        weight = st.number_input("Weight (kg or lbs)", min_value=0.0, step=0.1, value=last_weight)
    with col2:
        fluids = st.number_input("Fluid Intake Today (mL)", min_value=0, step=50, value=2000)
    with col3:
        last_dose = float(df['Dose'].iloc[-1]) if not df.empty else 0.0
        dose = st.number_input("Cumulative Dose (Gy)", min_value=0.0, step=2.0, value=last_dose)
        
    st.markdown("**Symptom Severity (0 = No Symptoms, 10 = Severe)**")
    col4, col5 = st.columns(2)
    with col4:
        pain = st.slider("Mouth / Throat Pain", 0, 10, 0)
    with col5:
        saliva = st.slider("Saliva Thickness / Dryness", 0, 10, 0)
        
    notes = st.text_area("Care Notes (Food styles, mood, or items discussed with doctor)")
    submit = st.form_submit_button("Save Entry & Share")

# --- 2. HITTING SUBMIT ---
if submit:
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Format perfectly matching our Google Sheet header
    new_entry = pd.DataFrame([{
        'Date': current_time,
        'Weight': float(weight),
        'Fluids': int(fluids),
        'Dose': float(dose),
        'Pain': int(pain),
        'Saliva': int(saliva),
        'Notes': str(notes)
    }])
    
    # Clean historical df and append new entry
    if not df.empty:
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d %H:%M:%S')
    updated_df = pd.concat([df, new_entry], ignore_index=True)
    
    # Push back up to Google Sheets securely
    conn.update(worksheet="Log", data=updated_df)
    st.success("🎉 Data successfully saved! Refreshing dashboard...")
    st.rerun()

# --- 3. PREDICTIVE INSIGHTS ENGINE ---
if not df.empty:
    st.markdown("---")
    st.subheader("🚨 Care System Alerts")
    
    df = df.sort_values('Date')
    latest = df.iloc[-1]
    
    # Calculate 7-day weight loss trends
    one_week_ago = datetime.now() - timedelta(days=7)
    past_entries = df[df['Date'] <= one_week_ago]
    
    if not past_entries.empty:
        baseline_weight = float(past_entries['Weight'].iloc[-1])
        weight_loss_pct = ((baseline_weight - float(latest['Weight'])) / baseline_weight) * 100
    else:
        weight_loss_pct = 0.0

    alert_triggered = False
    
    if weight_loss_pct >= 2.0:
        st.error(f"⚠️ **Critical Weight Alert:** Dad has dropped {weight_loss_pct:.1f}% of his body weight over the past week. Consider switching to high-calorie liquid meals (shakes/smoothies) and inform his clinical dietitian.")
        alert_triggered = True
        
    if int(latest['Fluids']) < 1500:
        st.warning(f"💧 **Low Hydration Warning:** Fluid intake is currently {latest['Fluids']}mL. Target is 2000mL+. Encourage small, scheduled sips of water, bone broth, or electrolyte fluids every waking hour.")
        alert_triggered = True
        
    if int(latest['Pain']) >= 7:
        st.error("🛑 **Severe Pain Alert:** Mouth pain is rated high. Ensure prescribed oral rinses (like magic mouthwash) are being administered exactly 30 minutes before meal attempts to assist with swallowing.")
        alert_triggered = True
        
    if int(latest['Saliva']) >= 7 or float(latest['Dose']) >= 30.0:
        st.info("👅 **Mucositis / Radiation Threshold Alert:** Cumulative dose is stacking up. Ensure strict adherence to non-alcoholic baking soda/saltwater mouth rinses 4-6 times daily and keep an active humidifier in his bedroom.")
        alert_triggered = True

    if not alert_triggered:
        st.success("✅ All metrics currently hold within safe baseline tracking. Keep up the consistent care!")

    # --- 4. HISTORY PREVIEW ---
    st.markdown("---")
    st.subheader("📊 Recent Log History")
    # Format the date column beautifully for the family to read
    display_df = df.copy()
    display_df['Date'] = display_df['Date'].dt.strftime('%b %d, %Y')
    st.dataframe(display_df.tail(10), use_container_width=True, hide_index=True)
