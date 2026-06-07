import streamlit as st
import requests
import pandas as pd

# 기본 좌표를 군산 컨트리클럽으로 설정
DEFAULT_LAT = 35.895
DEFAULT_LON = 126.655

def get_coordinates(location_name):
    url = f"https://nominatim.openstreetmap.org/search?q={location_name}&format=json&limit=1"
    response = requests.get(url, headers={'User-Agent': 'WeatherApp/1.0'}).json()
    if response:
        return float(response[0]['lat']), float(response[0]['lon']), response[0]['display_name']
    return None, None, None

def get_weather_data(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    # 바람, 비 등 추가 데이터를 가져오도록 파라미터 확대
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,cloud_cover,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,sunshine_duration,wind_speed_10m_max",
        "timezone": "auto",
        "forecast_days": 10
    }
    response = requests.get(url, params=params)
    return response.json()

def calculate_custom_index(temp, rain, wind, cloud_cover):
    """구름 낀 날을 가장 좋게 평가하는 맞춤형 알고리즘"""
    if rain > 0.5:
        return "🔴 나쁨 (비 옴)"
    elif wind > 15.0:
        return "🟡 주의 (바람 강함)"
    elif cloud_cover >= 60:
        return "🌟 최상 (구름 껴서 눈부심 없고 시원함!)" # 취향 적극 반영
    else:
        return "🟢 무난 (단, 햇빛이 강할 수 있음)"

st.set_page_config(page_title="나만의 맞춤 날씨", layout="centered")
st.title("🎯 나만의 10일 맞춤 날씨 예측기")

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
    daily = weather['daily']
    
    # --- 실시간 요약 (취향 반영) ---
    st.subheader("현재 실시간 날씨 요약")
    col1, col2 = st.columns(2)
    
    status = calculate_custom_index(
        current['temperature_2m'], 
        current['precipitation'], 
        current['wind_speed_10m'], 
        current['cloud_cover']
    )
    col1.metric("내 취향 반영 활동 지수", status)
    col2.metric("현재 기온", f"{current['temperature_2m']}°C")

    st.divider()

    # --- 데이터 정리 ---
    df_daily = pd.DataFrame({
        "날짜": daily["time"],
        "최고기온(°C)": daily["temperature_2m_max"],
        "최저기온(°C)": daily["temperature_2m_min"],
        "강수확률(%)": daily["precipitation_probability_max"],
        "총 강수량(mm)": daily["precipitation_sum"],
        "일조시간(시간)": [round(s / 3600, 1) for s in daily["sunshine_duration"]],
        "최대풍속(km/h)": daily["wind_speed_10m_max"]
    })
    df_daily.set_index("날짜", inplace=True)

    # --- 탭을 이용한 개별 정보 보기 ---
    st.subheader("📅 10일 대략적 예측 (항목별 상세 보기)")
    tab1, tab2, tab3, tab4 = st.tabs(["📊 종합 요약", "☔ 비(강수)", "☁️ 구름(해)", "🌬️ 바람"])
    
    with tab1:
        st.markdown("**10일간의 전체 날씨 정보입니다.** (강수확률 50% 이상 빨간색 표시)")
        st.dataframe(
            df_daily.style.map(lambda x: 'color: red; font-weight: bold' if x >= 50 else '', subset=['강수확률(%)']),
            use_container_width=True
        )
        
    with tab2:
        st.markdown("**언제 비가 올 위험이 가장 높은지 확률로 확인하세요.**")
        st.bar_chart(df_daily["강수확률(%)"], color="#4C72B0")
        st.caption("※ 막대가 높은 날은 일정을 피하는 것이 좋습니다.")

    with tab3:
        st.markdown("**해가 쨍쨍한 시간(일조 시간)입니다.** (취향에 따라 수치가 낮은 날이 좋은 날입니다!)")
        # 구름을 좋아하시므로 일조시간이 짧을수록(차트가 낮을수록) 굿
        st.area_chart(df_daily["일조시간(시간)"], color="#E8A317")
        st.caption("※ 그래프가 바닥에 가까울수록 구름이 많아 활동하기 좋은 날입니다.")

    with tab4:
        st.markdown("**날짜별 최대 풍속 변화입니다.**")
        st.line_chart(df_daily["최대풍속(km/h)"], color="#55A868")
        st.caption("※ 15km/h 이상이면 바람이 꽤 부는 날입니다.")