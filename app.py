from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime as dt
import math
import os
import re
import requests
from difflib import get_close_matches
from werkzeug.utils import secure_filename

# ---- External helpers that call free live APIs ----
from api_helpers import get_port_coordinates, get_weather

# ---- Optional: LLM engines (OpenAI primary, Ollama fallback) ----
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

# OCR + PDF helpers
from pdf2image import convert_from_path
import pytesseract
import PyPDF2

# ------------------ Flask Config ------------------
app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB limit

# ------------------ Aliases for Sailor-friendly Names ------------------
PORT_ALIASES = {
    "kandla": "deendayal",
    "bombay": "mumbai",
    "cochin": "kochi",
    "madras": "chennai",
    "calcutta": "kolkata",
    "vizag": "visakhapatnam",
    "new york": "new york harbor",
    "rotterd": "rotterdam",
    "singa": "singapore",
    "shangai": "shanghai",
    "abudhabi": "abu dhabi",
    "jebelali": "jebel ali",
    "kandla port": "deendayal",
}

# ------------------ Laytime Rules (sample) ------------------
LAYTIME_RULES = {
    "mumbai": 72,
    "dubai": 96,
    "singapore": 84,
    "rotterdam": 120,
    "shanghai": 90
}

# ------------------ Utilities ------------------
EARTH_RADIUS_NM = 3440.065  # Nautical miles

def _to_radians(deg: float) -> float:
    return deg * math.pi / 180.0

def haversine_nm(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    dlat = _to_radians(b_lat - a_lat)
    dlon = _to_radians(b_lon - a_lon)
    lat1 = _to_radians(a_lat)
    lat2 = _to_radians(b_lat)
    h = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(h))

def distance_between_vessels(lat1, lon1, lat2, lon2):
    return haversine_nm(float(lat1), float(lon1), float(lat2), float(lon2))

def build_alerts(port_key: str):
    port = (port_key or "").lower().strip()
    alerts = []
    if port == "mumbai":
        alerts.append("⚠ Cyclonic activity expected in Arabian Sea, exercise caution.")
    if port == "dubai":
        alerts.append("⚠ High temperature alert, ensure crew hydration and engine cooling.")
    return alerts or ["✅ No major alerts reported."]

# ------------------ Location Helper ------------------
def get_location_from_ip(ip=None):
    try:
        if not ip or ip.startswith(("127.", "192.168.")) or ip == "0.0.0.0":
            ip = requests.get("https://api.ipify.org", timeout=5).text.strip()
        resp = requests.get(f"http://ip-api.com/json/{ip}", timeout=5).json()
        if resp.get("status") == "success":
            city = resp.get("city", "Unknown city")
            country = resp.get("country", "Unknown country")
            lat, lon = resp.get("lat"), resp.get("lon")
            return f"Your vessel is near {city}, {country} (lat: {lat}, lon: {lon}).", lat, lon
        return "Location could not be determined.", None, None
    except Exception as e:
        return f"Error fetching location: {str(e)}", None, None

# ------------------ Port Resolver ------------------
def normalize_port_name(name: str) -> str:
    raw = (name or "").lower().strip()
    return PORT_ALIASES.get(raw, raw)

def resolve_port(name: str):
    if not name:
        return None, None
    query = normalize_port_name(name)
    for attempt in (query, f"Port of {query}", f"{query} port"):
        coords = get_port_coordinates(attempt)
        if coords:
            return attempt.title(), coords
    return None, None

# ------------------ LLM Helper ------------------
def ask_llm_general(user_message: str, engine: str = None) -> str:
    engine = (engine or "").lower()
    openai_key = os.getenv("OPENAI_API_KEY")

    system_prompt = (
        "You are a helpful maritime and general knowledge assistant. "
        "Answer clearly and concisely. Use system time for current date/time."
    )

    def _try_openai():
        try:
            from openai import OpenAI
            client = OpenAI()
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_message}],
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return None

    def _try_ollama():
        try:
            import ollama
            resp = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_message}],
            )
            return resp["message"]["content"].strip()
        except Exception:
            return None

    if engine == "openai":
        return _try_openai() or _try_ollama() or "(AI unavailable)"
    if engine == "ollama":
        return _try_ollama() or _try_openai() or "(AI unavailable)"
    if openai_key:
        return _try_openai() or _try_ollama() or "(AI unavailable)"
    return _try_ollama() or "(AI unavailable)"

# ------------------ Chat Endpoint ------------------
@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message", "") or "").strip().lower()
    engine = (payload.get("engine") or "").strip().lower()

    try:
        if user_message.startswith("distance"):
            txt = user_message.replace("distance", "", 1).strip()
            if txt.startswith("from "):
                txt = txt[5:].strip()
            if " to " not in txt:
                return jsonify({"reply": "Please use 'distance <from> to <to>'."})
            from_name, to_name = map(str.strip, txt.split(" to ", 1))
            f_disp, f_coords = resolve_port(from_name)
            t_disp, t_coords = resolve_port(to_name)
            if f_coords and t_coords:
                nm = haversine_nm(*f_coords, *t_coords)
                return jsonify({"reply": f"Distance from {f_disp} to {t_disp} is {round(nm,1)} nautical miles."})
            return jsonify({"reply": f"Could not resolve '{from_name}' or '{to_name}'."})

        if user_message.startswith("weather"):
            port_phrase = user_message.replace("weather", "", 1).strip()
            if port_phrase.startswith("at "):
                port_phrase = port_phrase[3:].strip()
            if not port_phrase or "my location" in port_phrase:
                ip = request.remote_addr
                loc_text, lat, lon = get_location_from_ip(ip)
                if lat and lon:
                    return jsonify({"reply": f"{loc_text} Weather: {get_weather(lat, lon)}"})
                return jsonify({"reply": loc_text})
            disp, coords = resolve_port(port_phrase)
            if coords:
                return jsonify({"reply": f"Weather at {disp}: {get_weather(*coords)}"})
            return jsonify({"reply": f"Could not find '{port_phrase}'."})

        if user_message.startswith("alert"):
            port = re.search(r"at (.+)$", user_message)
            port = port.group(1).strip() if port else "mumbai"
            disp, _ = resolve_port(port)
            alerts = build_alerts((disp or port).lower())
            return jsonify({"reply": f"Alerts at {(disp or port).title()}: " + ' '.join(alerts)})

        if "location" in user_message or "where am i" in user_message:
            ip = request.remote_addr
            loc_text, _, _ = get_location_from_ip(ip)
            return jsonify({"reply": loc_text})

        if "laytime" in user_message:
            m = re.search(r"at (.+)$", user_message)
            if m:
                port = m.group(1).strip().lower()
                hours = LAYTIME_RULES.get(port)
                if hours:
                    return jsonify({"reply": f"Laytime at {port.title()} is {hours} hours."})
                return jsonify({"reply": f"No laytime data for {port}. Known: {', '.join(LAYTIME_RULES)}"})
            return jsonify({"reply": "Laytime is the time allowed for loading/unloading in charter parties."})

        return jsonify({"reply": ask_llm_general(user_message, engine=engine)})

    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"})

# ------------------ CP Document Upload + Parse API ------------------
@app.route("/upload_cp", methods=["POST"])
def upload_cp():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    extracted = ""
    try:
        if filename.lower().endswith(".txt"):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                extracted = f.read()

        elif filename.lower().endswith(".pdf"):
            # First try PyPDF2 text extraction
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    extracted += (page.extract_text() or "") + "\n"

            # Fallback: OCR if PDF text is too small (likely scanned CP)
            if len(extracted.strip()) < 100:
                pages = convert_from_path(filepath)
                extracted = ""
                for page in pages:
                    extracted += pytesseract.image_to_string(page) + "\n"

    except Exception as e:
        extracted = f"(Could not extract text: {str(e)})"

    # Regex patterns to catch whole clauses (multi-line)
    patterns = {
        "Laytime": r"(?is)laytime.*?(?=\n\s*\n|$)",
        "Demurrage": r"(?is)demurrage.*?(?=\n\s*\n|$)",
        "Dispatch": r"(?is)dispatch.*?(?=\n\s*\n|$)",
        "Notice of Readiness": r"(?is)(notice of readiness|NOR).*?(?=\n\s*\n|$)",
        "Freight": r"(?is)freight.*?(?=\n\s*\n|$)",
        "Arbitration": r"(?is)arbitration.*?(?=\n\s*\n|$)",
        "Law": r"(?is)(law|applicable law).*?(?=\n\s*\n|$)",
        "Clause Numbers": r"(?im)^clause\s+\d+.*?(?=\n\s*\n|$)"
    }

    summary = {}
    for key, pattern in patterns.items():
        matches = re.findall(pattern, extracted)
        if matches:
            summary[key] = [m.strip() for m in matches]

    # Fallback: if nothing found, let LLM summarize the CP
    if not summary and extracted and len(extracted) > 50:
        ai_summary = ask_llm_general(f"Summarize this charter party contract:\n\n{extracted[:4000]}")
        summary = {"note": "No structured clauses matched with regex.", "llm_summary": ai_summary}

    return jsonify({
        "message": f"File {filename} uploaded successfully!",
        "summary": summary or {"note": "No content extracted"},
        "path": filepath
    })

@app.route("/documents/upload", methods=["POST"])
def upload_document():
    return upload_cp()

# ------------------ Main ------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
