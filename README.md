# 🛰️ GEO-AGRI — Agricultural Remote Sensing Platform

> **Next-generation precision agriculture intelligence platform:** A premium integrated solution combining Google Earth Engine, Sentinel-2 satellite imagery, and Cesium.js 3D technology for advanced geospatial analysis and crop monitoring.

<div align="center">

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Google Earth Engine](https://img.shields.io/badge/Google_Earth_Engine-4285F4?logo=google&logoColor=white)](https://earthengine.google.com)
[![Sentinel-2](https://img.shields.io/badge/Sentinel--2-003247?logo=esa&logoColor=white)](https://sentinel.esa.int)
[![Cesium.js](https://img.shields.io/badge/Cesium.js-1F4788?logo=cesium&logoColor=white)](https://cesium.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[🌐 Live Demo](#demo) • [🚀 Quick Start](#quick-start) • [📚 Documentation](#documentation) • [💡 Features](#features) • [🤝 Contributing](#contributing)

</div>

---

## 📋 Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Usage Guide](#usage-guide)
- [Data Sources](#data-sources)
- [Deployment](#deployment)
- [API Documentation](#api-documentation)
- [Troubleshooting](#troubleshooting)
- [License & Attribution](#license--attribution)

---

## 🎯 Features

### 📊 Spectral Analysis & Vegetation Indices
| Feature | Description |
|---------|-------------|
| **NDVI / NDWI / EVI** | Cloud-free Sentinel-2 satellite data with field-level spectral indices and comprehensive time series analysis |
| **Advanced Vegetation Indices** | GNDVI, SAVI, MSAVI2, and other specialized indices for real-time plant stress detection |
| **Temporal Trend Analysis** | Seasonal variability detection, extrema identification, and predictive modeling |

### 🌱 Phenology & Agronomic Assessment
| Feature | Description |
|---------|-------------|
| **Automated Phenology Detection** | AI-powered automatic identification of planting, flowering, and harvest stages |
| **Yield Estimation** | Crop yield projections based on historical data and spectral signatures |
| **Field Heterogeneity Analysis** | Sub-field variability mapping and zoning |

### 🛰️ Satellite Data & Time-Lapse
| Feature | Description |
|---------|-------------|
| **GEE Time-Lapse Engine** | Annual and monthly historical change animations via Google Earth Engine |
| **Sentinel-2 L2A Integration** | Low-cloud coverage data with 10-day revisit frequency |
| **STAC Catalog Access** | Advanced querying and data retrieval via Planetary Computer |

### 🚁 3D Visualization & UAV Simulation
| Feature | Description |
|---------|-------------|
| **Cesium.js 3D Drone Flyover** | Interactive 3D flight visualization with real Bing satellite imagery and SRTM terrain |
| **Interactive Camera Controls** | Real-time zoom, rotation, pitch, and speed adjustments |
| **3D GEE Perspective Time-Lapse** | SRTM DEM with Sentinel-2 colored perspective camera sequences |
| **UAV Route Planning** | Waypoint-based mission generation and flight simulation |

### 🧠 Machine Learning & Dataset Studio
| Feature | Description |
|---------|-------------|
| **Production-Ready Dataset Generation** | Automatic patch extraction, class balancing, and augmentation for CNN/ViT models |
| **Multi-Model Support** | ResNet, EfficientNet, and Vision Transformer compatibility |
| **Classification Tasks** | Land cover classification, crop health assessment, soil moisture prediction |
| **Standard Format Export** | COCO format output for object detection and instance segmentation |

### 🌍 Geospatial & Cadastral Integration
| Feature | Description |
|---------|-------------|
| **Cadastral Parcel Lookup** | Turkish Land Registry (TKGM) MEGSIS API integration for official field boundaries |
| **Flexible Geospatial Queries** | Coordinate-based or WKT polygon input for field definition |
| **Interactive Web Maps** | Leaflet/Folium-based interactive mapping interface |

---

## 💾 Technology Stack

### Frontend & Web Framework
- **Streamlit** — Interactive web UI framework
- **FastAPI + Uvicorn** — High-performance REST API
- **Folium** — Interactive mapping library

### Data Processing & Analysis
- **Google Earth Engine** — Large-scale satellite data processing
- **Rasterio & RioXarray** — Raster data I/O operations
- **GeoPandas & Shapely** — Vector geometry manipulation
- **NumPy & Pandas** — Numerical and tabular data analysis
- **Dask** — Distributed computing framework

### Visualization & Graphics
- **Cesium.js** — 3D geospatial visualization (WebGL)
- **Plotly** — Interactive statistical graphics
- **Matplotlib & Pillow** — Static images and image processing

### Data Sources & APIs
- **Sentinel-2 L2A** — Via Planetary Computer STAC
- **SRTM 30m DEM** — USGS/OpenTopography providers
- **Bing Aerial Imagery** — Cesium World Terrain base layer

### Additional Tools
- **Geemap** — Python API for Google Earth Engine
- **ImageIO & FFmpeg** — Video/animation codec
- **Celery + Redis** — Asynchronous task queue
- **PostgreSQL** — Metadata and cache storage
- **Python-dotenv** — Environment configuration

---

## 🚀 Quick Start

### Prerequisites
- Python 3.9 or higher
- Git
- Google Earth Engine account (free at [earthengine.google.com](https://earthengine.google.com))
- ~2GB disk space (for local cache)

### Step 1: Clone Repository
```bash
git clone https://github.com/yasinkaya701/geo-agri.git
cd geo-agri
```

### Step 2: Create Virtual Environment
```bash
# Linux/macOS
python -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

### Step 3: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Authenticate with Google Earth Engine
```bash
# For first-time setup
earthengine authenticate --project earth-500319

# Or from scratch
gcloud auth login
gcloud config set project earth-500319
```

### Step 5: Configure Environment Variables (Optional)
```bash
cp .env.example .env
# Add your API keys to .env file
```

### Step 6: Launch Application
```bash
streamlit run app.py
```

The application will automatically open in your browser at `http://localhost:8501`.

---

## 🏗️ Architecture

```
geo-agri/
├── app.py                              # Main Streamlit application
├── requirements.txt                    # Python package dependencies
├── Dockerfile                          # Container image definition
├── Procfile                            # Heroku deployment manifest
├── start_railway.sh                    # Railway.app deployment script
│
├── src/                                # Modular application code
│   ├── config.py                       # Configuration management
│   │
│   ├── ui/
│   │   ├── styles.py                   # Premium CSS design system
│   │   ├── cesium_flyover.py           # Cesium.js 3D drone component
│   │   ├── components.py               # TKGM parcel selector, Folium maps
│   │   └── plots.py                    # Plotly visualizations
│   │
│   ├── satellite/
│   │   ├── stac_client.py              # Planetary Computer STAC client
│   │   ├── bands_loader.py             # Sentinel-2 band loading & masking
│   │   ├── gee_timelapse.py            # GEE timelapse animation engine
│   │   ├── drone_simulator.py          # Synthetic UAV flight simulation
│   │   └── odm_client.py               # WebODM photogrammetry client
│   │
│   ├── geometry/
│   │   ├── projection.py               # CRS transformations & area calculations
│   │   └── operations.py               # Geometric operations
│   │
│   ├── dataset/
│   │   ├── ndvi.py                     # Spectral indices & phenology extraction
│   │   ├── filters.py                  # Image processing filters (Sobel, Gaussian, etc.)
│   │   ├── exporter.py                 # Data export utilities
│   │   ├── ml_generator.py             # ML dataset generation (CNN/ViT)
│   │   └── drone_analyzer.py           # Drone image analysis
│   │
│   └── tkgm/
│       └── megsis_client.py            # Turkish cadastral API client
│
├── google_earth_3d_timelapse/
│   ├── gee_3d_timelapse.py             # 3D perspective rendering engine
│   └── generate_3d_timelapse.py        # Offline timelapse generation
│
├── .streamlit/
│   └── config.toml                     # Streamlit configuration
│
└── .github/
    └── workflows/                      # CI/CD pipeline definitions
```

---

## 📖 Usage Guide

### 🎬 Core Workflow

#### 1️⃣ Field Selection
```python
# Select field interactively on map or provide WKT
field_coordinates = [
    (37.5, 29.5),
    (37.5, 29.6),
    (37.6, 29.6),
    (37.6, 29.5)
]
```

#### 2️⃣ Spectral Analysis
```python
from src.dataset.ndvi import calculate_ndvi

# Generate NDVI time series
ndvi_timeseries = calculate_ndvi(
    geometry=field_polygon,
    start_date="2023-01-01",
    end_date="2024-01-01",
    cloud_cover_tolerance=20
)
```

#### 3️⃣ Phenological Stage Detection
```python
from src.dataset.ndvi import extract_phenology

# Automatic growth stage identification
phenology = extract_phenology(ndvi_timeseries)
print(f"Planting: {phenology['sos_date']}")
print(f"Peak Growth: {phenology['peak_date']}")
print(f"Harvest: {phenology['eos_date']}")
```

#### 4️⃣ 3D Visualization
```python
from src.ui.cesium_flyover import render_drone_flyover_tab

render_drone_flyover_tab(
    geometry=field_polygon,
    altitude=500,        # meters
    camera_speed=50,     # m/s
    path_type="Orbital Scan"
)
```

#### 5️⃣ ML Dataset Generation
```python
from src.dataset.ml_generator import MLDatasetGenerator, DatasetConfig

config = DatasetConfig(
    patch_size=256,
    stride=128,
    normalization="minmax",
    aug_flip=True,
    aug_rotate=True
)
generator = MLDatasetGenerator(config)
dataset = generator.generate_from_processed(satellite_data)
dataset.to_coco_format("output_dataset.json")
```

### 🔧 Programmatic API Usage

Start the FastAPI backend:

```bash
uvicorn src.api.main:app --reload
```

Python client example:

```python
import requests

# Calculate vegetation index
response = requests.post("http://localhost:8000/api/ndvi", json={
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[29.5, 37.5], [29.6, 37.5], ...]]
    },
    "start_date": "2023-01-01",
    "end_date": "2024-01-01",
    "index_type": "NDVI"
})

result = response.json()
print(result['ndvi_timeseries'])
```

---

## 📡 Data Sources

| Data Type | Source | Resolution | Update Frequency |
|-----------|--------|-----------|------------------|
| **Multispectral Imagery** | Sentinel-2 L2A | 10-60m | 5-10 days |
| **Digital Elevation Model** | SRTM 30m | 30m | Static (2000) |
| **High-Res Aerial** | Bing Maps | 0.5-1m | Variable |
| **Field Boundaries** | TKGM MEGSIS | Vector | Annual |
| **Weather Data** | OpenWeather | Point/Grid | Hourly |

### Data Access Examples

```python
import ee
from src.satellite.stac_client import StacClient

# Query Sentinel-2 via STAC
stac = StacClient()
items = stac.search_sentinel_data(
    geometry_wgs84=field_polygon,
    start_date="2024-01-01",
    end_date="2024-06-30",
    max_cloud_cover=20
)

# Access SRTM via Google Earth Engine
dem = ee.Image("USGS/SRTMGL1_Ellip/SRTMGL1_Ellip_srtm")
elevation = dem.sample(ee.Geometry.Point([29.55, 37.55])).getInfo()
print(f"Elevation: {elevation['properties']['elevation']} m")
```

---

## 🚀 Deployment

### Option 1: Streamlit Community Cloud (Easiest)

```bash
# 1. Push to GitHub
git add .
git commit -m "Deploy to Streamlit Cloud"
git push origin main

# 2. Visit https://share.streamlit.io
# 3. Click "New app" → select repo → Deploy
```

**Required Secrets** (in `Settings → Secrets`):
```toml
[gee]
project = "earth-500319"

[api]
stac_endpoint = "https://planetarycomputer.microsoft.com/api/stac/v1"
```

### Option 2: Docker Container

```bash
# Build image
docker build -t geo-agri:latest .

# Run container
docker run -p 8501:8501 \
  -e GEE_PROJECT=earth-500319 \
  -v ~/.config/earthengine:/root/.config/earthengine \
  geo-agri:latest
```

### Option 3: Railway.app (Recommended)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and link project
railway link

# Deploy
railway up
```

Railway will automatically use the `start_railway.sh` script.

### Option 4: Heroku

```bash
# Login and create app
heroku login
heroku create geo-agri-app

# Set environment variables
heroku config:set GEE_PROJECT=earth-500319
heroku config:set PYTHONUNBUFFERED=1

# Deploy
git push heroku main
```

Heroku will automatically use the `Procfile` configuration.

---

## 📚 API Documentation

### REST Endpoints

#### `POST /api/ndvi`
Calculate NDVI time series for a specific geometry.

**Request:**
```json
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[29.5, 37.5], [29.6, 37.5], [29.6, 37.6], [29.5, 37.6], [29.5, 37.5]]]
  },
  "start_date": "2023-01-01",
  "end_date": "2024-01-01",
  "cloud_cover": 20,
  "reducer": "mean"
}
```

**Response:**
```json
{
  "dates": ["2023-01-05", "2023-01-15", "2023-01-25", ...],
  "ndvi_values": [0.35, 0.38, 0.45, ...],
  "std_dev": [0.08, 0.07, 0.06, ...],
  "cloud_coverage": [5, 3, 2, ...]
}
```

#### `POST /api/phenology`
Extract phenological stages from NDVI time series.

**Request:**
```json
{
  "ndvi_timeseries": [0.35, 0.38, 0.45, 0.62, 0.71, 0.68, 0.55, 0.32],
  "dates": ["2023-05-01", "2023-05-11", ...],
  "smoothing_window": 11
}
```

**Response:**
```json
{
  "planting_date": "2023-05-15",
  "flowering_date": "2023-07-10",
  "peak_ndvi": 0.71,
  "peak_date": "2023-08-01",
  "maturity_date": "2023-08-20",
  "harvest_date": "2023-09-10",
  "growing_season_length": 118,
  "confidence_score": 0.92
}
```

#### `POST /api/dataset/generate`
Generate production-ready ML dataset.

**Request:**
```json
{
  "geometry": {...},
  "model_type": "cnn",
  "patch_size": 256,
  "patch_overlap": 0.25,
  "augmentation": true,
  "train_split": 0.7,
  "val_split": 0.15,
  "test_split": 0.15
}
```

**Response:**
```json
{
  "dataset_id": "ds_20240624_abc123",
  "num_samples": 450,
  "num_channels": 9,
  "classes": {
    "bare_soil": 45,
    "sparse_vegetation": 135,
    "dense_vegetation": 270
  },
  "splits": {"train": 315, "val": 68, "test": 67},
  "format": "coco",
  "download_url": "https://api.geo-agri.app/datasets/ds_20240624_abc123/download"
}
```

#### `GET /api/health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "gee_connected": true,
  "stac_connected": true,
  "cache_hit_rate": 0.78
}
```

---

## 🛠️ Troubleshooting

### Common Issues & Solutions

**Issue: "ModuleNotFoundError: No module named 'ee'"**
```bash
# Solution: Reinstall Earth Engine API
pip install earthengine-api --upgrade
earthengine authenticate
```

**Issue: "Sentinel-2 data not found"**
- **Cause**: High cloud coverage or incorrect date range
- **Solution**: Extend date range or increase cloud_cover parameter
```python
items = stac.search_sentinel_data(
    geometry_wgs84=field,
    start_date="2024-01-01",
    end_date="2024-06-30",  # Wider range
    max_cloud_cover=30      # More tolerant
)
```

**Issue: "Streamlit connection timeout"**
```bash
# Clear cache and restart
streamlit cache clear
streamlit run app.py --client.maxMessageSize=200
```

**Issue: "3D Cesium map not loading"**
- Check WebGL support in browser (F12 → Console)
- Verify coordinates are in valid range [-180, 180] for longitude, [-90, 90] for latitude
- Try different browser (Chrome/Firefox recommended)

### Debug Mode

```python
# Enable debug logging in app.py
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Run with verbose output
streamlit run app.py --logger.level=debug
```

---

## 📊 Performance Specifications

| Metric | Limit | Notes |
|--------|-------|-------|
| **Maximum field size** | 100 km² | GEE memory constraints |
| **Maximum time range** | 20 years | SRTM availability |
| **Minimum resolution** | 10m | Sentinel-2 blue band |
| **API Rate Limit** | 100 requests/min | Per IP address |
| **Cache TTL** | 7 days | Redis expiration |
| **Typical analysis time** | 30-60 seconds | For 1 year, 1 field |

---

## 🤝 Contributing

We welcome contributions! Here's how to get started:

### Contribution Workflow

1. **Fork the Repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/geo-agri.git
   cd geo-agri
   ```

2. **Create Feature Branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```

3. **Make Your Changes**
   - Follow [PEP 8](https://pep8.org/) style guide
   - Add docstrings to functions
   - Update relevant tests

4. **Commit Changes**
   ```bash
   git commit -m "Add amazing-feature: description"
   ```

5. **Push to Branch**
   ```bash
   git push origin feature/amazing-feature
   ```

6. **Open Pull Request**
   - Describe changes clearly
   - Link relevant issues
   - Include before/after screenshots if applicable

### Code Quality Standards

```bash
# Code formatting
pip install black flake8 isort
black src/
isort src/
flake8 src/

# Type checking (optional)
pip install mypy
mypy src/

# Run tests
pytest tests/ -v --cov=src
```

### Reporting Issues

Please use the [GitHub Issues](https://github.com/yasinkaya701/geo-agri/issues) tracker with:
- Clear, descriptive title
- Steps to reproduce
- Expected vs actual behavior
- System information (OS, Python version, etc.)
- Relevant logs or screenshots

---

## 📄 License & Attribution

- **License**: [MIT License](LICENSE)
- **Author**: Yasin Kaya ([@yasinkaya701](https://github.com/yasinkaya701))
- **Maintained**: Active development as of 2024

### Acknowledgments

- 🙏 **ESA/Copernicus** — Sentinel-2 mission and data
- 🙏 **Google** — Earth Engine platform and API
- 🙏 **Microsoft** — Planetary Computer STAC catalog
- 🙏 **Cesium** — WebGL geospatial visualization
- 🙏 **Python Community** — NumPy, Pandas, GeoPandas, and ecosystem

---

## 📞 Contact & Support

- **Issues & Bug Reports**: [GitHub Issues](https://github.com/yasinkaya701/geo-agri/issues)
- **Feature Requests**: [GitHub Discussions](https://github.com/yasinkaya701/geo-agri/discussions)
- **Email Support**: [yasinkaya701@gmail.com](mailto:yasinkaya701@gmail.com)
- **Follow Updates**: ⭐ Star the repository

---

## 🗺️ Project Roadmap

- [ ] **v2.1**: Multi-field batch processing
- [ ] **v2.2**: React-based web frontend
- [ ] **v2.3**: Mobile application (React Native)
- [ ] **v2.4**: Real-time alert system (WebSockets)
- [ ] **v2.5**: AI-powered crop disease detection (ResNet/EfficientNet)
- [ ] **v3.0**: Blockchain-based data provenance
- [ ] **v3.1**: Integration with drone fleets (MQTT)
- [ ] **v3.2**: Prescriptive agronomy recommendations

---

<div align="center">

**Made with 🌱 and ❤️ by [yasinkaya701](https://github.com/yasinkaya701)**

If you find this project useful, please give it a ⭐ on GitHub!

![GitHub Stars](https://img.shields.io/github/stars/yasinkaya701/geo-agri)
![GitHub Forks](https://img.shields.io/github/forks/yasinkaya701/geo-agri)
![GitHub Issues](https://img.shields.io/github/issues/yasinkaya701/geo-agri)

</div>
