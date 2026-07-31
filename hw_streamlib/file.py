import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import requests
from datetime import datetime

st.set_page_config(layout="wide")
st.title('Анализ температурных данных')
uploaded_file = st.sidebar.file_uploader(
    "Загрузите CSV-файл с историческими данными",
    type=["csv"]
)

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file, parse_dates=["timestamp"])
else:
    st.warning("Загрузите файл с историческими данными")
    st.stop()


month_to_season = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn"
}
if "season" not in df.columns:
    df["season"] = df["timestamp"].dt.month.map(month_to_season)

def process_city(city_df):
    city_df = city_df.sort_values("timestamp").copy()

    city_df["rolling_mean_30"] = city_df["temperature"].rolling(30, min_periods=1).mean()

    stats = city_df.groupby("season")["temperature"].agg(["mean", "std"]).reset_index()
    stats.columns = ["season", "mean_temp", "std_temp"]

    city_df = city_df.merge(stats, on="season", how="left")

    city_df["is_anomaly"] = (
        (city_df["temperature"] < city_df["mean_temp"] - 2 * city_df["std_temp"]) |
        (city_df["temperature"] > city_df["mean_temp"] + 2 * city_df["std_temp"])
    )
    return city_df


def get_current_season():
    return month_to_season[datetime.now().month]


def get_current_temperature(city, api_key):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": api_key,
        "units": "metric"
    }

    response = requests.get(url, params=params)

    if response.status_code == 401:
        error_data = response.json()
        message = error_data.get("message", "Unknown error")

        st.error('Invalid API key. Please see https://openweathermap.org/faq#error401 for more info.')
        return None
    if response.status_code != 200:
        st.error('Invalid API key. Please see https://openweathermap.org/faq#error401 for more info.')
        return None

    data = response.json()
    return data["main"]["temp"]


def check_temp(city, current_temp, stats):
    season = get_current_season()

    row = stats[
        (stats["city"] == city) &
        (stats["season"] == season)
    ]

    mean = row["mean_temp"].values[0]
    std = row["std_temp"].values[0]

    lower = mean - 2 * std
    upper = mean + 2 * std

    if lower <= current_temp <= upper:
        return "Нормальная"
    else:
        return "Аномальная"


st.sidebar.header("Настройки")
cities = df["city"].unique()
selected_city = st.sidebar.selectbox("Выбери город", cities)
api_key = st.sidebar.text_input("API ключ OpenWeather", type="password")

city_df = df[df["city"] == selected_city]
city_df = process_city(city_df)
season_stats = city_df[["city", "season", "mean_temp", "std_temp"]].drop_duplicates()

st.subheader("Описательная статистика")
st.write(city_df["temperature"].describe())

st.subheader("Временной ряд с температур выделением аномалий")
fig, ax = plt.subplots()
ax.plot(city_df["timestamp"], city_df["temperature"], label="Температура")
ax.plot(city_df["timestamp"], city_df["rolling_mean_30"], label="Скользящее среднее")
anomalies = city_df[city_df["is_anomaly"]]
ax.scatter(anomalies["timestamp"], anomalies["temperature"], label="Аномалии")
ax.set_title("Температура во времени")
ax.set_xlabel("Дата")
ax.set_ylabel("Температура")
ax.legend()
st.pyplot(fig)

st.subheader("Сезонные профили")
fig2, ax2 = plt.subplots()
ax2.bar(season_stats["season"], season_stats["mean_temp"], yerr=season_stats["std_temp"])
ax2.set_title("Средняя температура по сезонам")
ax2.set_xlabel("Сезон")
ax2.set_ylabel("Температура")
st.pyplot(fig2)

st.subheader("Текущая температура")
if api_key:
    temp = get_current_temperature(selected_city, api_key)
    if temp is not None:
        status = check_temp(selected_city, temp, season_stats)
        st.write(f"Температура сейчас: {temp} °C")
        st.write(f"Статус: {status}")
else:
    st.warning("Введите API ключ")

# отсюда ниже реализация доп функций: сравнение с рандомным городом и вывод максимума и минимума в выбранном городе

import random
cities = df["city"].unique().tolist()

if "random_city" not in st.session_state:
    st.session_state.random_city = None

if st.sidebar.button("Выбрать случайный город"):
    available_cities = [city for city in cities if city != selected_city]
    st.session_state.random_city = random.choice(available_cities)

def get_city_data(city, df):
    city_df = df[df["city"] == city].copy()
    city_df = process_city(city_df)
    season_stats = city_df[["city", "season", "mean_temp", "std_temp"]].drop_duplicates()
    return city_df, season_stats

st.subheader("Сравнение с случайным городом")

if st.session_state.random_city is None:
    st.info("Нажми кнопку «Выбрать случайный город», чтобы сравнить температуры.")
else:
    random_city = st.session_state.random_city
    st.write(f"Случайный город: **{random_city}**")

    selected_city_df, selected_stats = get_city_data(selected_city, df)
    random_city_df, random_stats = get_city_data(random_city, df)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"### {selected_city}")
        st.write(f"Средняя историческая температура: {selected_city_df['temperature'].mean():.2f} °C")

        if api_key:
            try:
                selected_temp = get_current_temperature(selected_city, api_key)
                selected_status = check_temp(selected_city, selected_temp, selected_stats)

                st.write(f"Текущая температура: {selected_temp:.2f} °C")
                st.write(f"Статус: {selected_status}")
            except Exception as e:
                st.error(f"Ошибка для {selected_city}: {e}")

    with col2:
        st.markdown(f"### {random_city}")
        st.write(f"Средняя историческая температура: {random_city_df['temperature'].mean():.2f} °C")

        if api_key:
            try:
                random_temp = get_current_temperature(random_city, api_key)
                random_status = check_temp(random_city, random_temp, random_stats)

                st.write(f"Текущая температура: {random_temp:.2f} °C")
                st.write(f"Статус: {random_status}")
            except Exception as e:
                st.error(f"Ошибка для {random_city}: {e}")

    if api_key:
        try:
            diff = selected_temp - random_temp
            st.write(f"### Разница температур: {diff:.2f} °C")
        except:
            pass

def generate_recommendation(city_df, selected_city, current_temp=None, current_status=None):
    avg_temp = city_df["temperature"].mean()
    std_temp = city_df["temperature"].std()

    hottest_day = city_df.loc[city_df["temperature"].idxmax()]
    coldest_day = city_df.loc[city_df["temperature"].idxmin()]

    recommendation = []

    recommendation.append(
        f"Для города {selected_city} средняя историческая температура составляет {avg_temp:.2f} °C."
    )

    recommendation.append(
        f"Стандартное отклонение температуры равно {std_temp:.2f}, что показывает разброс значений."
    )

    if current_temp is not None and current_status is not None:
        if current_status == "Нормальная":
            recommendation.append(
                f"Текущая температура {current_temp:.2f} °C находится в пределах нормы для текущего сезона."
            )
        else:
            recommendation.append(
                f"Текущая температура {current_temp:.2f} °C является аномальной для текущего сезона."
            )

    recommendation.append(
        f"Самый тёплый день за весь период наблюдений: {hottest_day['timestamp'].date()}, температура {hottest_day['temperature']:.2f} °C."
    )

    recommendation.append(
        f"Самый холодный день за весь период наблюдений: {coldest_day['timestamp'].date()}, температура {coldest_day['temperature']:.2f} °C."
    )

    return " ".join(recommendation)

def get_year_extremes(city_df, year):
    year_df = city_df[city_df["timestamp"].dt.year == year]

    if year_df.empty:
        return None, None

    max_row = year_df.loc[year_df["temperature"].idxmax()]
    min_row = year_df.loc[year_df["temperature"].idxmin()]

    return max_row, min_row

available_years = sorted(city_df["timestamp"].dt.year.unique())
selected_year = st.selectbox("Выбери год", available_years, key="selected_year")

st.subheader("Максимальная и минимальная температура за выбранный год")

max_row, min_row = get_year_extremes(city_df, selected_year)

if max_row is not None and min_row is not None:
    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Максимальная температура",
            f"{max_row['temperature']:.2f} °C"
        )
        st.write(f"Дата: {max_row['timestamp'].date()}")

    with col2:
        st.metric(
            "Минимальная температура",
            f"{min_row['temperature']:.2f} °C"
        )
        st.write(f"Дата: {min_row['timestamp'].date()}")
else:
    st.warning("Для выбранного года нет данных")

current_temp_value = None
current_status_value = None

if api_key:
    temp = get_current_temperature(selected_city, api_key)

    if temp is not None:
        status = check_temp(selected_city, temp, season_stats)

        current_temp_value = temp
        current_status_value = status

        st.write(f"Температура сейчас: {temp} °C")
        st.write(f"Статус: {status}")
else:
    st.warning("Введите API ключ")



recommendation_text = generate_recommendation(
    city_df,
    selected_city,
    current_temp=current_temp_value,
    current_status=current_status_value
)

st.write(recommendation_text)
