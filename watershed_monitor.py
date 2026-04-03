import os
import json
import time
import hashlib
import requests
from datetime import datetime, timezone, timedelta

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT = os.environ["TELEGRAM_CHAT_ID"]

REQUEST_TIMEOUT = 60
PAUSE = 5
STATE_FILE = "state.json"

# عدل النقاط كما تريد
POINTS = [
    {"name": "وادي حنيفة", "lat": 24.5000, "lng": 46.6000},
    {"name": "جدة", "lat": 21.5433, "lng": 39.1728},
    {"name": "الدمام", "lat": 26.4207, "lng": 50.0888},
]

WATERSHED = "https://mghydro.com/app/watershed_api"
RIVERS = "https://mghydro.com/app/upstream_rivers_api"
FLOW = "https://mghydro.com/app/flowpath_api"

MIN_AREA_KM2 = 10.0
MIN_USEFUL_FEATURES = 1


def now_ksa():
    return datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d %H:%M KSA")


def send(msg):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        data={
            "chat_id": CHAT,
            "text": msg,
            "disable_web_page_preview": True
        },
        timeout=REQUEST_TIMEOUT
    )
    r.raise_for_status()


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


def get_area(fc):
    try:
        return float(fc["features"][0]["properties"].get("area_km2", 0))
    except Exception:
        return 0.0


def count_features(fc):
    if not fc or "features" not in fc:
        return 0
    return len(fc["features"])


def calculate_score(area, rivers, flow):
    score = 0

    # مساحة الحوض
    if area > 100000:
        score += 40
    elif area > 50000:
        score += 30
    elif area > 10000:
        score += 20
    else:
        score += 10

    # عدد مقاطع الأنهار
    if rivers > 200:
        score += 40
    elif rivers > 100:
        score += 30
    elif rivers > 50:
        score += 20
    elif rivers > 0:
        score += 10

    # مسارات الجريان
    if flow > 100:
        score += 20
    elif flow > 50:
        score += 15
    elif flow > 10:
        score += 10
    elif flow > 0:
        score += 5

    return min(score, 100)


def classify(score):
    if score >= 80:
        return "🔴 عالي"
    elif score >= 60:
        return "🟠 متوسط مرتفع"
    elif score >= 40:
        return "🟡 متوسط"
    return "🟢 منخفض"


def interpret(area, rivers, flow):
    if area > 50000 and (rivers > 100 or flow > 50):
        return "الحوض كبير نسبيًا وشبكة الجريان واسعة، لذلك أي أمطار أو تلوث upstream قد يمتد أثره بشكل أكبر."
    elif area > 20000 or flow > 20:
        return "الحوض متوسط إلى كبير، ويستحق الربط مع رصد الأمطار أو أحداث التلوث."
    else:
        return "الحوض محدود نسبيًا، ويبدو أن التأثير المحتمل أكثر محلية."


def recommendation(score):
    if score >= 80:
        return "رفع الجاهزية وربط الموقع مباشرة مع رصد الأمطار والسيول أو التلوث."
    elif score >= 60:
        return "مراقبة مستمرة وربط النتائج مع أي تنبيهات بيئية أخرى."
    elif score >= 40:
        return "المتابعة الدورية مناسبة حاليًا."
    else:
        return "لا حاجة إلى تصعيد حاليًا، مع الاستمرار في المتابعة."


def signature(area, rivers, flow):
    raw = f"{round(area, 2)}|{rivers}|{flow}"
    return hashlib.md5(raw.encode()).hexdigest()


def is_useful_result(area, rivers, flow):
    if area < MIN_AREA_KM2:
        return False

    if rivers < MIN_USEFUL_FEATURES and flow < MIN_USEFUL_FEATURES:
        return False

    return True


def main():
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}

    logs = []
    sent = 0

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
            rivers = count_features(rv)
            flow = count_features(fl)

            if not is_useful_result(area, rivers, flow):
                logs.append(
                    f"{name}: تم التجاوز لأن النتيجة غير مفيدة أو الحوض صغير جدًا "
                    f"(area={area}, rivers={rivers}, flow={flow})."
                )
                continue

            sig = signature(area, rivers, flow)
            if state.get(name) == sig:
                logs.append(f"{name}: لا يوجد تغير.")
                continue

            score = calculate_score(area, rivers, flow)
            level = classify(score)

            msg = f"""🌊 تقرير الحوض المائي – تنبيه تشغيلي
🕒 {now_ksa()}
════════════════════
📍 الموقع: {name}
📌 الإحداثيات: {lat}, {lng}

📊 المؤشر التقريبي: {score}/100
📌 المستوى: {level}

🗺️ مساحة الحوض: {area:,.2f} كم²
🌿 عدد مقاطع الأنهار upstream: {rivers}
➡️ عدد مسارات الجريان downstream: {flow}

🧠 التفسير:
{interpret(area, rivers, flow)}

🧭 التوصية:
{recommendation(score)}

🔗 الخريطة:
https://maps.google.com/?q={lat},{lng}
"""

            send(msg)
            state[name] = sig
            sent += 1
            logs.append(f"{name}: تم الإرسال.")

        except Exception as e:
            logs.append(f"{name}: خطأ - {e}")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print("🧪 ملخص التشغيل")
    print(f"Checked: {len(POINTS)}")
    print(f"Sent: {sent}")
    print("------")
    for x in logs:
        print(x)


if __name__ == "__main__":
    main()
