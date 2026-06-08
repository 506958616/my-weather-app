import streamlit as st
import requests
import pandas as pd
from datetime import timedelta

# 1. 기본 위치 정의 및 세션 상태(즐겨찾기) 초기화
DEFAULT_PLACES = {
    "⛳ 군산 컨트리클럽": (35.895, 126.655),
    "🏠 우리집 (기본값)": (35.840, 127.130)  # 필요시 본인의 위도/경도로 수정 가능
}

if "favorites" not in st.session_state:
    st.session_state["favorites"] = DEFAULT_PLACES.copy()

def get_current_ip_location():
    """IP 기반으로 현재 접속한 기기의 대략적인 위도/경도를 가져옴"""
    try:
        res = requests.get("https://ipapi.co/json/", timeout=3).json()
        if "latitude" in res and "longitude" in res:
            return float(res["latitude"]), float(res["longitude"]), f"📍 현재 내 위치 ({res.get('city', '자동감지')})"
    except:
        pass
    return None, None, None

def get_coordinates(location_name):
    """검색어 기반 위도/경도 반환"""
    url = f"https://nominatim.openstreetmap.org/search?q={location_name}&format=json&limit=1"
    try:
        response = requests.get(url, headers={'User-Agent': 'WeatherApp/3.0'}, timeout=3).json()
        if response:
            return float(response[0]['lat']), float(response[0]['lon']), response[0]['display_name']
    except:
        pass
    return None, None, None

@st.cache_data(ttl=600)
def get_weather_data(lat, lon):
    """Open-Meteo API 기상 데이터 호출 (10분 캐싱)"""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,cloud_cover,wind_speed_10m,wind_gusts_10m,weather_code",
        "hourly": "temperature_2m,precipitation_probability,precipitation,cloud_cover,wind_speed_10m,wind_gusts_10m,uv_index",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max",
        "timezone": "auto",
        "forecast_days": 3
    }
    return requests.get(url, params=params).json()

# --- UI 레이아웃 시작 ---
st.set_page_config(page_title="필드 그늘 탐색기", layout="centered")
st.title("⛅ 필드 최적 그늘 날씨 탐색기")

# 기능 1 & 2: 위치 선택 (자동위치 / 즐겨찾기 / 직접검색)
st.subheader("📍 위치 선택 및 즐겨찾기")
location_mode = st.radio("위치 설정 방법", ["현재 내 위치 자동 잡기", "즐겨찾기에서 선택", "새로운 장소 검색"], horizontal=True)

lat, lon, display_name = DEFAULT_PLACES["⛳ 군산 컨트리클럽"][0], DEFAULT_PLACES["⛳ 군산 컨트리클럽"][1], "군산 컨트리클럽"

if location_mode == "현재 내 위치 자동 잡기":
    ip_lat, ip_lon, ip_name = get_current_ip_location()
    if ip_lat:
        lat, lon, display_name = ip_lat, ip_lon, ip_name
    else:
        st.warning("현재 위치를 불러올 수 없어 기본값(군산CC)으로 대체합니다.")

elif location_mode == "즐겨찾기에서 선택":
    selected_fav = st.selectbox("등록된 즐겨찾기 목록", list(st.session_state["favorites"].keys()))
    lat, lon = st.session_state["favorites"][selected_fav]
    display_name = selected_fav

elif location_mode == "새로운 장소 검색":
    search_query = st.text_input("검색할 지역명이나 골프장 이름을 입력하세요 (예: 아시아나CC, 군산시)", "")
    if search_query:
        s_lat, s_lon, s_name = get_coordinates(search_query)
        if s_lat:
            lat, lon, display_name = s_lat, s_lon, s_name
            st.success(f"🔍 검색 성공: {display_name}")
            # 즐겨찾기 추가 버튼 활성화
            if st.button("⭐ 이 장소를 즐겨찾기에 등록"):
                st.session_state["favorites"][f"⭐ {search_query}"] = (lat, lon)
                st.toast(f"'{search_query}'가 즐겨찾기에 추가되었습니다!")
        else:
            st.error("장소를 찾을 수 없습니다. 정확한 명칭으로 다시 검색해 주세요.")

st.info(f"🌐 탐색 중인 지역: **{display_name}** (위도: {round(lat,3)}, 경도: {round(lon,3)})")
st.divider()

# --- 데이터 연산 및 시각화 ---
weather = get_weather_data(lat, lon)

if weather:
    current = weather['current']
    hourly = weather['hourly']
    
    # 시간 데이터 프레임 구축 및 타임존 무결성 확보
    df_hourly = pd.DataFrame({
        "시간_원본": pd.to_datetime(hourly["time"]),
        "기온(°C)": hourly["temperature_2m"],
        "비올확률(%)": hourly["precipitation_probability"],
        "강수량(mm)": hourly["precipitation"],
        "구름량(%)": hourly["cloud_cover"],
        "자외선(UV)": hourly["uv_index"],
        "풍속(km/h)": hourly["wind_speed_10m"],
        "돌풍(km/h)": hourly["wind_gusts_10m"]
    })
    
    # 서버-로컬 간 타임존 에러 완전 차단
    now_time = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None)
    df_hourly = df_hourly[df_hourly["시간_원본"] >= (now_time - timedelta(hours=1))].head(24) # 향후 24시간 정밀 분석
    
    # [핵심] 유저 맞춤 그늘(Shade) 필터 조건 연산
    # 조건: 구름 60% 이상이고, 강수량이 없으며, 자외선이 3 이하인 황금 시간대
    df_hourly["그늘점수"] = (df_hourly["구름량(%)"] >= 60) & (df_hourly["강수량(mm)"] == 0) & (df_hourly["자외선(UV)"] <= 3)
    df_hourly["시간"] = df_hourly["시간_원본"].dt.strftime("%H:00")
    df_hourly.set_index("시간", inplace=True)
    
    # 1. 상단 현재 상태 요약 요약
    st.subheader("👀 실시간 필드 상태 요약")
    c_col1, c_col2, c_col3 = st.columns(3)
    c_col1.metric("현재 기온", f"{current['temperature_2m']}°C")
    c_col2.metric("현재 구름량", f"{current['cloud_cover']}%")
    
    is_current_shade = "☁️ 시원한 그늘 상태" if current['cloud_cover'] >= 60 and current['precipitation'] == 0 else "☀️ 햇빛 노출 주의"
    if current['precipitation'] > 0: is_current_shade = "☔ 현재 비 오는 중"
    c_col3.metric("현재 그늘 여부", is_current_shade)
    
    st.divider()
    
    # 2. 기능 3: '구름과 그늘' 최적화 시간대 시각화
    st.subheader("🎯 햇빛 없는 최적의 '그늘 타임라인' (향후 24시간)")
    st.markdown("유저님의 취향을 반영하여 **[구름 60% 이상 + 비 안 옴 + 자외선 안전]** 환경의 시간대를 분석했습니다.")
    
    # 그늘 타임라인 시각화 테이블 생성
    shade_hours = df_hourly[df_hourly["그늘점수"] == True].index.tolist()
    
    if shade_hours:
        st.success(f"🌟 **오늘~내일 중 추천 그늘 시간대:** {', '.join(shade_hours)}")
    else:
        st.warning("⚠️ 향후 24시간 이내에 조건에 맞는 100% 완벽한 그늘 시간대가 없습니다. 아래 그래프에서 구름이 가장 높은 시간을 확인하세요.")
        
    # 복합 상호작용 차트
    v_tab1, v_tab2, v_tab3 = st.tabs(["☁️ 구름량 & 자외선 (그늘 집중분석)", "🌧️ 강수 예측 (확률/강수량)", "💨 바람 변화 (풍속/돌풍)"])
    
    with v_tab1:
        st.markdown("**구름량(막대)이 높고 자외선(선)이 낮은 구간이 최적의 그늘 타이밍입니다.**")
        # 구름량과 자외선을 겹쳐서 시각화하여 직관성 확보
        st.bar_chart(df_hourly["구름량(%)"], color="#90A4AE")
        st.line_chart(df_hourly["자외선(UV)"], color="#FF7043")
        
    with v_tab2:
        st.markdown("**시간별 비 올 확률과 실제 쏟아질 강수량 비교**")
        st.bar_chart(df_hourly[["비올확률(%)", "강수량(mm)"]])
        
    with v_tab3:
        st.markdown("**평균 풍속과 순간적인 돌풍의 세기 비교**")
        st.line_chart(df_hourly[["풍속(km/h)", "돌풍(km/h)"]])
