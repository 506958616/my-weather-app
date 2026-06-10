import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# 1. 설정 및 즐겨찾기 초기화
ST_VERSION = "V6.1 (Free API Only & Cross-Platform Stable)"
DEFAULT_PLACES = {
    "⛳ 군산 컨트리클럽": (35.895, 126.655),
    "🏠 우리집 (전주 기준)": (35.824, 127.148)
}

if "favorites" not in st.session_state:
    st.session_state["favorites"] = DEFAULT_PLACES.copy()

def get_current_location_by_ip():
    try:
        res = requests.get("https://ipapi.co/json/", timeout=3).json()
        return float(res["latitude"]), float(res["longitude"]), f"📍 현재 내 위치 ({res.get('city', '자동감지')})"
    except: return None, None, None

def get_coords_by_name(name):
    url = f"https://nominatim.openstreetmap.org/search?q={name}&format=json&limit=1"
    try:
        res = requests.get(url, headers={'User-Agent': 'WeatherApp/6.1'}, timeout=3).json()
        if res: return float(res[0]['lat']), float(res[0]['lon']), res[0]['display_name']
    except: return None, None, None

@st.cache_data(ttl=600)
def fetch_weather(lat, lon):
    # 무료 공용 API 고정 및 안정적인 필수 변수만 호출
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, 
        "longitude": lon,
        "hourly": "temperature_2m,apparent_temperature,precipitation,cloud_cover,cloud_cover_low,cloud_cover_mid,wind_speed_10m,uv_index",
        "timezone": "auto", 
        "forecast_days": 10
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# --- UI 구성 ---
st.set_page_config(page_title="Gunsan CC Weather V6.1", layout="centered")
st.caption(f"시스템 버전: {ST_VERSION}")
st.title("🎯 필드 그늘 & 위험지역 분석기")

with st.expander("📍 위치 설정 및 즐겨찾기 관리", expanded=False):
    mode = st.radio("위치 설정", ["자동 위치", "즐겨찾기", "장소 검색"], horizontal=True)
    lat, lon, d_name = DEFAULT_PLACES["⛳ 군산 컨트리클럽"][0], DEFAULT_PLACES["⛳ 군산 컨트리클럽"][1], "군산 컨트리클럽"

    if mode == "자동 위치":
        i_lat, i_lon, i_name = get_current_location_by_ip()
        if i_lat: lat, lon, d_name = i_lat, i_lon, i_name
    elif mode == "즐겨찾기":
        choice = st.selectbox("등록된 장소", list(st.session_state["favorites"].keys()))
        lat, lon = st.session_state["favorites"][choice]
        d_name = choice
    elif mode == "장소 검색":
        q = st.text_input("골프장명이나 지역명 입력", "")
        if q:
            s_lat, s_lon, s_name = get_coords_by_name(q)
            if s_lat:
                lat, lon, d_name = s_lat, s_lon, s_name
                if st.button("⭐ 즐겨찾기에 추가"):
                    st.session_state["favorites"][f"⭐ {q}"] = (lat, lon)
                    st.rerun()

st.info(f"🌐 기준: **{d_name}**")

data = fetch_weather(lat, lon)

if data and "hourly" in data:
    st.subheader("📅 분석 날짜 선택")
    
    # 💡 [핵심 수정] 명시적으로 pd.Series로 감싸 .dt 접근자 오류를 완벽하게 방지합니다.
    raw_times = pd.Series(pd.to_datetime(data["hourly"]["time"]))
    
    if raw_times.dt.tz is not None:
        raw_times = raw_times.dt.tz_localize(None)
        
    unique_dates = raw_times.dt.date.unique().tolist()
    selected_date = st.selectbox("예보 날짜를 선택하세요 (향후 10일)", options=unique_dates)

    df_hourly = pd.DataFrame({
        "시간_원본": raw_times,
        "기온": data["hourly"]["temperature_2m"],
        "체감온도": data["hourly"]["apparent_temperature"],
        "강수량": data["hourly"]["precipitation"],
        "전체구름량": data["hourly"]["cloud_cover"],
        "하층구름": data["hourly"]["cloud_cover_low"],
        "중층구름": data["hourly"]["cloud_cover_mid"],
        "지상풍속": data["hourly"]["wind_speed_10m"],
        "자외선": data["hourly"]["uv_index"]
    })

    df_day = df_hourly[df_hourly["시간_원본"].dt.date == selected_date].copy()
    
    # 핵심 지표 정밀 연산
    df_day["구름두께"] = ((df_day["하층구름"] + df_day["중층구름"]) / 2).round(1)
    df_day["그늘지속성"] = df_day["지상풍속"].apply(lambda x: max(0, min(100, int((1 - (x / 30)) * 100))))

    # 필드 주간 가동 시간 (오전 6시 ~ 오후 7시) 고정
    is_daytime = (df_day["시간_원본"].dt.hour >= 6) & (df_day["시간_원본"].dt.hour <= 19)
    df_day["정밀그늘확정"] = (df_day["구름두께"] >= 60) & (df_day["강수량"] == 0) & (df_day["자외선"] <= 3) & (df_day["그늘지속성"] >= 50) & is_daytime
    df_day["라운딩금지"] = is_daytime & ((df_day["체감온도"] >= 33.0) | ((df_day["구름두께"] <= 20) & (df_day["자외선"] >= 7)))

    df_day["표시시간"] = df_day["시간_원본"].dt.strftime("%H:00")
    df_day.set_index("표시시간", inplace=True)

    st.divider()
    
    # 상단 타임라인 대시보드 브리핑
    danger_hours = df_day[df_day["라운딩금지"] == True].index.tolist()
    best_shade = df_day[df_day["정밀그늘확정"] == True].index.tolist()

    if danger_hours:
        st.error(f"🛑 **열사병 위험 (라운딩 금지 시간대):** {', '.join(danger_hours)}")
    if best_shade:
        st.success(f"🌟 **태양 회피 최적 (명품 그늘 시간대):** {', '.join(best_shade)}")
    if not danger_hours and not best_shade:
        st.info("✅ 야외 활동에 극단적인 위험이나 특별한 그늘 호재가 없는 무난한 날씨입니다.")

    # 📱 모바일 최적화 고밀도 컬러 테이블 판넬
    st.subheader("📱 한눈에 보는 시간대별 컨디션 표")
    st.markdown("<p style='font-size:12px; color:gray; margin-top:-10px;'>※ 초록색 줄=그늘 찬스 / 빨간색 줄=열사병 위험 / 검은색 줄=보통</p>", unsafe_allow_html=True)

    def assign_status_text(row):
        if row["라운딩금지"]: return "🚨 위험(금지)"
        elif row["정밀그늘확정"]: return "🟢 그늘추천"
        else: return "보통"

    df_day["상태"] = df_day.apply(assign_status_text, axis=1)

    df_mobile = pd.DataFrame({
        "체감(℃)": df_day["체감온도"].round(1),
        "구름(%)": df_day["구름두께"].astype(int),
        "유지(점)": df_day["그늘지속성"],
        "자외선": df_day["자외선"].round(1),
        "현황": df_day["상태"]
    })

    def style_rows_by_condition(row):
        if "위험" in str(row["현황"]):
            return ['color: #D32F2F; font-weight: bold; background-color: #FFEBEE;'] * len(row)
        elif "그늘" in str(row["현황"]):
            return ['color: #2E7D32; font-weight: bold; background-color: #E8F5E9;'] * len(row)
        else:
            return ['color: #212121; font-weight: normal; background-color: #FFFFFF;'] * len(row)

    styled_mobile_df = df_mobile.style.apply(style_rows_by_condition, axis=1)
    st.dataframe(styled_mobile_df, use_container_width=True, height=520)

    # 하단 정밀 트렌드 차트
    st.divider()
    st.subheader("📉 정밀 예측 트렌드 그래프")
    tab1, tab2 = st.tabs(["☁️ 구름 밀도 및 상층풍 바람", "🌡️ 기온 변화 추이"])
    
    with tab1:
        st.bar_chart(df_day["구름두께"], color="#90A4AE")
        st.line_chart(df_day["그늘지속성"], color="#00E676")

    with tab2:
        st.line_chart(df_day[["기온", "체감온도"]])
else:
    st.error("⚠️ 데이터 로드에 실패했습니다. 공용 API 서버 상태를 확인해 주세요.")
