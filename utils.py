import os
import requests
from dotenv import load_dotenv

load_dotenv()

WEATHER_KEY = os.getenv("OPENWEATHER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")


# 🌡️ WEATHER DATA
def get_weather(lat, lon):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_KEY}&units=metric"
    response = requests.get(url).json()

    return {
        "temperature": response["main"]["temp"],
        "humidity": response["main"]["humidity"]
    }


# 🌱 AI CROP RECOMMENDATION
def get_crop_ai(state, temp, rainfall, dtwl):
    prompt = f"""
    Suggest suitable crops for:

    Location: {state}
    Temperature: {temp} °C
    Rainfall: {rainfall} mm
    Groundwater Level: {dtwl} m

    Give clear crop names and short reason.
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_KEY}"

    headers = {"Content-Type": "application/json"}

    data = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print("Gemini Error:", result)
        return "Recommendation not available. Check API key or quota."