import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np
from sklearn.linear_model import LinearRegression
from flask import Flask, jsonify, request
from flask_cors import CORS
import os
from dotenv import load_dotenv
import requests
import json
import re
import google.generativeai as genai

load_dotenv()

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:TP007@localhost:5432/groundwater_db")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

try:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_state ON groundwater_data(state_ut);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_district ON groundwater_data(district);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_block ON groundwater_data(block);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_village ON groundwater_data(village);")
        conn.commit()
except Exception as e:
    print(f"Database setup error: {e}")

def build_filters(args, include_block=True, include_village=True):
    filters = []
    params = []
    if args.get('state'):
        filters.append("state_ut ILIKE %s")
        params.append(args.get('state'))
    if args.get('district'):
        filters.append("district ILIKE %s")
        params.append(args.get('district'))
    if include_block and args.get('block'):
        filters.append("block ILIKE %s")
        params.append(args.get('block'))
    if include_village and args.get('village'):
        filters.append("village ILIKE %s")
        params.append(args.get('village'))
    
    where_clause = " AND ".join(filters)
    if where_clause:
        where_clause = "WHERE " + where_clause
    return where_clause, params

@app.route('/states')
def get_states():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT state_ut FROM groundwater_data WHERE state_ut IS NOT NULL AND state_ut != '' ORDER BY state_ut")
                states = [row[0] for row in cur.fetchall()]
        return jsonify(states)
    except Exception as e:
        print("Error /states:", e)
        return jsonify([])

@app.route('/districts')
def get_districts():
    try:
        where_clause, params = build_filters(request.args, include_block=False, include_village=False)
        query = f"SELECT DISTINCT district FROM groundwater_data {where_clause} " + ("AND" if where_clause else "WHERE") + " district IS NOT NULL AND district != '' ORDER BY district"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                districts = [row[0] for row in cur.fetchall()]
        return jsonify(districts)
    except Exception as e:
        print("Error /districts:", e)
        return jsonify([])

@app.route('/blocks')
def get_blocks():
    try:
        where_clause, params = build_filters(request.args, include_village=False)
        query = f"SELECT DISTINCT block FROM groundwater_data {where_clause} " + ("AND" if where_clause else "WHERE") + " block IS NOT NULL AND block != '' ORDER BY block"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                blocks = [row[0] for row in cur.fetchall()]
        return jsonify(blocks)
    except Exception as e:
        print("Error /blocks:", e)
        return jsonify([])

@app.route('/villages')
def get_villages():
    try:
        where_clause, params = build_filters(request.args)
        query = f"SELECT DISTINCT village FROM groundwater_data {where_clause} " + ("AND" if where_clause else "WHERE") + " village IS NOT NULL AND village != '' ORDER BY village"
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                villages = [row[0] for row in cur.fetchall()]
        return jsonify(villages)
    except Exception as e:
        print("Error /villages:", e)
        return jsonify([])

@app.route('/kpi')
def kpi():
    try:
        where_clause, params = build_filters(request.args)
        query = f"""
            SELECT 
                AVG(dtwl) AS overall_dtwl,
                (SELECT dtwl FROM groundwater_data {where_clause} ORDER BY date DESC LIMIT 1) AS current_dtwl,
                (SELECT date FROM groundwater_data {where_clause} ORDER BY date DESC LIMIT 1) AS current_date,
                AVG(dtwl) FILTER (WHERE season ILIKE 'Premonsoon') AS premonsoon,
                AVG(dtwl) FILTER (WHERE season ILIKE 'Postmonsoon') AS postmonsoon
            FROM groundwater_data
            {where_clause}
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params + params + params)
                result = cur.fetchone()
            
        overall_dtwl = round(result[0], 2) if result and result[0] is not None else "--"
        current_dtwl = round(result[1], 2) if result and result[1] is not None else "--"
        current_date_val = result[2] if result and result[2] is not None else None
        
        if current_date_val:
            try:
                current_date = current_date_val.strftime('%Y-%m-%d')
            except Exception:
                current_date = str(current_date_val)[:10]
        else:
            current_date = "--"

        premonsoon = round(result[3], 2) if result and result[3] is not None else "--"
        postmonsoon = round(result[4], 2) if result and result[4] is not None else "--"
        
        return jsonify({
            "overall_dtwl": overall_dtwl,
            "current_dtwl": current_dtwl,
            "current_date": current_date,
            "premonsoon": premonsoon,
            "postmonsoon": postmonsoon
        })
    except Exception as e:
        print("Error /kpi:", e)
        return jsonify({"overall_dtwl": "--", "current_dtwl": "--", "current_date": "--", "premonsoon": "--", "postmonsoon": "--"})

@app.route('/trend-data')
def trend_data():
    try:
        where_clause, params = build_filters(request.args)
        query = f"""
            SELECT 
                EXTRACT(YEAR FROM CAST(date AS DATE)) as year,
                AVG(dtwl) AS overall,
                AVG(dtwl) FILTER (WHERE season ILIKE 'Premonsoon') AS premonsoon,
                AVG(dtwl) FILTER (WHERE season ILIKE 'Postmonsoon') AS postmonsoon
            FROM groundwater_data
            {where_clause}
            GROUP BY year
            ORDER BY year
        """
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                result = cur.fetchall()
        
        formatted_result = []
        for row in result:
            formatted_result.append({
                "year": int(row['year']) if row['year'] else "Unknown",
                "overall": round(row['overall'], 2) if row['overall'] is not None else None,
                "premonsoon": round(row['premonsoon'], 2) if row['premonsoon'] is not None else None,
                "postmonsoon": round(row['postmonsoon'], 2) if row['postmonsoon'] is not None else None
            })
            
        return jsonify(formatted_result)
    except Exception as e:
        print("Error /trend-data:", e)
        return jsonify([])

@app.route('/rainfall-correlation')
def rainfall_data():
    try:
        where_clause, params = build_filters(request.args)
        query = f"""
            SELECT 
                EXTRACT(YEAR FROM CAST(date AS DATE)) as year,
                AVG(dtwl) as avg_dtwl
            FROM groundwater_data
            {where_clause}
            GROUP BY year
            ORDER BY year
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                result = cur.fetchall()
            
        years = [str(int(row[0])) if row[0] is not None else "Unknown" for row in result]
        groundwater = [round(row[1], 2) if row[1] is not None else 0 for row in result]
        rainfall = [round(row[1] * 100, 2) if row[1] is not None else 0 for row in result]
        
        return jsonify({
            "years": years,
            "rainfall": rainfall,
            "groundwater": groundwater
        })
    except Exception as e:
        print("Error /rainfall-correlation:", e)
        return jsonify({"years": [], "rainfall": [], "groundwater": []})

@app.route('/map-data')
def map_data():
    try:
        where_clause, params = build_filters(request.args)
        query = f"""
            SELECT latitude as lat, longitude as lon, dtwl
            FROM groundwater_data
            {where_clause}
            {"AND" if where_clause else "WHERE"} latitude IS NOT NULL AND longitude IS NOT NULL
            LIMIT 3000
        """
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                result = cur.fetchall()
            
        data = [
            {"lat": float(row['lat']), "lon": float(row['lon']), "dtwl": float(row['dtwl']) if row['dtwl'] is not None else 0}
            for row in result if row['lat'] is not None and row['lon'] is not None
        ]
        return jsonify(data)
    except Exception as e:
        print("Error /map-data:", e)
        return jsonify([])

@app.route('/weather')
def weather():
    try:
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        state = request.args.get('state')
        district = request.args.get('district')
        block = request.args.get('block')
        village = request.args.get('village')

        def fetch_weather(url):
            try:
                res = requests.get(url, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    temp = data.get('main', {}).get('temp', 0)
                    humidity = data.get('main', {}).get('humidity', 0)
                    if temp != 0 and humidity != 0:
                        return {"temperature": temp, "humidity": humidity}
            except Exception:
                pass
            return None

        # 1. Try with exact lat/lon
        if lat and lon and lat != 'undefined' and lon != 'undefined' and float(lat) != 0 and float(lon) != 0:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
            data = fetch_weather(url)
            if data: return jsonify(data)

        # 2. Hierarchical fallback
        locations_to_try = []
        if village and village != 'undefined': locations_to_try.append(f"{village}, IN")
        if block and block != 'undefined': locations_to_try.append(f"{block}, IN")
        if district and district != 'undefined': locations_to_try.append(f"{district}, IN")
        if state and state != 'undefined': locations_to_try.append(f"{state}, IN")
        locations_to_try.append("India")

        for loc in locations_to_try:
            url = f"https://api.openweathermap.org/data/2.5/weather?q={loc}&appid={OPENWEATHER_API_KEY}&units=metric"
            data = fetch_weather(url)
            if data: return jsonify(data)

        # Extreme fallback
        return jsonify({"temperature": 25.0, "humidity": 60})

    except Exception as e:
        print("Error /weather:", e)
        return jsonify({"temperature": 25.0, "humidity": 60})

def get_ai_crop_recommendations(state, district, block, village, dtwl, avg_dtwl, temperature, humidity, rainfall):
    prompt = f"""
You are an agricultural expert.

Based on the following data, recommend crops.

Location: {state}, {district}, {block}, {village}
DTWL: {dtwl} meters
Average DTWL: {avg_dtwl} meters
Temperature: {temperature} °C
Humidity: {humidity} %
Rainfall: {rainfall} mm

STRICT RULES:
- Return ONLY valid JSON
- Do NOT include explanations outside JSON
- Follow EXACT structure below:

{{
  "suitable": [
    {{"crop": "Crop Name", "reason": "Short reason"}}
  ],
  "moderate": [
    {{"crop": "Crop Name", "reason": "Short reason"}}
  ],
  "not_recommended": [
    {{"crop": "Crop Name", "reason": "Short reason"}}
  ]
}}

- If no crops, return empty arrays []
"""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        raw_text = response.text.strip()

        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except:
                parsed = {"suitable": [], "moderate": [], "not_recommended": []}
        else:
            parsed = {"suitable": [], "moderate": [], "not_recommended": []}

        if not parsed.get("suitable") and not parsed.get("moderate") and not parsed.get("not_recommended"):
            parsed = {
                "suitable": [{"crop": "Millets", "reason": "Low water requirement"}],
                "moderate": [{"crop": "Pulses", "reason": "Moderate water requirement"}],
                "not_recommended": [{"crop": "Rice", "reason": "High water requirement"}]
            }
        return parsed
    except Exception as e:
        print("Error getting AI crop recommendations:", e)
        return {
            "suitable": [{"crop": "Millets", "reason": "Low water requirement"}],
            "moderate": [{"crop": "Pulses", "reason": "Moderate water requirement"}],
            "not_recommended": [{"crop": "Rice", "reason": "High water requirement"}]
        }

@app.route('/ai-crop')
def ai_crop():
    try:
        state = request.args.get("state", "")
        district = request.args.get("district", "")
        block = request.args.get("block", "")
        village = request.args.get("village", "")

        dtwl = request.args.get('dtwl', '0')
        avg_dtwl = request.args.get('avg_dtwl', '0')
        temperature = request.args.get('temp', '0')
        humidity = request.args.get('humidity', '0')
        rainfall = request.args.get('rainfall', '0')

        parsed = get_ai_crop_recommendations(state, district, block, village, dtwl, avg_dtwl, temperature, humidity, rainfall)
        return jsonify(parsed)

    except Exception as e:
        print("Error /ai-crop:", e)
        return jsonify({
            "suitable": [{"crop": "Millets", "reason": "Low water requirement"}],
            "moderate": [{"crop": "Pulses", "reason": "Moderate water requirement"}],
            "not_recommended": [{"crop": "Rice", "reason": "High water requirement"}]
        })

@app.route('/api/recharge-efficiency')
def recharge_efficiency():
    try:
        where_clause, params = build_filters(request.args)
        query = f"""
            SELECT 
                EXTRACT(YEAR FROM CAST(date AS DATE)) as year,
                AVG(dtwl) FILTER (WHERE season ILIKE 'Premonsoon') as pre,
                AVG(dtwl) FILTER (WHERE season ILIKE 'Postmonsoon') as post
            FROM groundwater_data
            {where_clause}
            GROUP BY year
            ORDER BY year
            LIMIT 5000
        """
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                result = cur.fetchall()

        efficiencies = []
        for row in result:
            if row['year'] is None or row['pre'] is None or row['post'] is None:
                continue
            y = int(row['year'])
            efficiency = float(row['post']) - float(row['pre'])

            efficiencies.append({
                "year": y,
                "efficiency": round(efficiency, 2)
            })
            
        return jsonify(efficiencies)
    except Exception as e:
        return jsonify([])

@app.route('/api/autonomy')
def autonomy():
    try:
        where_clause, params = build_filters(request.args)
        query = f"SELECT dtwl as current FROM groundwater_data {where_clause} ORDER BY date DESC LIMIT 1"
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                row = cur.fetchone()

        current = row['current'] if row and row['current'] is not None else None
        
        if current is None:
            return jsonify({"days_of_autonomy": "--", "status": "Unknown"})
        
        if current == 0:
            days = 0
        else:
            days = round(current / 0.05)
        
        status = "Safe"
        if days < 100: status = "Warning"
        elif days < 365: status = "Moderate"

        return jsonify({"days_of_autonomy": days, "status": status})
    except Exception:
        return jsonify({"days_of_autonomy": "--", "status": "Unknown"})

@app.route('/api/borewell-safety')
def borewell_safety():
    try:
        where_clause, params = build_filters(request.args)
        query = f"""
            SELECT latitude as lat, longitude as lon, dtwl
            FROM groundwater_data
            {where_clause}
            {"AND" if where_clause else "WHERE"} latitude IS NOT NULL AND longitude IS NOT NULL
            LIMIT 3000
        """
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                result = cur.fetchall()

        data = []
        for row in result:
            dtwl = float(row['dtwl']) if row['dtwl'] else 0
            status = "SAFE"
            if dtwl > 15: status = "RISKY"
            elif dtwl >= 5: status = "MODERATE"
            
            data.append({
                "lat": float(row['lat']),
                "lng": float(row['lon']),
                "dtwl": dtwl,
                "status": status
            })
        return jsonify(data)
    except Exception:
        return jsonify([])

@app.route('/api/health-card')
def health_card():
    try:
        where_clause, params = build_filters(request.args)
        query = f"""
            SELECT dtwl, date
            FROM groundwater_data
            {where_clause}
            ORDER BY date ASC
            LIMIT 5000
        """
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                result = cur.fetchall()

        if not result:
            return jsonify({"health_score": "--", "trend": "--", "avg_dtwl": "--", "recharge": "--", "autonomy": "--", "risk": "--"})

        dtwls = [float(r['dtwl']) for r in result if r['dtwl'] is not None]
        if not dtwls:
            return jsonify({"health_score": "--", "trend": "--", "avg_dtwl": "--", "recharge": "--", "autonomy": "--", "risk": "--"})

        avg_dtwl = sum(dtwls) / len(dtwls)
        first_dtwl = dtwls[0]
        last_dtwl = dtwls[-1]
        
        trend = "Declining" if last_dtwl > first_dtwl else "Improving"
        
        if avg_dtwl < 5:
            score = 90
            risk = "low"
        elif avg_dtwl <= 10:
            score = 65
            risk = "medium"
        else:
            score = 30
            risk = "high"

        return jsonify({
            "health_score": score,
            "trend": trend,
            "avg_dtwl": round(avg_dtwl, 2),
            "recharge": 60,
            "autonomy": round(last_dtwl / 0.05) if last_dtwl else 0,
            "risk": risk
        })
    except Exception:
        return jsonify({"health_score": "--", "trend": "--", "avg_dtwl": "--", "recharge": "--", "autonomy": "--", "risk": "--"})

@app.route('/api/forecast')
def forecast():
    try:
        where_clause, params = build_filters(request.args)
        query = f"""
            SELECT 
                EXTRACT(YEAR FROM CAST(date AS DATE)) as year,
                AVG(dtwl) as overall
            FROM groundwater_data
            {where_clause}
            GROUP BY year
            ORDER BY year
            LIMIT 5000
        """
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                result = cur.fetchall()

        if not result or len(result) < 2:
            return jsonify([])

        years = np.array([int(r['year']) for r in result if r['year']]).reshape(-1, 1)
        values = np.array([float(r['overall']) for r in result if r['overall']])
        
        model = LinearRegression()
        model.fit(years, values)
        
        last_year = int(years[-1][0])
        future_years = np.array([[last_year + i] for i in range(1, 6)])
        preds = model.predict(future_years)
        
        res = [{"year": int(y[0]), "value": round(float(v), 2)} for y, v in zip(future_years, preds)]
        return jsonify(res)
    except Exception as e:
        print("Forecast Error:", e)
        return jsonify([])

@app.route('/api/alerts')
def alerts():
    try:
        where_clause, params = build_filters(request.args)
        query = f"""
            SELECT dtwl, date
            FROM groundwater_data
            {where_clause}
            ORDER BY date ASC
            LIMIT 5000
        """
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                result = cur.fetchall()

        alerts_list = []
        if result:
            dtwls = [float(r['dtwl']) for r in result if r['dtwl'] is not None]
            if dtwls:
                avg_dtwl = sum(dtwls) / len(dtwls)
                last = dtwls[-1]
                first = dtwls[0]
                
                if avg_dtwl > 10:
                    alerts_list.append({
                        "alert": "⚠ Groundwater level is very deep",
                        "reason": "Water is found deep below the ground, which makes it difficult to extract using normal borewells.",
                        "impact": "Farmers may need deeper drilling or may face water shortage.",
                        "recommendation": "Use water-saving irrigation methods like drip irrigation and avoid overuse."
                    })
                
                if last > first:
                    alerts_list.append({
                        "alert": "⚠ Groundwater trend is declining",
                        "reason": "Water level is reducing year by year.",
                        "impact": "Future water availability could be at risk if extraction continues at the current rate.",
                        "recommendation": "Adopt crop rotation with less water-intensive crops and promote rainwater harvesting."
                    })

        query_eff = f"""
            SELECT 
                AVG(dtwl) FILTER (WHERE season ILIKE 'Premonsoon') as pre,
                AVG(dtwl) FILTER (WHERE season ILIKE 'Postmonsoon') as post
            FROM groundwater_data
            {where_clause}
            LIMIT 5000
        """
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query_eff, params)
                eff_res = cur.fetchone()
        
        if eff_res and eff_res['pre'] is not None and eff_res['post'] is not None:
            eff = float(eff_res['post']) - float(eff_res['pre'])
            if eff < 1: 
                alerts_list.append({
                    "alert": "⚠ Recharge efficiency is low",
                    "reason": "Rainwater is not effectively increasing groundwater levels.",
                    "impact": "Aquifers are not recovering after the monsoon season.",
                    "recommendation": "Construct percolation tanks and check dams to improve groundwater recharge."
                })

        if not alerts_list:
            alerts_list.append({
                "alert": "✅ Groundwater levels are stable",
                "reason": "Current extraction is balanced with natural recharge.",
                "impact": "Water availability is sufficient for current agricultural needs.",
                "recommendation": "Continue standard water management practices."
            })
            
        return jsonify({"alerts": alerts_list})
    except Exception:
        return jsonify({"alerts": []})

@app.route('/api/insights')
def insights():
    try:
        where_clause, params = build_filters(request.args)
        query = f"SELECT AVG(dtwl) as a, MAX(dtwl) as c FROM groundwater_data {where_clause}"
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                row = cur.fetchone()
        c = row['c'] if row and row['c'] else 0
        a = row['a'] if row and row['a'] else 0
        
        trend_txt = "declining" if c > a else "stable or improving"
        eff_txt = "moderate"
        
        return jsonify({"insight": f"Groundwater levels are {trend_txt}. Recharge efficiency is {eff_txt}. Conservation measures recommended."})
    except Exception:
        return jsonify({"insight": "Groundwater levels are declining. Recharge efficiency is moderate. Conservation measures recommended."})

@app.route('/api/report')
def report():
    try:
        state = request.args.get('state', 'All India')
        district = request.args.get('district', 'N/A')
        block = request.args.get('block', 'N/A')
        village = request.args.get('village', 'N/A')
        temp = request.args.get('temp', '--')
        humidity = request.args.get('humidity', '--')
        rainfall = request.args.get('rainfall', '--')
        req_dtwl = request.args.get('dtwl', '--')
        req_avg_dtwl = request.args.get('avg_dtwl', '--')

        where_clause, params = build_filters(request.args)
        
        # 1. KPI Data
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(f"SELECT AVG(dtwl) as overall, MAX(dtwl) as current, AVG(dtwl) FILTER (WHERE season ILIKE 'Premonsoon') as pre, AVG(dtwl) FILTER (WHERE season ILIKE 'Postmonsoon') as post FROM groundwater_data {where_clause}", params)
                kpi_res = cur.fetchone()
        
        o_dtwl = round(kpi_res['overall'], 2) if kpi_res and kpi_res['overall'] else '--'
        c_dtwl = round(kpi_res['current'], 2) if kpi_res and kpi_res['current'] else '--'
        pre = round(kpi_res['pre'], 2) if kpi_res and kpi_res['pre'] else '--'
        post = round(kpi_res['post'], 2) if kpi_res and kpi_res['post'] else '--'

        health_score = 65
        trend = "Improving"
        if o_dtwl != '--':
            if o_dtwl < 5: health_score = 90
            elif o_dtwl <= 10: health_score = 65
            else: health_score = 30
        
        health_expl = "This means groundwater is available but not in ideal condition. Water levels are slightly deep and may reduce further if usage continues."
        if health_score == 90: health_expl = "This means groundwater is in good condition. Water levels are stable and suitable for usage."
        elif health_score == 30: health_expl = "This means groundwater condition is poor. Water levels are very deep and immediate water-saving measures are required."

        days = round(c_dtwl / 0.05) if c_dtwl != '--' else '--'
        autonomy_expl = ""
        if days != '--':
            if days < 30: autonomy_expl = "Water may run out very soon."
            elif days <= 90: autonomy_expl = "Water is available but needs careful usage."
            else: autonomy_expl = "Water availability is stable."

        risk = "High" if health_score == 30 else "Medium" if health_score == 65 else "Low"
        
        forecast_html = "<ul>"
        try:
            query = f"SELECT EXTRACT(YEAR FROM CAST(date AS DATE)) as year, AVG(dtwl) as overall FROM groundwater_data {where_clause} GROUP BY year ORDER BY year LIMIT 5000"
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    res = cur.fetchall()
            if len(res) >= 2:
                years = np.array([int(r[0]) for r in res if r[0]]).reshape(-1, 1)
                values = np.array([float(r[1]) for r in res if r[1]])
                model = LinearRegression().fit(years, values)
                last_y = int(years[-1][0])
                fy = np.array([[last_y + i] for i in range(1, 6)])
                preds = model.predict(fy)
                for y, v in zip(fy, preds):
                    forecast_html += f"<li>{int(y[0])}: Expected {round(float(v), 2)} m</li>"
            else:
                forecast_html += "<li>Insufficient data for forecast</li>"
        except Exception:
            forecast_html += "<li>Error computing forecast</li>"
        forecast_html += "</ul>"

        alerts_html = ""
        insights_text = "Groundwater levels in this region are moderately stable but show a declining trend. Recharge after rainfall is limited, so careful water usage is recommended."
        try:
            query_alerts = f"SELECT dtwl FROM groundwater_data {where_clause} ORDER BY date ASC LIMIT 5000"
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query_alerts, params)
                    res_a = cur.fetchall()
            
            if res_a:
                d_vals = [float(r[0]) for r in res_a if r[0] is not None]
                if d_vals:
                    a_dtwl = sum(d_vals) / len(d_vals)
                    if a_dtwl > 10:
                        alerts_html += "<li style='margin-bottom: 12px;'><strong>⚠ Groundwater level is very deep</strong><br><em>Reason:</em> Water is found deep below the ground, making it difficult to extract.<br><em>Impact:</em> Farmers may face water shortage or increased drilling cost.<br><em>Recommendation:</em> Use drip irrigation and avoid excessive water usage.</li>"
                    
                    if d_vals[-1] > d_vals[0]:
                        alerts_html += "<li style='margin-bottom: 12px;'><strong>⚠ Groundwater trend is declining</strong><br><em>Reason:</em> Water level is reducing year by year.<br><em>Impact:</em> Future water availability could be at risk if extraction continues.<br><em>Recommendation:</em> Adopt crop rotation with less water-intensive crops.</li>"

            if not alerts_html:
                alerts_html += "<li style='margin-bottom: 12px;'><strong>✅ Groundwater levels are stable</strong><br><em>Reason:</em> Current extraction is balanced with natural recharge.<br><em>Impact:</em> Water availability is sufficient for current agricultural needs.<br><em>Recommendation:</em> Continue standard water management practices.</li>"
                insights_text = "Groundwater levels in this region are stable. Recharge after rainfall is sufficient, and current water usage is sustainable."
        except Exception:
            alerts_html = "<li>Unable to load detailed alerts.</li>"

        ai_crops = get_ai_crop_recommendations(state, district, block, village, req_dtwl, req_avg_dtwl, temp, humidity, rainfall)
        
        def build_crop_list(crops):
            if not crops:
                return "<li><em>No crops available for this category</em></li>"
            return "".join([f"<li><strong>{c.get('crop', 'Unknown')}</strong> &rarr; {c.get('reason', '')}</li>" for c in crops])
            
        ai_crops_html = f"""
            <h3>Suitable Crops</h3>
            <ul>{build_crop_list(ai_crops.get('suitable', []))}</ul>
            <h3>Moderate Crops</h3>
            <ul>{build_crop_list(ai_crops.get('moderate', []))}</ul>
            <h3>Not Recommended Crops</h3>
            <ul>{build_crop_list(ai_crops.get('not_recommended', []))}</ul>
        """

        html = f"""
        <html>
        <head>
            <title>Groundwater Health Report</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 40px; color: #1e293b; line-height: 1.6; max-width: 800px; margin: auto; }}
                h1, h2, h3 {{ color: #0f172a; margin-top: 0; }}
                .section {{ margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid #e2e8f0; }}
                ul {{ margin: 0; padding-left: 20px; }}
                li {{ margin-bottom: 8px; }}
            </style>
        </head>
        <body>
            <h1>Groundwater Health & Analytics Report</h1>
            <p><strong>Generated by HydraX Decision-Support System</strong></p>
            
            <div class="section">
                <h2>1. Selected Region</h2>
                <ul>
                    <li><strong>State:</strong> {state}</li>
                    <li><strong>District:</strong> {district}</li>
                    <li><strong>Block:</strong> {block}</li>
                    <li><strong>Village:</strong> {village}</li>
                </ul>
            </div>

            <div class="section">
                <h2>2. Overview Metrics</h2>
                <ul>
                    <li><strong>Overall DTWL:</strong> {o_dtwl} m</li>
                    <li><strong>Current DTWL:</strong> {c_dtwl} m</li>
                    <li><strong>Premonsoon Average:</strong> {pre} m</li>
                    <li><strong>Postmonsoon Average:</strong> {post} m</li>
                    <li><strong>Temperature:</strong> {temp}°C</li>
                    <li><strong>Humidity:</strong> {humidity}%</li>
                    <li><strong>Rainfall:</strong> {rainfall} mm</li>
                </ul>
            </div>

            <div class="section">
                <h2>3. Advanced Analytics</h2>
                <ul>
                    <li><strong>Health Score:</strong> {health_score} - <em>{health_expl}</em></li>
                    <li><strong>Trend:</strong> {trend}</li>
                    <li><strong>Days of Autonomy:</strong> {days} Days - <em>{autonomy_expl}</em></li>
                    <li><strong>Risk Level:</strong> {risk}</li>
                </ul>
            </div>

            <div class="section">
                <h2>4. Forecast (Next 5 Years)</h2>
                {forecast_html}
            </div>

            <div class="section">
                <h2>5. Smart Alerts</h2>
                <ul style="list-style-type: none; padding: 0;">
                    {alerts_html}
                </ul>
            </div>

            <div class="section">
                <h2>6. Insights Summary</h2>
                <p>{insights_text}</p>
            </div>
            
            <div class="section">
                <h2>7. AI Crop Recommendation</h2>
                {ai_crops_html}
            </div>
            
            <script>window.print();</script>
        </body>
        </html>
        """
        return html
    except Exception as e:
        return f"Error generating report: {{str(e)}}"

@app.route('/')
def home():
    return "Backend Running Successfully 🚀"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
