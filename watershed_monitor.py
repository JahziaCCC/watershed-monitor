import os
import json
import time
import hashlib
import requests
from datetime import datetime, timezone, timedelta

# =========================
# ENV
# =========================
BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT = os.environ["TELEGRAM_CHAT_ID"]

REQUEST_TIMEOUT = 60
PAUSE = 5
STATE_FILE = "state.json"

# =========================
# نقاط الرصد (عدلها)
# =========================
POINTS = [
    {"name": "وادي حنيفة", "lat": 24.5000, "lng": 46.6000},
    {"name": "جدة", "lat": 21.5433, "lng": 39.1728},
    {"name": "الدمام", "lat": 26.4207, "lng": 50.0888},
]

# =========================
# API
# =========================
WATERSHED = "https://mghydro.com/app/watershed_api"
RIVERS = "https://mghydro.com/app/upstream_rivers_api"
FLOW = "https://mghydro.com/app/flowpath_api"

MIN_AREA_KM2 = 10.0

# =========================
# TIME
# =========================
def now_ksa():
    return datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d %H:%M KSA")

# =========================
# TELEGRAM
# =========================
def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        data={"chat_id": CHAT, "text": msg, "disable_web_page_preview": True},
        timeout=REQUEST_TIMEOUT
    )

# =========================
# API CALL
# =========================
def fetch(url, lat, lng):
    params = {
        "lat": lat,
        "lng": lng,
        "precision": "high",
        "simplify": "false",
        "beautify": "false",
    }

    r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)

    if r.status_code == 404:
        return None

    r.raise_for_status()
    return r.json()

# =========================
# DATA
# =========================
def get_area(fc):
    try:
        return float(fc["features"][0]["properties"].get("area_km2", 0))
    except:
        return 0.0

def count(fc):
    return len(fc["features"]) if fc and "features" in fc else 0

# =========================
# RISK ENGINE (معدل للبيئة الصحراوية)
# =========================
def calculate_score(area, flow):
    score = 0

    # حجم الحوض
    if area > 100000:
        score += 30
    elif area > 50000:
        score += 25
    elif area > 10000:
        score += 20
    else:
        score += 10

    # الأهم: flowpath (الأودية)
    if flow > 150:
        score += 50
    elif flow > 100:
        score += 40
    elif flow > 50:
        score += 30
    elif flow > 20:
        score += 20
    elif flow > 5:
        score += 10

    return min(score, 100)

def classify(score):
    if score >= 80:
        return "🔴 عالي"
    elif score >= 60:
        return "🟠 متوسط مرتفع"
    elif score >= 40:
        return "🟡 متوسط"
    return "🟢 منخفض"

# =========================
# تفسير احترافي
# =========================
def interpret(area, flow):
    if flow > 100:
        return "شبكة الأودية داخل الحوض واسعة، مما يزيد احتمالية انتقال السيول أو التلوث بسرعة."
    elif flow > 50:
        return "يوجد عدد ملحوظ من مسارات الجريان (Wadis)، ويستحسن ربطها برصد الأمطار."
    elif area > 20000:
        return "الحوض متوسط إلى كبير، وقد يتأثر بالأحداث البيئية في المنبع."
    else:
        return "الحوض محدود نسبيًا والتأثير غالبًا محلي."

def recommendation(score):
    if score >= 80:
        return "رفع الجاهزية وربط الموقع مباشرة مع رصد الأمطار والسيول."
    elif score >= 60:
        return "مراقبة مستمرة وربط النتائج مع أي تنبيهات بيئية."
    elif score >= 40:
        return "المتابعة الدورية مناسبة."
    else:
        return "لا حاجة إلى تصعيد حاليًا."

# =========================
# SIGNATURE
# =========================
def signature(area, flow):
    raw = f"{round(area,2)}|{flow}"
    return hashlib.md5(raw.encode()).hexdigest()

# =========================
# FILTER
# =========================
def is_valid(area, flow):
    if area < MIN_AREA_KM2:
        return False
    if flow < 5:
        return False
    return True

# =========================
# MAIN
# =========================
def run():
    state = {}

    if os.path.exists(STATE_FILE):
        state = json.load(open(STATE_FILE))

    for p in POINTS:
        name = p["name"]
        lat = p["lat"]
        lng = p["lng"]

        try:
            ws = fetch(WATERSHED, lat, lng)
            time.sleep(PAUSE)

            rv = fetch(RIVERS, lat, lng)
            time.sleep(PAUSE)

            fl = fetch(FLOW, lat, lng)
            time.sleep(PAUSE)

            area = get_area(ws)
            flow = count(fl)

            # فلترة
            if not is_valid(area, flow):
                continue

            sig = signature(area, flow)

            if state.get(name) == sig:
                continue

            score = calculate_score(area, flow)
            level = classify(score)

            msg = f"""🌊 تقرير الحوض المائي – تنبيه تشغيلي
🕒 {now_ksa()}
════════════════════
📍 الموقع: {name}
📌 الإحداثيات: {lat}, {lng}

📊 مؤشر المخاطر: {score}/100
📌 المستوى: {level}

🗺️ مساحة الحوض: {area:,.2f} كم²
➡️ عدد مسارات الجريان (Wadis): {flow}

🧠 التفسير:
{interpret(area, flow)}

🧭 التوصية:
{recommendation(score)}

🔗 الخريطة:
https://maps.google.com/?q={lat},{lng}
"""

            send(msg)
            state[name] = sig

        except Exception as e:
            print("Error:", e)

    json.dump(state, open(STATE_FILE, "w"))

if __name__ == "__main__":
    run()
