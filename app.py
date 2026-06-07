import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# 기본 좌표: 군산 컨트리클럽
DEFAULT_LAT = 35.895
DEFAULT_LON = 126.655

def get_coordinates(location_name):
    url = f"https://nominatim.openstreetmap.org/search?q={location_name}&format=json&limit=1"
    try:
        response = requests.get(url, headers={'User-Agent': 'WeatherApp/1.0'}).json()
        if response:
            return float(response[0]['lat']), float(response[0]['lon']), response[0]['display_name']
    except:
        pass
    return None, None, None

@st.cache_data(ttl=600) # 10분간 데이터 캐싱하여 속도 최적화 및 에러 방지
def get_weather_data(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,cloud_cover,wind_speed_10m,weather_code",
        "hourly": "temperature_2m,precipitation_probability,precipitation,cloud_cover,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunshine_duration",
        "timezone": "auto",
        "forecast_days": 10
    }
    return requests.get(url, params=params).json()

def get_weather_status(code, cloud):
    """기상 코드를 바탕으로 상태 문자열과 이미지를 반환"""
    if code in [1, 2, 3]:
        if cloud >= 60:
            return "☁️ 흐림 (시원함)", "https://images.unsplash.com/photo-1534088568595-a066f410bcda?w=300&q=80" # 구름낀 하늘
        return "☀️ 맑음", "https://images.unsplash.com/photo-1508248467877-92693523d601?w=300&q=80" # 맑은 하늘
    elif code in [45, 48]:
        return "🌫️ 안개", "https://images.unsplash.com/photo-1494548162494-384bba4ab999?w=300&q=80"
    elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
        return "☔ 비 옴", "https://images.unsplash.com/photo-1534274988757-a28bf1a57c17?w=300&q=80" # 빗방울
    elif code in [71, 73, 75, 85, 86]:
        return "❄️ 눈 옴", "https://images.unsplash.com/photo-1518242008880-ca5e7f9f545a?w=300&q=80"
    else:
        return "☁️ 흐림", "https://images.unsplash.com/photo-1534088568595-a066f410bcda?w=300&q=80"

st.set_page_config(page_title="실시간 고정밀 날씨", layout="centered")
st.title("🎯 실시간 맞춤형 날씨 대시보드")

search_query = st.text_input("위치 검색 (비워두면 기본설정: 군산 CC)", "")
lat, lon, display_name = DEFAULT_LAT, DEFAULT_LON, "군산 컨트리클럽 (Gunsan CC)"

if search_query:
    s_lat, s_lon, s_name = get_coordinates(search_query)
    if s_lat:
        lat, lon, display_name = s_lat, s_lon, s_name

st.caption(f"📍 현재 기준 위치: {display_name}")

weather = get_weather_data(lat, lon)

if weather:
    current = weather['current']
    hourly = weather['hourly']
    daily = weather['daily']
    
    # 1. 현재 상황 이미지 및 요약
    status_text, img_url = get_weather_status(current['weather_code'], current['cloud_cover'])
    
    st.subheader("👀 한눈에 보는 현재 상황")
    col_img, col_info = st.columns([1, 2])
    
    with col_img:
        st.image(img_url, caption=status_text, use_container_width=True)
        
    with col_info:
        activity_status = "🌟 최상 (구름 껴서 시원함)" if current['cloud_cover'] >= 60 and current['precipitation'] == 0 else "🟢 무난함"
        if current['precipitation'] > 0: activity_status = "🔴 나쁨 (비)"
        
        st.metric("내 취향 활동 지수", activity_status)
        st.write(f"• **현재 기온:** {current['temperature_2m']}°C")
        st.write(f"• **현재 구름 량:** {current['cloud_cover']}%")
        st.write(f"• **현재 풍속:** {current['wind_speed_10m']} km/h")
        st.write(f"• **실시간 강수량:** {current['precipitation']} mm")

    st.divider()

    # 2. [핵심 업데이트] 1시간 단위 정밀 예측 (오늘~내일)
    st.subheader("🕒 1시간 단위 정밀 예측 (향후 36시간)")
    
    df_hourly = pd.DataFrame({
        "시간": pd.to_datetime(hourly["time"]),
        "기온(°C)": hourly["temperature_2m"],
        "비올확률(%)": hourly["precipitation_probability"],
        "구름량(%)": hourly["cloud_cover"],
        "풍속(km/h)": hourly["wind_speed_10m"]
    })
    
    # 현재 시간 이후의 데이터 36시간 분량만 필터링
    now_time = datetime.now().astimezone()
    df_hourly = df_hourly[df_hourly["시간"] >= (now_time - timedelta(hours=1))].head(36)
    df_hourly["시간"] = df_hourly["시간"].dt.strftime("%m/%d %H:00")
    df_hourly.set_index("시간", inplace=True)
    
    # 시간별 세부 수치 선택 탭
    h_tab1, h_tab2, h_tab3 = st.tabs(["🌧️ 시간별 비 올 확률", "☁️ 시간별 구름 변화", "🌡️ 시간별 기온/바람"])
    
    with h_tab1:
        st.markdown("**몇 시에 비가 오는지 확률로 확인하세요.**")
        st.bar_chart(df_hourly["비올확률(%)"], color="#4C72B0")
    with h_tab2:
        st.markdown("**구름이 얼마나 끼는지 확인하세요. (수치가 높을수록 햇빛 없는 흐린 날)**")
        st.area_chart(df_hourly["구름량(%)"], color="#7A7A7A")
    with h_tab3:
        st.markdown("**기온과 풍속의 변화 그래프입니다.**")
        st.line_chart(df_hourly[["기온(°C)", "풍속(km/h)"]])

    st.divider()

    # 3. 10일 대략적 예측
    st.subheader("📅 10일 장기 예측 (대략적 흐름)")
    df_daily = pd.DataFrame({
        "날짜": daily["time"],
        "최고기온(°C)": daily["temperature_2m_max"],
        "최저기온(°C)": daily["temperature_2m_min"],
        "최대강수확률(%)": daily["precipitation_probability_max"],
        "일조시간(시간)": [round(s / 3600, 1) for s in daily["sunshine_duration"]]
    })
    df_daily.set_index("날짜", inplace=True)
    st.dataframe(
        df_daily.style.map(lambda x: 'color: red; font-weight: bold' if x >= 50 else '', subset=['최대강수확률(%)']),
        use_container_width=True
    )
