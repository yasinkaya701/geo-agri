"""
Cesium.js Drone Flyover Bileşeni
=================================
Parsel koordinatları alır → tarayıcıda gerçekçi 3D drone uçuşu üretir.
Cesium Ion ücretsiz token kullanır (Bing uydu + SRTM arazi = Google Earth kalitesi).
"""
import streamlit.components.v1 as components
import json
import math


# Ücretsiz Cesium Ion demo token — production için kullanıcı kendi token'ını alır
# https://cesium.com/ion/signup (ücretsiz)
CESIUM_ION_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJlYWE1OWUxNy1mMWZiLTQzYjYtYTQ0OS1kMWFjYmFiZThhNDgiLCJpZCI6Mjc2Mzc4LCJpYXQiOjE3MTk5OTU1MDJ9.PBtlEt_h3rJ78_PnXXO4a-IZC8sQPIPnQ9_fh1tnLsE"


FLIGHT_MODES = {
    "orbit":    "🌀 360° Orbit",
    "approach": "🚁 Yaklaşma",
    "grid":     "📐 Grid Tarama",
    "panorama": "🏔️ Panorama",
}


def render_cesium_flyover(
    lat: float,
    lon: float,
    polygon_coords: list,          # [[lon,lat], ...] WGS84
    flight_mode: str = "orbit",    # orbit | approach | grid | panorama
    altitude_m: float = 300.0,     # Drone irtifası (metre)
    speed: float = 1.0,            # Animasyon hızı çarpanı
    show_controls: bool = True,
    height_px: int = 550,
    cesium_token: str = CESIUM_ION_TOKEN,
) -> None:
    """
    Streamlit içine gömülü Cesium.js 3D drone flyover bileşeni.
    Gerçek Bing uydu görüntüsü + SRTM arazi = Google Earth kalitesi.
    """
    # Polygon merkez ve boyut hesaplama
    lons = [c[0] for c in polygon_coords]
    lats = [c[1] for c in polygon_coords]
    cx   = (min(lons) + max(lons)) / 2
    cy   = (min(lats) + max(lats)) / 2
    
    lat_m  = 111132.0
    lon_m  = 111412.0 * math.cos(math.radians(lat))
    width  = (max(lons) - min(lons)) * lon_m
    height_geo = (max(lats) - min(lats)) * lat_m
    radius = max(max(width, height_geo) * 0.7, 200)

    # Uçuş yolu JavaScript'e gönder
    flight_params = json.dumps({
        "mode": flight_mode,
        "lat": cy, "lon": cx,
        "radius": radius,
        "altitude": altitude_m,
        "speed": speed,
        "polygon": [[c[0], c[1]] for c in polygon_coords],
    })

    html = f"""
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Drone Flyover</title>
<script src="https://cesium.com/downloads/cesiumjs/releases/1.118/Build/Cesium/Cesium.js"></script>
<link href="https://cesium.com/downloads/cesiumjs/releases/1.118/Build/Cesium/Widgets/widgets.css" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:100%; height:{height_px}px; overflow:hidden; background:#080C14; font-family:'Inter',sans-serif; }}
  #cesiumContainer {{ width:100%; height:100%; }}

  /* Control panel */
  #controls {{
    position:absolute; top:12px; left:12px; z-index:100;
    background:rgba(8,12,20,0.88); backdrop-filter:blur(12px);
    border:1px solid rgba(255,255,255,0.1); border-radius:12px;
    padding:12px 16px; min-width:210px;
    box-shadow:0 4px 24px rgba(0,0,0,0.6);
  }}
  #controls h3 {{
    font-size:11px; font-weight:700; text-transform:uppercase;
    letter-spacing:0.1em; color:#94A3B8; margin-bottom:10px;
  }}
  .btn-mode {{
    display:block; width:100%; text-align:left;
    background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08);
    border-radius:8px; color:#CBD5E1; font-size:12px; font-weight:500;
    padding:7px 12px; margin:4px 0; cursor:pointer;
    transition:all 0.18s ease;
  }}
  .btn-mode:hover {{ background:rgba(16,185,129,0.12); border-color:rgba(16,185,129,0.4); color:#fff; }}
  .btn-mode.active {{ background:rgba(16,185,129,0.18); border-color:rgba(16,185,129,0.6); color:#10B981; }}

  /* HUD */
  #hud {{
    position:absolute; bottom:12px; left:12px; z-index:100;
    background:rgba(8,12,20,0.82); backdrop-filter:blur(10px);
    border:1px solid rgba(255,255,255,0.08); border-radius:10px;
    padding:10px 14px; font-size:11px; color:#64748B;
    font-family:'JetBrains Mono','Courier New',monospace;
    line-height:1.6;
  }}
  #hud span {{ color:#94A3B8; }}
  #hud .val {{ color:#F0F6FF; }}
  #hud .green {{ color:#10B981; }}

  /* Status badge */
  #status {{
    position:absolute; top:12px; right:12px; z-index:100;
    background:rgba(8,12,20,0.82); backdrop-filter:blur(10px);
    border:1px solid rgba(16,185,129,0.3); border-radius:99px;
    padding:5px 14px; font-size:11px; font-weight:600;
    color:#10B981; font-family:'JetBrains Mono',monospace;
    display:flex; align-items:center; gap:6px;
  }}
  .dot {{
    width:6px;height:6px;border-radius:50%;background:#10B981;
    animation:pulse 1.5s infinite;
  }}
  @keyframes pulse {{ 0%,100%{{opacity:1;box-shadow:0 0 4px #10B981;}} 50%{{opacity:0.4;box-shadow:none;}} }}

  /* Loading overlay */
  #loader {{
    position:absolute;inset:0;background:#080C14;
    display:flex;flex-direction:column;align-items:center;justify-content:center;
    z-index:200; gap:12px;
  }}
  #loader-text {{ color:#94A3B8; font-size:13px; font-family:'Inter',sans-serif; }}
  .spinner {{
    width:36px;height:36px;border:3px solid rgba(16,185,129,0.2);
    border-top-color:#10B981;border-radius:50%;animation:spin 0.8s linear infinite;
  }}
  @keyframes spin {{ to{{ transform:rotate(360deg); }} }}
</style>
</head>
<body>

<div id="loader">
  <div class="spinner"></div>
  <div id="loader-text">🌍 3D arazi yükleniyor...</div>
</div>

<div id="cesiumContainer"></div>

<div id="controls" {'style="display:none"' if not show_controls else ''}>
  <h3>🚁 Uçuş Modu</h3>
  <button class="btn-mode {'active' if flight_mode=='orbit' else ''}"    onclick="setMode('orbit')"    id="btn-orbit">🌀 360° Orbit</button>
  <button class="btn-mode {'active' if flight_mode=='approach' else ''}" onclick="setMode('approach')" id="btn-approach">🚁 Yaklaşma</button>
  <button class="btn-mode {'active' if flight_mode=='grid' else ''}"     onclick="setMode('grid')"     id="btn-grid">📐 Grid Tarama</button>
  <button class="btn-mode {'active' if flight_mode=='panorama' else ''}" onclick="setMode('panorama')" id="btn-panorama">🏔️ Panorama</button>
  <hr style="border-color:rgba(255,255,255,0.07);margin:10px 0;">
  <button class="btn-mode" onclick="togglePlay()" id="btn-play">⏸ Durdur</button>
  <button class="btn-mode" onclick="resetView()" style="margin-top:2px">🎯 Merkeze Dön</button>
</div>

<div id="hud">
  <span>İRT</span> <span class="val" id="h-alt">---</span>m &nbsp;
  <span>BAŞ</span> <span class="val" id="h-head">---</span>° &nbsp;
  <span>EĞ</span>  <span class="val" id="h-pitch">---</span>°<br>
  <span>LAT</span> <span class="val" id="h-lat">---</span> &nbsp;
  <span>LON</span> <span class="val" id="h-lon">---</span><br>
  <span class="green">● GEE · Sentinel-2 · SRTM</span>
</div>

<div id="status"><div class="dot"></div>LIVE 3D</div>

<script>
Cesium.Ion.defaultAccessToken = '{cesium_token}';

const PARAMS = {flight_params};
let viewer, animTimer, animRunning = true, currentMode = PARAMS.mode;
let animProgress = 0;

async function init() {{
  try {{
    viewer = new Cesium.Viewer('cesiumContainer', {{
      terrainProvider: await Cesium.createWorldTerrainAsync({{
        requestWaterMask: false, requestVertexNormals: true
      }}),
      imageryProvider: new Cesium.IonImageryProvider({{ assetId: 2 }}),
      animation: false, baseLayerPicker: false, fullscreenButton: false,
      geocoder: false, homeButton: false, infoBox: false,
      navigationHelpButton: false, sceneModePicker: false,
      selectionIndicator: false, timeline: false,
      creditContainer: document.createElement('div'),
    }});

    // Dark atmosphere
    viewer.scene.skyAtmosphere.show = true;
    viewer.scene.fog.enabled = true;
    viewer.scene.fog.density = 0.0002;
    viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#080C14');
    viewer.scene.skyBox.show = true;

    // Draw parcel polygon
    drawParcel();
    
    // Start flyover
    document.getElementById('loader').style.display = 'none';
    startFlight(currentMode);

    // HUD updater
    setInterval(updateHUD, 100);

  }} catch(e) {{
    document.getElementById('loader-text').textContent = '⚠ Yükleme hatası: ' + e.message;
    console.error(e);
  }}
}}

function drawParcel() {{
  const coords = PARAMS.polygon.map(p => Cesium.Cartesian3.fromDegrees(p[0], p[1]));
  coords.push(coords[0]); // close
  viewer.entities.add({{
    polyline: {{
      positions: coords,
      width: 3,
      material: new Cesium.PolylineGlowMaterialProperty({{
        glowPower: 0.2, color: Cesium.Color.fromCssColorString('#10B981')
      }})
    }}
  }});
  // Fill polygon
  viewer.entities.add({{
    polygon: {{
      hierarchy: new Cesium.PolygonHierarchy(
        PARAMS.polygon.map(p => Cesium.Cartesian3.fromDegrees(p[0], p[1]))
      ),
      material: Cesium.Color.fromCssColorString('#10B981').withAlpha(0.12),
      outline: false,
      height: 0,
      perPositionHeight: false,
    }}
  }});
}}

function startFlight(mode) {{
  if (animTimer) clearInterval(animTimer);
  animProgress = 0;
  
  const baseDuration = 600 / PARAMS.speed; // frames at 60fps
  const lat = PARAMS.lat, lon = PARAMS.lon;
  const R = PARAMS.radius, alt = PARAMS.altitude;

  if (mode === 'orbit') {{
    animTimer = setInterval(() => {{
      if (!animRunning) return;
      animProgress += 1 / baseDuration;
      if (animProgress >= 1) animProgress = 0;
      
      const angle = animProgress * 2 * Math.PI;
      const camLon = lon + (R / (111412 * Math.cos(lat * Math.PI/180))) * Math.cos(angle);
      const camLat = lat + (R / 111132) * Math.sin(angle);
      
      viewer.camera.lookAt(
        Cesium.Cartesian3.fromDegrees(lon, lat, 0),
        new Cesium.HeadingPitchRange(
          -angle - Math.PI/2,
          Cesium.Math.toRadians(-32 - 10 * Math.sin(animProgress * 4 * Math.PI)),
          R * 1.8
        )
      );
    }}, 16);
    
  }} else if (mode === 'approach') {{
    animTimer = setInterval(() => {{
      if (!animRunning) return;
      animProgress += 1 / baseDuration;
      if (animProgress >= 1) {{ animProgress = 0; }}
      
      const t = animProgress;
      const ease = t < 0.5 ? 2*t*t : -1+(4-2*t)*t;
      
      // Start far, zoom into parcel
      const startDist = R * 8, endDist = R * 1.2;
      const dist = startDist + (endDist - startDist) * ease;
      const startAlt = alt * 4, endAlt = alt * 0.6;
      const camAlt = startAlt + (endAlt - startAlt) * ease;
      
      const angle = t * Math.PI; // 180 degree sweep during approach
      viewer.camera.lookAt(
        Cesium.Cartesian3.fromDegrees(lon, lat, 0),
        new Cesium.HeadingPitchRange(
          angle, Cesium.Math.toRadians(-20 - 30 * ease), dist
        )
      );
    }}, 16);
    
  }} else if (mode === 'grid') {{
    // Boustrophedon (snake) scan over parcel
    const rows = 5;
    animTimer = setInterval(() => {{
      if (!animRunning) return;
      animProgress += 1 / baseDuration;
      if (animProgress >= 1) animProgress = 0;
      
      const t = animProgress;
      const row = Math.floor(t * rows);
      const rowT = (t * rows) - row;
      const rowDir = row % 2 === 0 ? rowT : 1 - rowT;
      
      const latFrac = (row / rows) * 2 - 1; // -1 to 1
      const camLat = lat + latFrac * (R / 111132) * 0.8;
      const camLon = lon + (rowDir * 2 - 1) * (R / (111412 * Math.cos(lat * Math.PI/180))) * 0.8;
      
      viewer.camera.setView({{
        destination: Cesium.Cartesian3.fromDegrees(camLon, camLat, alt * 1.5),
        orientation: {{ heading:0, pitch: Cesium.Math.toRadians(-80), roll:0 }}
      }});
    }}, 16);
    
  }} else if (mode === 'panorama') {{
    // High altitude 360 pan
    animTimer = setInterval(() => {{
      if (!animRunning) return;
      animProgress += 0.7 / baseDuration;
      if (animProgress >= 1) animProgress = 0;
      
      const angle = animProgress * 2 * Math.PI;
      viewer.camera.lookAt(
        Cesium.Cartesian3.fromDegrees(lon, lat, 0),
        new Cesium.HeadingPitchRange(angle, Cesium.Math.toRadians(-20), R * 4)
      );
    }}, 16);
  }}
}}

function setMode(mode) {{
  currentMode = mode;
  document.querySelectorAll('.btn-mode').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-' + mode)?.classList.add('active');
  startFlight(mode);
}}

function togglePlay() {{
  animRunning = !animRunning;
  document.getElementById('btn-play').textContent = animRunning ? '⏸ Durdur' : '▶ Başlat';
}}

function resetView() {{
  viewer.camera.lookAt(
    Cesium.Cartesian3.fromDegrees(PARAMS.lon, PARAMS.lat, 0),
    new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-45), PARAMS.radius * 3)
  );
}}

function updateHUD() {{
  if (!viewer) return;
  const pos = viewer.camera.positionCartographic;
  if (!pos) return;
  document.getElementById('h-alt').textContent   = Math.round(pos.height);
  document.getElementById('h-head').textContent  = Math.round(Cesium.Math.toDegrees(viewer.camera.heading));
  document.getElementById('h-pitch').textContent = Math.round(Cesium.Math.toDegrees(viewer.camera.pitch));
  document.getElementById('h-lat').textContent   = Cesium.Math.toDegrees(pos.latitude).toFixed(5);
  document.getElementById('h-lon').textContent   = Cesium.Math.toDegrees(pos.longitude).toFixed(5);
}}

init();
</script>
</body>
</html>
"""
    components.html(html, height=height_px, scrolling=False)


def render_drone_flyover_tab(geometry_geojson: dict, key_suffix: str = "") -> None:
    """Streamlit tab içinde Cesium.js drone flyover bileşeni."""
    import streamlit as st
    from shapely.geometry import shape as shp_shape

    st.markdown("""
    <div class="card card-accent">
        <div class="card-title">🚁 Gerçekçi Drone Flyover — Cesium.js 3D</div>
        <div class="card-subtitle">
            Seçili tarla üzerinde gerçek Google Earth kalitesinde 3D drone uçuşu.
            Bing uydu görüntüsü + SRTM arazi modeli · Tarayıcıda canlı render.
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("**Uçuş Parametreleri**")
        flight_mode = st.selectbox(
            "Uçuş Modu",
            options=list(FLIGHT_MODES.keys()),
            format_func=lambda x: FLIGHT_MODES[x],
            key=f"fly_mode_{key_suffix}"
        )
        altitude = st.slider("İrtifa (m)", 50, 1000, 300, 25, key=f"fly_alt_{key_suffix}")
        speed    = st.slider("Hız", 0.3, 3.0, 1.0, 0.1, key=f"fly_speed_{key_suffix}")

        st.markdown("""
        **Veri Kaynakları:**
        - 🌍 Bing Aerial (Cesium Ion)
        - 🏔️ Cesium World Terrain (SRTM)
        - 🟢 Parsel sınırı: TKGM

        **Modu Değiştir:** Sol panelden tıkla  
        **Durdur/Başlat:** Kontrol panelinden
        """)

    with col2:
        try:
            geom    = shp_shape(geometry_geojson.get("geometry", geometry_geojson))
            lat     = geom.centroid.y
            lon     = geom.centroid.x
            coords  = list(geom.exterior.coords) if hasattr(geom, 'exterior') else [(lon, lat)]

            render_cesium_flyover(
                lat=lat, lon=lon,
                polygon_coords=coords,
                flight_mode=flight_mode,
                altitude_m=altitude,
                speed=speed,
                show_controls=True,
                height_px=540,
            )
        except Exception as e:
            st.error(f"Cesium yükleme hatası: {e}")
            st.info("Parsel seçili olmalı ve tarayıcınız WebGL desteklemeli.")
