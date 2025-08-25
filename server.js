// server.js (full, amended)

const express = require("express");
const cors = require("cors");
const multer = require("multer");
const path = require("path");
const fs = require("fs");

// ---- make fetch work everywhere (Node >=18 has fetch; else lazy import node-fetch)
const fetch =
  global.fetch ||
  ((...args) => import("node-fetch").then(({ default: f }) => f(...args)));

const app = express();
app.use(cors());
app.use(express.json());

// ---------- file uploads (unchanged) ----------
const upload = multer({ dest: "uploads/" });
app.post("/documents/upload", upload.single("file"), (req, res) => {
  if (!req.file) return res.status(400).json({ error: "No file uploaded" });
  const filePath = path.join(__dirname, req.file.path);
  let size = 0;
  try {
    size = fs.statSync(filePath).size;
  } catch {}
  return res.json({
    name: req.file.originalname,
    summary: `Placeholder summary. File size: ${size} bytes.`,
  });
});

// ---------- helpers: geocoding + distance ----------
async function geocodePlace(name) {
  // Open-Meteo Geocoding (free, no API key)
  const url = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(
    name
  )}&count=1&language=en&format=json`;
  const r = await fetch(url);
  if (!r.ok) {
    console.error("[Geocode] Bad response", r.status, url);
    return null;
  }
  const data = await r.json();
  const first = data?.results?.[0];
  if (!first) {
    console.warn("[Geocode] No results for:", name);
    return null;
  }
  return {
    name: first.name,
    country: first.country || "",
    lat: first.latitude,
    lon: first.longitude,
  };
}

function toRadians(d) {
  return (d * Math.PI) / 180;
}
function greatCircleNm(a, b) {
  // Haversine distance in nautical miles
  const R_km = 6371;
  const dLat = toRadians(b.lat - a.lat);
  const dLon = toRadians(b.lon - a.lon);
  const lat1 = toRadians(a.lat);
  const lat2 = toRadians(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  const d_km = 2 * R_km * Math.asin(Math.min(1, Math.sqrt(h)));
  const d_nm = d_km * 0.539957; // km -> nautical miles
  return d_nm;
}

// ---------- marine weather helper with fallback ----------
async function tryMarine(lat, lon) {
  const url = `https://marine-api.open-meteo.com/v1/marine?latitude=${lat}&longitude=${lon}&hourly=wave_height,wind_speed,wind_wave_direction&timezone=auto`;
  const r = await fetch(url);
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    console.warn("[Marine] HTTP", r.status, url, text.slice(0, 120));
    return null;
  }
  const data = await r.json();
  const h = data?.hourly;
  if (!h || !h.time?.length) {
    console.warn("[Marine] No hourly data for", lat, lon);
    return null;
  }
  return {
    time: h.time[0],
    wave: h.wave_height?.[0] ?? null,
    wind: h.wind_speed?.[0] ?? null,
    waveDir: h.wind_wave_direction?.[0] ?? null,
    usedLat: lat,
    usedLon: lon,
  };
}

async function getMarineWeatherNear(lat, lon) {
  // Many ports are inland; the marine API often rejects land points (HTTP 400).
  // Strategy: try the exact point; if null, try small offsets around it.
  const offsets = [0, 0.25, -0.25, 0.5, -0.5, 0.75, -0.75, 1, -1];
  for (const dlat of offsets) {
    for (const dlon of offsets) {
      const cand = await tryMarine(lat + dlat, lon + dlon);
      if (cand) return cand;
    }
  }
  return null;
}

// ---------- land weather fallback ----------
async function getLandWeather(lat, lon) {
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current_weather=true&timezone=auto`;
  const r = await fetch(url);
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    console.warn("[Land WX] HTTP", r.status, url, text.slice(0, 120));
    return null;
  }
  const data = await r.json();
  return data?.current_weather || null;
}

// ---------- chat endpoint ----------
app.post("/chat", async (req, res) => {
  const message = (req.body?.message || "").trim();
  if (!message) return res.json({ reply: "Please type a question." });

  // ---------------- Distance (intact) ----------------
  const distMatch = message.match(
    /distance\s+([A-Za-z\s]+?)\s+(?:to|->)\s+([A-Za-z\s]+)$/i
  );
  if (distMatch) {
    const fromName = distMatch[1].trim();
    const toName = distMatch[2].trim();
    try {
      const [from, to] = await Promise.all([
        geocodePlace(fromName),
        geocodePlace(toName),
      ]);
      if (!from)
        return res.json({
          reply: `I couldn't find "${fromName}". Try another port/city name.`,
        });
      if (!to)
        return res.json({
          reply: `I couldn't find "${toName}". Try another port/city name.`,
        });

      const nm = greatCircleNm(from, to);
      const nmRounded = Math.round(nm); // neat round nm

      const reply =
        `📏 Great-circle distance:\n` +
        `• ${from.name}, ${from.country} (${from.lat.toFixed(
          3
        )}, ${from.lon.toFixed(3)})\n` +
        `→ ${to.name}, ${to.country} (${to.lat.toFixed(3)}, ${to.lon.toFixed(
          3
        )})\n` +
        `= **${nmRounded} nautical miles** (approx., rhumb lines not included).`;

      return res.json({ reply });
    } catch (e) {
      console.error("[Distance] Error:", e);
      return res.json({ reply: "⚠️ Distance service error. Please try again." });
    }
  }

  // ---------------- Marine Weather (with robust fallback) ----------------
  const weatherMatch = message.match(/weather\s+(?:at|in)\s+([A-Za-z\s]+)$/i);
  if (weatherMatch) {
    const placeName = weatherMatch[1].trim();

    try {
      // 1) Geocode
      const place = await geocodePlace(placeName);
      if (!place)
        return res.json({
          reply: `I couldn’t find "${placeName}". Try another port/city.`,
        });

      // 2) Try marine first (waves + wind). If null, fallback to land weather.
      const marine = await getMarineWeatherNear(place.lat, place.lon);

      if (marine && (marine.wave != null || marine.wind != null)) {
        let alert = "";
        if (typeof marine.wave === "number" && marine.wave > 3) {
          alert = "\n⚠️ Storm warning: High waves expected!";
        }
        const reply =
          `🌊 Marine Weather for **${place.name}, ${place.country}**\n` +
          `At ${marine.time} (local):\n` +
          `• Wave height: ${
            marine.wave != null ? `${marine.wave} m` : "n/a"
          }\n` +
          `• Wind speed: ${
            marine.wind != null ? `${marine.wind} m/s` : "n/a"
          }\n` +
          `• Wave direction: ${
            marine.waveDir != null ? `${marine.waveDir}°` : "n/a"
          }\n` +
          `• Grid used: (${marine.usedLat.toFixed(2)}, ${marine.usedLon.toFixed(
            2
          )})` +
          alert;

        return res.json({ reply });
      }

      // 3) Land weather fallback (no waves, but at least wind/temp)
      const land = await getLandWeather(place.lat, place.lon);
      if (land) {
        const reply =
          `🌍 Weather for **${place.name}, ${place.country}** (land fallback)\n` +
          `• Temperature: ${land.temperature} °C\n` +
          `• Windspeed: ${land.windspeed} km/h\n` +
          `• Wind direction: ${land.winddirection}°\n` +
          `• Time: ${land.time}\n` +
          `• Note: Marine grid not available right at this point; moved to land weather.`;

        return res.json({ reply });
      }

      // 4) If everything failed:
      return res.json({
        reply:
          "⚠️ Weather service error (marine & land). Please try again with another nearby coastal location.",
      });
    } catch (e) {
      console.error("[Weather] Error:", e);
      return res.json({
        reply: "⚠️ Error fetching weather. Try again later.",
      });
    }
  }

  // ---------------- Default ----------------
  return res.json({
    reply: `You asked: "${message}". This is a test response from backend.`,
  });
});

// ---------- health check ----------
app.get("/", (_req, res) =>
  res.send("✅ Maritime Assistant Backend is running!")
);

// ---------- start ----------
const PORT = 8000;
app.listen(PORT, () => {
  console.log(`✅ Backend running on http://localhost:${PORT}`);
});
