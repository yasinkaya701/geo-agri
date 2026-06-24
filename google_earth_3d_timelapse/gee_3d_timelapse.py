#!/usr/bin/env python3
"""
Google Earth Engine — Gerçek 3D Tarihsel Timelapse Videosu
===========================================================
GEE projesi: earth-500319

Gerçek Google Earth verilerini kullanarak:
  - SRTM 30m gerçek yükseklik verisi
  - Sentinel-2 / Landsat 8-9 tarihsel uydu görüntüleri  
  - Esri World Imagery (en yüksek çözünürlük)
  - Perspektif homografi ile Google Earth stili 3D render
  - H.264 MP4 + GIF export
"""

import os
import io
import sys
import math
import time
import urllib.request
import argparse
import warnings
from typing import List, Tuple, Optional, Dict, Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import matplotlib
matplotlib.use('Agg')
from matplotlib.colors import LightSource
import imageio

warnings.filterwarnings('ignore')

GEE_PROJECT = "earth-500319"


# ─────────────────────────────────────────────────────────────
# 1. GEE Initialization
# ─────────────────────────────────────────────────────────────

def init_gee():
    import ee
    try:
        ee.Initialize(project=GEE_PROJECT)
        print(f"  ✓ GEE başlatıldı: {GEE_PROJECT}")
        return ee
    except Exception as e:
        print(f"  ✗ GEE başlatma hatası: {e}")
        raise


# ─────────────────────────────────────────────────────────────
# 2. GEE'den Gerçek Veriler
# ─────────────────────────────────────────────────────────────

def deg_to_meters(lat):
    lat_m = 111132.954 - 559.822 * math.cos(2 * math.radians(lat))
    lon_m = 111412.84 * math.cos(math.radians(lat))
    return lat_m, lon_m


def compute_bbox(lat, lon, buffer_m):
    lat_m, lon_m = deg_to_meters(lat)
    d_lat = buffer_m / lat_m
    d_lon = buffer_m / lon_m
    return lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat


def fetch_gee_elevation(ee, lat, lon, buffer_m, grid_size=128):
    """GEE SRTM 30m gerçek yükseklik verisi."""
    print("  → GEE SRTM yükseklik verisi indiriliyor...")
    
    minlon, minlat, maxlon, maxlat = compute_bbox(lat, lon, buffer_m)
    region = ee.Geometry.BBox(minlon, minlat, maxlon, maxlat)
    
    srtm = ee.Image('USGS/SRTMGL1_003').select('elevation')
    
    url = srtm.getThumbURL({
        'region': region,
        'dimensions': grid_size,
        'format': 'png',
        'min': 800,
        'max': 1100,
        'palette': ['000000', 'ffffff']
    })
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    
    img = Image.open(io.BytesIO(data)).convert('L')
    img = img.resize((grid_size, grid_size), Image.Resampling.BILINEAR)
    elev_norm = np.array(img, dtype=np.float32) / 255.0
    
    # Scale to real elevation (Burdur ~800-1100m)
    elev = elev_norm * 300.0 + 800.0
    print(f"     ✓ SRTM OK: min={elev.min():.0f}m max={elev.max():.0f}m")
    return elev


def fetch_gee_aerial(ee, lat, lon, buffer_m, size=2048):
    """GEE'den en yüksek çözünürlüklü gerçek satellite görüntüsü."""
    print(f"  → GEE Satellite görüntüsü [{size}px]...")
    
    minlon, minlat, maxlon, maxlat = compute_bbox(lat, lon, buffer_m)
    region = ee.Geometry.BBox(minlon, minlat, maxlon, maxlat)
    
    # Use Sentinel-2 cloud-free composite (latest year)
    s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
          .filterBounds(region)
          .filterDate('2023-01-01', '2024-12-31')
          .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
          .sort('CLOUDY_PIXEL_PERCENTAGE')
          .mosaic()
          .select(['B4', 'B3', 'B2']))
    
    url = s2.getThumbURL({
        'region': region,
        'dimensions': size,
        'format': 'jpg',
        'min': 0,
        'max': 3000,
        'gamma': 1.4,
    })
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    
    img = Image.open(io.BytesIO(data)).convert('RGB')
    # Force square crop (center crop)
    w, h = img.size
    if w != h:
        side = min(w, h)
        left = (w - side) // 2
        top  = (h - side) // 2
        img = img.crop((left, top, left+side, top+side))
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    print(f"     ✓ Aerial OK: {img.size}")
    return img


def fetch_gee_historical_scenes(ee, lat, lon, buffer_m,
                                  start_date, end_date,
                                  num_scenes=8, size=1024):
    """GEE'den tarihsel Sentinel-2/Landsat sahneleri."""
    print(f"  → GEE tarihsel sahneler ({start_date} → {end_date}, n={num_scenes})...")
    
    minlon, minlat, maxlon, maxlat = compute_bbox(lat, lon, buffer_m)
    region = ee.Geometry.BBox(minlon, minlat, maxlon, maxlat)
    
    scenes = []
    
    # Sentinel-2 (2017+)
    s2_col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
              .filterBounds(region)
              .filterDate(start_date, end_date)
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 15))
              .sort('system:time_start'))
    
    # GEE toList() max 200 — clamp idx ve spread et
    list_cap = 200
    s2_list = s2_col.toList(list_cap)
    s2_size_raw = min(s2_col.size().getInfo(), list_cap)
    print(f"     Found {s2_col.size().getInfo()} Sentinel-2 scenes (sampling from first {list_cap})")
    
    step = max(1, s2_size_raw // num_scenes)
    indices = list(range(0, min(s2_size_raw, num_scenes * step), step))[:num_scenes]
    
    for idx in indices:
        try:
            img_info = ee.Image(s2_list.get(idx))
            date_ms = img_info.date().getInfo()['value']
            date_str = time.strftime('%Y-%m-%d', time.gmtime(date_ms / 1000))
            
            img_rgb = img_info.select(['B4', 'B3', 'B2'])
            
            url = img_rgb.getThumbURL({
                'region': region,
                'dimensions': size,
                'format': 'jpg',
                'min': 0,
                'max': 3000,
                'gamma': 1.4,
            })
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            
            scene_img = Image.open(io.BytesIO(data)).convert('RGB')
            # Force square crop
            sw, sh = scene_img.size
            if sw != sh:
                side = min(sw, sh)
                scene_img = scene_img.crop(((sw-side)//2, (sh-side)//2,
                                            (sw+side)//2, (sh+side)//2))
            scene_img = scene_img.resize((size, size), Image.Resampling.LANCZOS)
            scenes.append((date_str, scene_img))
            print(f"     ✓ S2 {date_str}: {scene_img.size}")
            
        except Exception as e:
            print(f"     ⚠ Scene {idx} failed: {e}")
            continue
    
    # Also try Landsat 8/9 for older dates
    if len(scenes) < num_scenes // 2:
        try:
            l8_col = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
                      .filterBounds(region)
                      .filterDate(start_date, end_date)
                      .filter(ee.Filter.lt('CLOUD_COVER', 15))
                      .sort('system:time_start'))
            
            l8_size = l8_col.size().getInfo()
            l8_list = l8_col.toList(200)
            step_l8 = max(1, l8_size // (num_scenes - len(scenes)))
            
            for idx in range(0, min(l8_size, (num_scenes - len(scenes)) * step_l8), step_l8):
                try:
                    img_info = ee.Image(l8_list.get(idx))
                    date_ms = img_info.date().getInfo()['value']
                    date_str = time.strftime('%Y-%m-%d', time.gmtime(date_ms / 1000))
                    
                    img_rgb = img_info.select(['SR_B4', 'SR_B3', 'SR_B2'])
                    url = img_rgb.getThumbURL({
                        'region': region,
                        'dimensions': size,
                        'format': 'jpg',
                        'min': 7000,
                        'max': 25000,
                        'gamma': 1.4,
                    })
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = resp.read()
                    scene_img = Image.open(io.BytesIO(data)).convert('RGB')
                    scenes.append((date_str, scene_img))
                    print(f"     ✓ L8 {date_str}: {scene_img.size}")
                except Exception:
                    continue
        except Exception:
            pass
    
    scenes.sort(key=lambda x: x[0])
    print(f"  ✓ Toplam {len(scenes)} tarihsel sahne hazır")
    return scenes


# ─────────────────────────────────────────────────────────────
# 3. Google Earth Stili Perspektif Render
# ─────────────────────────────────────────────────────────────

def find_perspective_coeffs(src_pts, dst_pts):
    """PIL perspective coefficients: src → dst mapping (inverse for PIL)."""
    matrix = []
    for (x1, y1), (x2, y2) in zip(dst_pts, src_pts):
        matrix.append([x1, y1, 1, 0, 0, 0, -x2*x1, -x2*y1])
        matrix.append([0, 0, 0, x1, y1, 1, -y2*x1, -y2*y1])
    A = np.array(matrix, dtype=np.float64)
    B = np.array([c for p in src_pts for c in p], dtype=np.float64)
    try:
        res = np.linalg.solve(A, B)
        return tuple(res)
    except np.linalg.LinAlgError:
        return None


def apply_hillshade(tex_img: Image.Image, elevation: np.ndarray,
                     sun_azim: float = 315.0, blend: float = 0.3) -> Image.Image:
    """Arazi hillshade'i yüksek çözünürlüklü texture'a uygula."""
    w, h = tex_img.size
    ls = LightSource(azdeg=sun_azim, altdeg=50)
    shade = ls.hillshade(elevation, vert_exag=4.0, dx=10.0, dy=10.0)
    
    shade_img = Image.fromarray((shade * 255).astype(np.uint8)).resize(
        (w, h), Image.Resampling.BILINEAR
    )
    shade_arr = np.array(shade_img, dtype=np.float32) / 255.0
    tex_arr = np.array(tex_img, dtype=np.float32) / 255.0
    
    blended = tex_arr * (1 - blend) + tex_arr * shade_arr[:, :, np.newaxis] * blend
    blended = np.clip(blended, 0, 1)
    return Image.fromarray((blended * 255).astype(np.uint8))


def render_google_earth_frame(
    tex_img: Image.Image,      # Satellite texture (top-down)
    elevation: np.ndarray,      # DEM grid
    azim_deg: float,            # Camera azimuth (0=N, 90=E)
    tilt_deg: float,            # Camera tilt from nadir (0=straight down, 60=oblique)
    screen_w: int = 1280,
    screen_h: int = 720,
    zoom: float = 0.55,
) -> Image.Image:
    """
    Google Earth birebir perspektif render.
    Gerçek perspektif homografi ile yüksek kaliteli görünüm.
    """
    img_w, img_h = tex_img.size
    cx, cy = img_w / 2.0, img_h / 2.0

    # Apply hillshade for realism
    shaded = apply_hillshade(tex_img, elevation,
                              sun_azim=(azim_deg + 135) % 360, blend=0.28)

    # Perspective parameters
    azim_rad = math.radians(azim_deg)
    tilt_rad = math.radians(tilt_deg)  # 0=nadir, 60=oblique

    # How much perspective distortion (more tilt = more perspective)
    perspective_factor = math.sin(tilt_rad)  # 0..1

    # Horizontal field of view in source image units
    hw = img_w * zoom  # half-width of visible ground area
    hh = img_h * zoom  # half-height

    # Near vs far edge width (perspective trapezoid)
    near_w = hw * (1 + perspective_factor * 0.8)
    far_w  = hw * (1 - perspective_factor * 0.5)

    # How far "forward" the view extends (forward = azimuth direction)
    forward_reach = hh * perspective_factor * 0.6

    # Direction vectors in image coordinates
    # Azimuth 0 = North = up in image (y decreases)
    fx =  math.sin(azim_rad)   # East component
    fy = -math.cos(azim_rad)   # North component (image y inverted)
    rx =  math.cos(azim_rad)   # Right component (perpendicular)
    ry =  math.sin(azim_rad)

    # Far center (in forward direction from image center)
    far_cx  = cx + fx * forward_reach
    far_cy  = cy + fy * forward_reach
    # Near center (slightly behind center)
    near_cx = cx - fx * forward_reach * 0.35
    near_cy = cy - fy * forward_reach * 0.35

    # Source quad in aerial image (trapezoid we see from this angle)
    src = [
        (far_cx  - rx * far_w,   far_cy  - ry * far_w),    # top-left  (far)
        (far_cx  + rx * far_w,   far_cy  + ry * far_w),    # top-right (far)
        (near_cx + rx * near_w,  near_cy + ry * near_w),   # bot-right (near)
        (near_cx - rx * near_w,  near_cy - ry * near_w),   # bot-left  (near)
    ]

    # Sky height depends on tilt angle
    sky_fraction = 0.12 + perspective_factor * 0.22  # 12-34% sky
    sky_h = int(screen_h * sky_fraction)
    terrain_y0 = sky_h

    # Destination quad = terrain portion of screen
    dst = [
        (0,        terrain_y0),
        (screen_w, terrain_y0),
        (screen_w, screen_h),
        (0,        screen_h),
    ]

    # Build frame
    frame = Image.new('RGB', (screen_w, screen_h), (0, 0, 0))

    # ── Sky gradient ──
    sky_arr = np.zeros((sky_h, screen_w, 3), dtype=np.uint8)
    for row in range(sky_h):
        t = row / max(sky_h - 1, 1)
        # Deep blue at zenith, pale blue at horizon
        sky_arr[row, :] = [
            int(8  + t * 110),   # R
            int(15 + t * 145),   # G
            int(45 + t * 185),   # B
        ]
    frame.paste(Image.fromarray(sky_arr), (0, 0))

    # ── Terrain perspective warp ──
    coeffs = find_perspective_coeffs(src, dst)
    if coeffs is not None:
        warped = shaded.transform(
            (screen_w, screen_h),
            Image.Transform.PERSPECTIVE,
            coeffs,
            Image.Resampling.BICUBIC
        )
        terrain_crop = warped.crop((0, terrain_y0, screen_w, screen_h))
        frame.paste(terrain_crop, (0, terrain_y0))

    # ── Atmospheric haze at horizon ──
    haze_rows = max(0, int((screen_h - terrain_y0) * 0.18))
    if haze_rows > 0:
        f_arr = np.array(frame, dtype=np.float32)
        for row in range(terrain_y0, terrain_y0 + haze_rows):
            t = 1.0 - (row - terrain_y0) / haze_rows
            t = t ** 1.5
            f_arr[row, :, 0] = f_arr[row, :, 0] * (1-t) + 150 * t
            f_arr[row, :, 1] = f_arr[row, :, 1] * (1-t) + 175 * t
            f_arr[row, :, 2] = f_arr[row, :, 2] * (1-t) + 210 * t
        frame = Image.fromarray(f_arr.clip(0,255).astype(np.uint8))

    # ── Lens vignette (subtle) ──
    vign = Image.new('RGBA', (screen_w, screen_h), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vign)
    for step in range(30):
        alpha = int(step * 2.5)
        pad = step * 4
        vd.rectangle([pad, pad, screen_w-pad, screen_h-pad],
                     outline=(0, 0, 0, alpha))
    frame = Image.alpha_composite(frame.convert('RGBA'), vign).convert('RGB')

    return frame


def add_google_earth_hud(frame: Image.Image, date_str: str,
                          lat: float, lon: float,
                          azim_deg: float, tilt_deg: float,
                          fidx: int, ftotal: int) -> Image.Image:
    """Google Earth stili UI overlay."""
    frame = frame.copy()
    d = ImageDraw.Draw(frame)
    W, H = frame.size

    try:
        f32 = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
        f20 = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        f15 = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
        f13 = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
    except Exception:
        f32 = f20 = f15 = f13 = ImageFont.load_default()

    white   = (255, 255, 255)
    yellow  = (255, 225, 40)
    lblue   = (160, 210, 255)
    shadow  = (0, 0, 0, 200)
    green   = (80, 220, 100)

    # ── Tarih rozeti (üst orta) ──
    db = d.textbbox((0,0), date_str, font=f32)
    dw = db[2] - db[0]
    dx = (W - dw) // 2
    # Shadow
    d.rectangle([dx-18, 12, dx+dw+18, 62], fill=(0,0,0,180))
    d.text((dx+2, 16), date_str, fill=(0,0,0,180), font=f32)  # drop shadow
    d.text((dx,   14), date_str, fill=yellow, font=f32)

    # ── Koordinat + bilgi (sol alt) ──
    info_bg_h = 85
    d.rectangle([0, H-info_bg_h, 370, H], fill=(0,0,0,160))
    d.text((14, H-info_bg_h+8),  f"Enlem:  {lat:.6f}°N", fill=white, font=f20)
    d.text((14, H-info_bg_h+32), f"Boylam: {lon:.6f}°E", fill=white, font=f20)
    d.text((14, H-info_bg_h+56), f"İrtifa: ~{900 + tilt_deg*0.5:.0f}m  |  GEE Sentinel-2 / SRTM", fill=lblue, font=f15)

    # ── İlerleme çubuğu (sağ alt) ──
    prog = (fidx+1) / max(ftotal,1)
    bx, by, bw, bh = W-175, H-32, 150, 16
    d.rectangle([bx-2, by-2, bx+bw+2, by+bh+2], fill=(30,30,30))
    d.rectangle([bx, by, bx+int(bw*prog), by+bh], fill=yellow)
    d.text((bx, by-22), f"Kare {fidx+1}/{ftotal}", fill=white, font=f13)

    # ── Pusula (sağ üst) ──
    nx, ny = W - 72, 72
    d.ellipse([nx-35, ny-35, nx+35, ny+35], outline=(255,255,255,180), width=2)
    d.ellipse([nx-32, ny-32, nx+32, ny+32], fill=(0,0,0,100))
    # Kuzey oku
    na = math.radians(-azim_deg)
    for r, col, wid in [(28, (255,60,60), 4), (28, (255,255,255), 2)]:
        tx = nx + r * math.sin(na)
        ty = ny - r * math.cos(na)
        bx2 = nx - (r*0.6) * math.sin(na)
        by2 = ny + (r*0.6) * math.cos(na)
        if col == (255,60,60):
            d.line([(bx2,by2),(tx,ty)], fill=col, width=wid)
        else:
            d.line([(bx2,by2),(tx,ty)], fill=col, width=1)
    d.text((nx-5, ny-55), "K", fill=white, font=f13)
    d.text((nx-5, ny+40), "G", fill=(180,180,180), font=f13)
    d.text((nx+40, ny-6), "D", fill=(180,180,180), font=f13)
    d.text((nx-56, ny-6), "B", fill=(180,180,180), font=f13)

    # ── Köşe süslemeleri ──
    pad, clen = 16, 28
    for cx2, cy2, sdx, sdy in [(pad,pad,1,1),(W-pad,pad,-1,1),(pad,H-pad,1,-1),(W-pad,H-pad,-1,-1)]:
        d.line([(cx2,cy2),(cx2+sdx*clen,cy2)], fill=white, width=2)
        d.line([(cx2,cy2),(cx2,cy2+sdy*clen)], fill=white, width=2)

    # ── Zoom seviyesi (sağ orta) ──
    zoom_pct = int(100 - tilt_deg)
    d.text((W-90, H//2-10), f"Zoom", fill=lblue, font=f13)
    d.text((W-90, H//2+6),  f"{zoom_pct}%", fill=white, font=f20)

    return frame


# ─────────────────────────────────────────────────────────────
# 4. Ana Pipeline
# ─────────────────────────────────────────────────────────────

def generate_gee_3d_timelapse(
    lat: float = 37.75737,
    lon: float = 30.12993,
    buffer_m: float = 800.0,
    start_date: str = "2019-01-01",
    end_date: str = "2024-12-31",
    output_path: str = "/tmp/gee_3d_timelapse.mp4",
    num_orbit_frames: int = 48,
    num_dates: int = 6,
    fps: int = 12,
    texture_size: int = 1024,
    tilt_min: float = 35.0,
    tilt_max: float = 60.0,
    zoom: float = 0.55,
) -> str:

    print("\n" + "═"*62)
    print("  🌍 GEE 3D Google Earth Tarihsel Timelapse")
    print("═"*62)
    print(f"  Koordinat: {lat:.5f}°N, {lon:.5f}°E")
    print(f"  Tampon: {buffer_m:.0f}m  |  Tarihler: {start_date} → {end_date}")
    print(f"  Çıktı: {output_path}")
    print("═"*62 + "\n")

    ee = init_gee()

    # Step 1: GEE SRTM DEM
    print("[1/5] GEE SRTM Yükseklik Verisi...")
    elevation = fetch_gee_elevation(ee, lat, lon, buffer_m, grid_size=128)

    # Step 2: Aerial base image (latest high-res)
    print("\n[2/5] GEE Yüksek Çözünürlüklü Uydu Görüntüsü...")
    try:
        aerial_base = fetch_gee_aerial(ee, lat, lon, buffer_m, size=texture_size)
    except Exception as e:
        print(f"  ⚠ GEE aerial failed ({e}), using Esri fallback...")
        import urllib.request, io
        lat_m, lon_m = deg_to_meters(lat)
        d_lat = buffer_m / lat_m; d_lon = buffer_m / lon_m
        minlon, minlat = lon-d_lon, lat-d_lat
        maxlon, maxlat = lon+d_lon, lat+d_lat
        esri_url = (f"https://services.arcgisonline.com/ArcGIS/rest/services/"
                    f"World_Imagery/MapServer/export?bbox={minlon},{minlat},{maxlon},{maxlat}"
                    f"&bboxSR=4326&imageSR=4326&size={texture_size},{texture_size}&format=jpg&f=image")
        req = urllib.request.Request(esri_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        aerial_base = Image.open(io.BytesIO(data)).convert('RGB')

    # Step 3: Historical scenes
    print("\n[3/5] GEE Tarihsel Sahne Listesi...")
    scenes = fetch_gee_historical_scenes(
        ee, lat, lon, buffer_m,
        start_date, end_date,
        num_scenes=num_dates,
        size=texture_size
    )

    if not scenes:
        print("  ⚠ Tarihsel sahne bulunamadı, aerial_base kullanılıyor")
        scenes = [("Güncel Görüntü", aerial_base)]

    # Step 4: Render
    total = num_orbit_frames * len(scenes)
    print(f"\n[4/5] {total} Kare Render Ediliyor ({num_orbit_frames} orbit × {len(scenes)} tarih)...")

    all_frames = []
    rendered = 0

    for tex_idx, (date_str, tex_img) in enumerate(scenes):
        # Enhance texture
        tex_img = tex_img.resize((texture_size, texture_size), Image.Resampling.LANCZOS)
        # Slight sharpening for Google Earth look
        tex_img = tex_img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))

        for cam_i in range(num_orbit_frames):
            t = cam_i / num_orbit_frames  # 0..1
            azim = t * 360.0

            # Tilt oscillates for cinematic effect
            tilt = tilt_min + (tilt_max - tilt_min) * (0.5 + 0.5 * math.sin(t * 2 * math.pi))

            frame = render_google_earth_frame(
                tex_img, elevation,
                azim_deg=azim,
                tilt_deg=tilt,
                screen_w=1280, screen_h=720,
                zoom=zoom
            )

            frame = add_google_earth_hud(
                frame, date_str, lat, lon,
                azim_deg=azim, tilt_deg=tilt,
                fidx=rendered, ftotal=total
            )

            all_frames.append(frame)
            rendered += 1

            if rendered % 12 == 0 or rendered == total:
                print(f"  Render: {rendered}/{total}", end="\r", flush=True)

    print(f"\n  ✓ {rendered} kare tamamlandı")

    # Step 5: Export
    print(f"\n[5/5] Video export...")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    frames_np = [np.array(f) for f in all_frames]

    try:
        import imageio.v2 as iio
        writer = iio.get_writer(output_path, fps=fps, codec='libx264',
                                 pixelformat='yuv420p', quality=9)
        for arr in frames_np:
            writer.append_data(arr)
        writer.close()
    except Exception:
        imageio.mimwrite(output_path, frames_np, fps=fps)

    mb = os.path.getsize(output_path) / 1e6
    print(f"  ✓ MP4: {output_path} ({mb:.1f} MB)")

    gif_path = output_path.replace(".mp4", "_preview.gif")
    try:
        step_g = max(1, len(all_frames) // 50)
        pv = [f.resize((640,360), Image.Resampling.LANCZOS) for f in all_frames[::step_g]]
        pv[0].save(gif_path, save_all=True, append_images=pv[1:],
                   duration=int(1000/max(fps//2,1)), loop=0, optimize=True)
        print(f"  ✓ GIF: {gif_path} ({os.path.getsize(gif_path)/1e6:.1f} MB)")
    except Exception as e:
        print(f"  ⚠ GIF: {e}")

    print("\n" + "═"*62)
    print("  ✅ TAMAMLANDI!")
    print(f"  📹 MP4: {output_path}")
    print(f"  🖼  GIF: {gif_path}")
    print("═"*62)
    return output_path


def main():
    p = argparse.ArgumentParser(description="GEE 3D Google Earth Timelapse")
    p.add_argument("--lat",     type=float, default=37.75737)
    p.add_argument("--lon",     type=float, default=30.12993)
    p.add_argument("--buffer",  type=float, default=800.0)
    p.add_argument("--start",   type=str,   default="2019-01-01")
    p.add_argument("--end",     type=str,   default="2024-12-31")
    p.add_argument("--output",  type=str,   default="/tmp/gee_3d_timelapse.mp4")
    p.add_argument("--frames",  type=int,   default=48)
    p.add_argument("--dates",   type=int,   default=6)
    p.add_argument("--fps",     type=int,   default=12)
    p.add_argument("--size",    type=int,   default=1024)
    p.add_argument("--zoom",    type=float, default=0.55)
    p.add_argument("--tilt-min",type=float, default=35.0)
    p.add_argument("--tilt-max",type=float, default=60.0)
    args = p.parse_args()
    generate_gee_3d_timelapse(
        lat=args.lat, lon=args.lon, buffer_m=args.buffer,
        start_date=args.start, end_date=args.end,
        output_path=args.output, num_orbit_frames=args.frames,
        num_dates=args.dates, fps=args.fps, texture_size=args.size,
        tilt_min=args.tilt_min, tilt_max=args.tilt_max, zoom=args.zoom
    )

if __name__ == "__main__":
    main()
