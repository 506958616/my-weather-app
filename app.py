import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# 1. 설정 및 즐겨찾기 초기화
ST_VERSION = "V5.1 (Perfect Mobile Edition)"
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
        res = requests.get(url, headers={'User-Agent': 'WeatherApp/5.1'}, timeout=3).json()
        if res: return float(res[0]['lat']), float(res[0]['lon']), res[0]['display_name']
    except: return None, None, None

@st.cache_data(ttl=600)
def fetch_weather(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "temperature_2m,apparent_temperature,precipitation,cloud_cover,cloud_cover_low,cloud_cover_mid,wind_speed_10m,wind_speed_850hpa,uv_index",
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": "auto", "forecast_days": 10
    }
    return requests.get(url, params=params).json()

# --- UI 구성 ---
st.set_page_config(page_title="Gunsan CC Weather V5.1", layout="centered")
# [수정 완료] 오타 원천 차단
st.markdown(f"<p style='text-align:right; color:gray; font-size:10px;'>{ST_VERSION}</p>", unsafe_allow_html=True)
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

if data:
    st.subheader("📅 분석 날짜 선택")
    daily_dates = data["daily"]["time"]
    selected_date_str = st.select_slider("예보 날짜를 선택하세요 (향후 10일)", options=daily_dates)
    selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()

    raw_times = pd.to_datetime(data["hourly"]["time"])
    if raw_times.tz is not None:
        raw_times = raw_times.dt.tz_localize(None)

    df_hourly = pd.DataFrame({
        "시간_원본": raw_times,
        "기온": data["hourly"]["temperature_2m"],
        "체감온도": data["hourly"]["apparent_temperature"],
        "강수량": data["hourly"]["precipitation"],
        "전체구름량": data["hourly"]["cloud_cover"],
        "하층구름": data["hourly"]["cloud_cover_low"],
        "중층구름": data["hourly"]["cloud_cover_mid"],
        "상층풍속": data["hourly"]["wind_speed_850hpa"],
        "지상풍속": data["hourly"]["wind_speed_10m"],
        "자외선": data["hourly"]["uv_index"]
    })

    df_day = df_hourly[df_hourly["시간_원본"].dt.date == selected_date].copy()
    
    # 지표 엔진 계산
    df_day["구름두께"] = ((df_day["하층구름"] + df_day["중층구름"]) / 2).round(1)
    df_day["그늘지속성"] = df_day["상층풍속"].apply(lambda x: max(0, min(100, int((1 - (x / 50)) * 100))))

    # 조건 매칭 (06:00 ~ 19:00 주간 기준)
    is_daytime = (df_day["시간_원본"].dt.hour >= 6) & (df_day["시간_원본"].dt.hour <= 19)
    df_day["정밀그늘확정"] = (df_day["구름두께"] >= 60) & (df_day["강수량"] == 0) & (df_day["자외선"] <= 3) & (df_day["그늘지속성"] >= 50) & is_daytime
    df_day["라운딩금지"] = is_daytime & ((df_day["체감온도"] >= 33.0) | ((df_day["구름두께"] <= 20) & (df_day["자외선"] >= 7)))

    def assign_status_text(row):
        if row["라운딩금지"]: return "🚨 위험"
        elif row["정밀그늘확정"]: return "🟢 추천"
        else: return "보통"

    df_day["상태"] = df_day.apply(assign_status_text, axis=1)

    # [수정] 모바일용 데이터프레임 분할 및 시간 포맷팅 안정화
    df_mobile = df_day[is_daytime].copy()
    
    df_day["표시시간"] = df_day["시간_원본"].dt.strftime("%H:00")
    df_day.set_index("표시시간", inplace=True)

    df_mobile["표시시간"] = df_mobile["시간_원본"].dt.strftime("%H:00")
    df_mobile.set_index("표시시간", inplace=True)

    # 상단 카드 요약 브리핑
    danger_hours = df_day[df_day["라운딩금지"] == True].index.tolist()
    best_shade = df_day[df_day["정밀그늘확정"] == True].index.tolist()

    st.divider()
    if danger_hours:
        st.error(f"🛑 **열사병 위험 (라운딩 금지 권장):** {', '.join(danger_hours)}")
    if best_shade:
        st.success(f"🌟 **안전 보장 (명품 그늘 시간대):** {', '.join(best_shade)}")
    if not danger_hours and not best_shade:
        st.info("✅ 극단적인 폭염 위험이나 완벽한 그늘이 없는 무난한 보통 날씨입니다.")

    # 📊 시간대별 컬러 코딩 요약 표
    st.subheader("📱 한눈에 보는 시간대별 컨디션 (06시~19시)")
    st.markdown("<p style='font-size:12px; color:gray; margin-top:-10px;'>※ 초록: 그늘추천 / 빨강: 열사병위험 / 검은색: 보통</p>", unsafe_allow_html=True)

    # 화면 공간 확보를 위해 불필요한 단위 생략 및 컬럼 최소화
    df_mobile_display = pd.DataFrame({
        "체감": df_mobile["체감온도"].round(1),
        "구름두께": df_mobile["구름두께"].astype(int).astype(str) + "%",
        "지속성": df_mobile["그늘지속성"].astype(str) + "점",
        "자외선": df_mobile["자외선"].round(1),
        "현황": df_mobile["상태"]
    })

    # 로우(Row) 색상 정의 함수
    def style_rows_by_condition(row):
        if "위험" in str(row["현황"]):
            return ['color: #D32F2F; font-weight: bold;'] * len(row)
        elif "추천" in str(row["현황"]):
            return ['color: #2E7D32; font-weight: bold;'] * len(row)
        else:
            return ['color: #212121; font-weight: normal;'] * len(row)

    styled_mobile_df = df_mobile_display.style.apply(style_rows_by_condition, axis=1)
    st.dataframe(styled_mobile_df, use_container_width=True, height=490)

    # 📉 차트 분석 섹션 (하단 이동)
    st.divider()
    st.subheader("📉 정밀 예측 트렌드 그래프")
    tab1, tab2 = st.tabs(["☁️ 구름 밀도 및 지속성", "🌡️ 기온 변화 추이"])
    
    with tab1:
        st.bar_chart(df_day["구름두께"], color="#90A4AE")
        st.line_chart(df_day["그늘지속성"], color="#00E676")

    with tab2:
        st.line_chart(df_day[["기온", "체감온도"]])
