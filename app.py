import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# 1. 설정 및 즐겨찾기 초기화
ST_VERSION = "V3.2 (Bugfix & Logic Overhaul)"
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
        res = requests.get(url, headers={'User-Agent': 'WeatherApp/3.2'}, timeout=3).json()
        if res: return float(res[0]['lat']), float(res[0]['lon']), res[0]['display_name']
    except: return None, None, None

@st.cache_data(ttl=600)
def fetch_weather(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation_probability,precipitation,cloud_cover,wind_speed_10m,wind_gusts_10m,uv_index",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max",
        "timezone": "auto", "forecast_days": 10
    }
    return requests.get(url, params=params).json()

# --- UI 구성 ---
st.set_page_config(page_title="Gunsan CC Weather V3.2", layout="centered")
st.markdown(f"<p style='text-align:right; color:gray; font-size:10px;'>{ST_VERSION}</p>", unsafe_allow_html=True)
st.title("🎯 필드 그늘 정밀 분석기")

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

    # [수정 1] 타임존 에러 방지: UTC 등 꼬리표를 강제로 떼어내고 순수 시간만 남김
    raw_times = pd.to_datetime(data["hourly"]["time"])
    if raw_times.tz is not None:
        raw_times = raw_times.dt.tz_localize(None)

    df_hourly = pd.DataFrame({
        "시간_원본": raw_times,
        "기온": data["hourly"]["temperature_2m"],
        "체감온도": data["hourly"]["apparent_temperature"],
        "습도": data["hourly"]["relative_humidity_2m"],
        "강수확률": data["hourly"]["precipitation_probability"],
        "강수량": data["hourly"]["precipitation"],
        "구름량": data["hourly"]["cloud_cover"],
        "자외선": data["hourly"]["uv_index"],
        "풍속": data["hourly"]["wind_speed_10m"],
        "돌풍": data["hourly"]["wind_gusts_10m"]
    })

    # 선택한 날짜 필터링
    df_day = df_hourly[df_hourly["시간_원본"].dt.date == selected_date].copy()
    
    # [수정 2] 야간 골프 추천 방지: 오전 6시 ~ 오후 7시 사이만 추천 가능 대상
    is_daytime = (df_day["시간_원본"].dt.hour >= 6) & (df_day["시간_원본"].dt.hour <= 19)
    df_day["그늘상태"] = (df_day["구름량"] >= 60) & (df_day["강수량"] == 0) & (df_day["자외선"] <= 3) & is_daytime
    
    df_day["표시시간"] = df_day["시간_원본"].dt.strftime("%H:00")
    df_day.set_index("표시시간", inplace=True)

    st.divider()
    best_shade = df_day[df_day["그늘상태"] == True].index.tolist()
    if best_shade:
        st.success(f"🌟 **{selected_date_str} 주간 최적 그늘 시간대:** {', '.join(best_shade)}")
    else:
        st.warning(f"⚠️ {selected_date_str}에는 주간 중 완벽한 그늘 조건이 없습니다. 아래 차트로 구름량을 확인하세요.")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["☁️ 그늘/자외선", "🌡️ 온도(기온/체감)", "🌧️ 비(확률/양)", "🌬️ 바람/돌풍", "📊 상세표"])

    with tab1:
        st.markdown("**구름량(%)이 높고 자외선(UV)이 낮은 구간이 시원합니다.**")
        st.bar_chart(df_day["구름량"], color="#90A4AE")
        st.line_chart(df_day["자외선"], color="#FF7043")

    with tab2:
        st.bar_chart(df_day[["기온", "체감온도"]])

    with tab3:
        st.bar_chart(df_day[["강수확률", "강수량"]])

    with tab4:
        st.line_chart(df_day[["풍속", "돌풍"]])

    with tab5:
        # [수정 3] 상세표의 소수점 1자리 정리
        st.dataframe(df_day.drop(columns=["시간_원본", "그늘상태"]).round(1), use_container_width=True)

    st.divider()
    st.subheader("🗓️ 10일간의 전체 흐름")
    df_10d = pd.DataFrame({
        "날짜": data["daily"]["time"],
        "최고기온": data["daily"]["temperature_2m_max"],
        "최저기온": data["daily"]["temperature_2m_min"],
        "최대강수확률": data["daily"]["precipitation_probability_max"],
        "최대자외선": data["daily"]["uv_index_max"]
    }).set_index("날짜")
    
    # [수정 3] 전체 흐름 표의 소수점 1자리 정리
    st.dataframe(df_10d.round(1), use_container_width=True)
