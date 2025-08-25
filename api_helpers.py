import requests

# Base URLs for free services
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

def get_port_coordinates(port_name, country=None):
    """
    Get latitude & longitude of a port using OpenStreetMap (Nominatim API).
    """
    query = port_name if not country else f"{port_name}, {country}"
    params = {"q": query, "format": "json", "limit": 1}
    response = requests.get(
        NOMINATIM_URL, 
        params=params, 
        headers={"User-Agent": "maritime-assistant"}
    )
    data = response.json()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])

def get_weather(lat, lon):
    """
    Get live weather info from Open-Meteo API.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": True
    }
    response = requests.get(OPEN_METEO_URL, params=params)
    data = response.json()
    return data.get("current_weather", {})

def query_ollama(prompt, model="llama3.1:8b"):
    """
    Send a prompt to a locally running Ollama model and return its response.
    Requires Ollama running locally (http://localhost:11434).
    """
    try:
        url = "http://localhost:11434/api/generate"
        payload = {"model": model, "prompt": prompt}
        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()

        # Concatenate streaming chunks
        output = ""
        for line in response.iter_lines():
            if line:
                chunk = line.decode("utf-8")
                try:
                    data = eval(chunk)  # parse JSON-like response
                    output += data.get("response", "")
                except Exception:
                    continue
        return output.strip()
    except Exception as e:
        return f"Ollama error: {e}"
