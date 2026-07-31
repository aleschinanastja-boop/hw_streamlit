import pandas as pd
import time
import requests
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()
API = os.getenv("API")

month_to_season = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn"
}


def process_city(city_df):
    city_df = city_df.sort_values("timestamp").copy()

    city_df["rolling_mean_30"] = city_df["temperature"].rolling(
        window=30,
        min_periods=1
    ).mean()

    stats = city_df.groupby("season")["temperature"].agg(["mean", "std"]).reset_index()
    stats.columns = ["season", "mean_temp", "std_temp"]

    city_df = city_df.merge(stats, on="season", how="left")

    city_df["is_anomaly"] = (
        (city_df["temperature"] < city_df["mean_temp"] - 2 * city_df["std_temp"]) |
        (city_df["temperature"] > city_df["mean_temp"] + 2 * city_df["std_temp"])
    )

    return city_df


def get_current_season():
    current_month = datetime.now().month
    return month_to_season[current_month]


def get_city_coordinates(city, api_key):
    url = "http://api.openweathermap.org/geo/1.0/direct"
    params = {
        "q": city,
        "limit": 1,
        "appid": api_key
    }

    response = requests.get(url, params=params, timeout=10)

    if response.status_code == 401:
        raise ValueError(response.json())

    response.raise_for_status()
    data = response.json()

    if not data:
        raise ValueError(f"Город {city} не найден")

    return data[0]["lat"], data[0]["lon"]


def get_current_temperature_sync(city, api_key):
    lat, lon = get_city_coordinates(city, api_key)

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": "metric"
    }

    response = requests.get(url, params=params, timeout=10)

    if response.status_code == 401:
        raise ValueError(response.json())

    response.raise_for_status()
    data = response.json()
    return data["main"]["temp"]


async def get_current_temperature_async(session, city, api_key):
    # координаты всё равно получаем синхронно один раз
    lat, lon = get_city_coordinates(city, api_key)

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": "metric"
    }

    async with session.get(url, params=params) as response:
        if response.status == 401:
            error_data = await response.json()
            raise ValueError(error_data)

        response.raise_for_status()
        data = await response.json()
        return {"city": city, "temp": data["main"]["temp"]}


def check_current_temperature(city, current_temp, season_stats):
    current_season = get_current_season()

    row = season_stats[
        (season_stats["city"] == city) &
        (season_stats["season"] == current_season)
    ]

    if row.empty:
        return f"Для города {city} нет данных"

    mean_temp = row["mean_temp"].iloc[0]
    std_temp = row["std_temp"].iloc[0]

    lower_bound = mean_temp - 2 * std_temp
    upper_bound = mean_temp + 2 * std_temp

    if lower_bound <= current_temp <= upper_bound:
        status = "нормальная"
    else:
        status = "аномальная"

    return {
        "city": city,
        "season": current_season,
        "current_temp": round(current_temp, 2),
        "mean_temp": round(mean_temp, 2),
        "std_temp": round(std_temp, 2),
        "lower_bound": round(lower_bound, 2),
        "upper_bound": round(upper_bound, 2),
        "status": status
    }


async def async_temperature_check(cities, api_key, season_stats):
    async with aiohttp.ClientSession() as session:
        tasks = [get_current_temperature_async(session, city, api_key) for city in cities]
        temps = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for item in temps:
        if isinstance(item, Exception):
            results.append(item)
        else:
            city = item["city"]
            temp = item["temp"]
            results.append(check_current_temperature(city, temp, season_stats))
    return results


if __name__ == "__main__":
    if not API:
        print("API ключ не найден в .env")
        exit()

    # 1. Исторические данные читаем из готового csv
    df = pd.read_csv("temperature_data.csv", parse_dates=["timestamp"])

    if "season" not in df.columns:
        df["season"] = df["timestamp"].dt.month.map(month_to_season)

    # 2. Исторический анализ
    start_hist = time.time()

    result_df = pd.concat(
        [process_city(group) for _, group in df.groupby("city")],
        ignore_index=True
    )

    hist_time = time.time() - start_hist

    print("\nскользящее среднее")
    print(result_df[["city", "timestamp", "temperature", "rolling_mean_30"]].head(10))

    print("\nстатистика по сезонам")
    season_stats = result_df[["city", "season", "mean_temp", "std_temp"]].drop_duplicates()
    print(season_stats.head(12))

    print("\nаномалии")
    anomalies = result_df[result_df["is_anomaly"]]
    print(anomalies[["city", "timestamp", "temperature", "mean_temp", "std_temp"]].head(10))

    print("\nаномалии по городам")
    print(anomalies.groupby("city").size())

    print(f"\nанализ исторических данных: {hist_time:.4f} секунд")

    # 3. Проверка текущей температуры через API
    cities_to_check = ["Berlin", "Cairo", "Dubai", "Beijing", "Moscow"]

    print("\n--- синхронные API-запросы ---")
    start_sync = time.time()

    sync_results = []
    for city in cities_to_check:
        try:
            current_temp = get_current_temperature_sync(city, API)
            result = check_current_temperature(city, current_temp, season_stats)
            sync_results.append(result)
        except Exception as e:
            sync_results.append(f"{city}: {e}")

    sync_time = time.time() - start_sync

    for item in sync_results:
        print(item)

    print("\n--- асинхронные API-запросы ---")
    start_async = time.time()

    async_results = asyncio.run(async_temperature_check(cities_to_check, API, season_stats))

    async_time = time.time() - start_async

    for item in async_results:
        print(item)

    print(f"\nсинхронные API-запросы: {sync_time:.4f} секунд")
    print(f"асинхронные API-запросы: {async_time:.4f} секунд")