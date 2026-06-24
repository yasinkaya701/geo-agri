# 🛰️ GEO-AGRI — Agricultural Remote Sensing Platform

> Premium agricultural intelligence dashboard powered by Google Earth Engine, Sentinel-2, and Cesium.js 3D flyover technology.

[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![GEE](https://img.shields.io/badge/Google_Earth_Engine-4285F4?logo=google&logoColor=white)](https://earthengine.google.com)
[![Sentinel-2](https://img.shields.io/badge/Sentinel--2-003247?logo=esa&logoColor=white)](https://sentinel.esa.int)

## Features

| Feature | Description |
|---|---|
| 📊 **NDVI / NDWI / EVI Zaman Serisi** | Bulut arındırılmış Sentinel-2 ile tarla bazlı spektral indeksler |
| 🌱 **Fenoloji Analizi** | Ekim, çiçeklenme, hasat dönemlerinin otomatik tespiti |
| 🛰️ **GEE Zaman Tüneli** | Google Earth Engine ile yıllık tarihsel değişim animasyonu |
| 🚁 **Cesium.js 3D Drone Flyover** | Gerçek Bing uydu + SRTM arazi üzerinde canlı 3D uçuş |
| 🌍 **3D GEE Video** | SRTM DEM + Sentinel-2 ile perspektif kamera timelapse |
| 🧠 **ML Dataset Studio** | CNN/ViT modelleri için patch extraction + augmentation |

## Quick Start

```bash
# 1. Sanal ortam
python -m venv .venv && source .venv/bin/activate

# 2. Bağımlılıklar
pip install -r requirements.txt

# 3. GEE kimlik doğrulama
earthengine authenticate --project earth-500319

# 4. Çalıştır
streamlit run app.py
```

## Deploy — Streamlit Community Cloud

1. Repoyu GitHub'a push et
2. [share.streamlit.io](https://share.streamlit.io) → **New app** → Bu repo
3. **Secrets** kısmına ekle:
   ```toml
   [gee]
   project = "earth-500319"
   ```
4. Deploy!

## Architecture

```
app.py                          # Ana Streamlit uygulaması
src/
  ui/
    styles.py                   # Premium CSS tasarım sistemi
    cesium_flyover.py           # Cesium.js 3D drone bileşeni
    components.py               # TKGM parsel seçici, Folium harita
  satellite/
    stac_client.py              # Planetary Computer STAC
    bands_loader.py             # Sentinel-2 band yükleme + Esri imagery
    gee_timelapse.py            # GEE timelapse engine
    drone_simulator.py          # Sentetik UAV simülasyonu
  dataset/
    ndvi.py                     # Spektral indeksler + fenoloji
    ml_generator.py             # ML dataset üretimi
google_earth_3d_timelapse/
  gee_3d_timelapse.py           # GEE SRTM + perspektif 3D render
  generate_3d_timelapse.py      # Offline 3D timelapse (matplotlib fallback)
```

## Data Sources

- **Imagery**: Sentinel-2 L2A (Planetary Computer STAC + GEE)
- **Elevation**: SRTM 30m (USGS via GEE + OpenTopography)
- **3D Flyover**: Cesium World Terrain + Bing Aerial
- **Parcel**: TKGM MEGSIS Kadastro API

---
*GEO-AGRI v2.0 · Agricultural Remote Sensing Platform*
