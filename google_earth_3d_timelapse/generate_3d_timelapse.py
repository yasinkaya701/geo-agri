#!/usr/bin/env python3
"""
3D Google Earth-Style Historical Timelapse Video Generator
==========================================================
"""

import os
import sys
import math
import argparse
import io
import warnings
from typing import List, Tuple, Optional, Dict, Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from matplotlib.colors import LightSource
import imageio

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
ESRI_IMAGERY_URL = (
    "https://services.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/export"
)
PLANETARY_COMPUTER_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"


def deg_to_meters_factors(lat):
    lat_m = 111132.954 - 559.822 * math.cos(2 * math.radians(lat))
    lon_m = 111412.84 * math.cos(math.radians(lat))
    return lat_m, lon_m


def compute_bbox_wgs84(lat, lon, buffer_m):
    lat_m, lon_m = deg_to_meters_factors(lat)
    d_lat = buffer_m / lat_m
    d_lon = buffer_m / lon_m
    return lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat


def fetch_esri_imagery(bbox, size=1024):
    import urllib.request
    minlon, minlat, maxlon, maxlat = bbox
    params = (f"?bbox={minlon},{minlat},{maxlon},{maxlat}"
              f"&bboxSR=4326&imageSR=4326&size={size},{size}&format=jpg&f=image")
    url = ESRI_IMAGERY_URL + params
    print(f"  -> Esri World Imagery [{size}px]...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    img = Image.open(io.BytesIO(data)).convert("RGB")
    print(f"     OK {img.size[0]}x{img.size[1]}")
    return img


def fetch_stac_scenes(bbox, start_date, end_date, max_cloud=20.0, max_items=8):
    import requests
    minlon, minlat, maxlon, maxlat = bbox
    payload = {
        "collections": ["sentinel-2-l2a"],
        "bbox": [minlon, minlat, maxlon, maxlat],
        "datetime": f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lte": max_cloud}},
        "sortby": [{"field": "datetime", "direction": "asc"}],
        "limit": 100
    }
    print(f"  -> STAC search ({start_date} to {end_date})...")
    resp = requests.post(f"{PLANETARY_COMPUTER_STAC}/search", json=payload, timeout=20)
    resp.raise_for_status()
    features = resp.json().get("features", [])
    print(f"     Found {len(features)} scenes")
    if not features:
        return []
    step = max(1, len(features) // max_items)
    return features[::step][:max_items]


def fetch_sentinel_preview(scene, bbox, size=512):
    import urllib.request
    assets = scene.get("assets", {})
    if "rendered_preview" in assets:
        href = assets["rendered_preview"]["href"]
        try:
            req = urllib.request.Request(href, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            img = Image.open(io.BytesIO(data)).convert("RGB")
            return img.resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            pass
    return None


def fetch_elevation(bbox, grid_size=64):
    import urllib.request
    minlon, minlat, maxlon, maxlat = bbox
    print("  -> Fetching elevation (SRTM)...")
    try:
        url = (f"https://portal.opentopography.org/API/globaldem?"
               f"demtype=SRTMGL1&south={minlat}&north={maxlat}"
               f"&west={minlon}&east={maxlon}&outputFormat=GTiff&API_Key=demoapikeyot2022")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = resp.read()
        import rasterio
        with rasterio.MemoryFile(data) as memfile:
            with memfile.open() as ds:
                elev = ds.read(1).astype(np.float32)
                elev = np.flipud(elev)
                img_e = Image.fromarray(elev).resize((grid_size, grid_size), Image.Resampling.BILINEAR)
                elev = np.array(img_e, dtype=np.float32)
                print(f"     SRTM OK: min={elev.min():.0f}m max={elev.max():.0f}m")
                return elev
    except Exception as e:
        print(f"     SRTM failed ({e}), using synthetic terrain")
    # Synthetic fallback
    x = np.linspace(-1, 1, grid_size)
    y = np.linspace(-1, 1, grid_size)
    xx, yy = np.meshgrid(x, y)
    base = 950.0
    elev = base + (20.0 * np.sin(xx * 3.0) * np.cos(yy * 2.5) +
                   10.0 * np.sin(xx * 7.0 + 1.2) * np.cos(yy * 5.0) +
                   5.0 * np.cos(xx * 12.0) * np.sin(yy * 9.0))
    return elev.astype(np.float32)


def create_mesh(elevation, lat_range, lon_range, lat):
    rows, cols = elevation.shape
    lat_m, lon_m = deg_to_meters_factors(lat)
    lat_ext = (lat_range[1] - lat_range[0]) * lat_m
    lon_ext = (lon_range[1] - lon_range[0]) * lon_m
    x = np.linspace(-lon_ext / 2, lon_ext / 2, cols)
    y = np.linspace(-lat_ext / 2, lat_ext / 2, rows)
    X, Y = np.meshgrid(x, y)
    return X, Y, elevation.copy()


def blend_hillshade(tex_img, elevation, blend=0.35):
    h, w = elevation.shape
    tex = np.array(tex_img.resize((w, h), Image.Resampling.LANCZOS)).astype(np.float32) / 255.0
    ls = LightSource(azdeg=315, altdeg=45)
    shade = ls.hillshade(elevation, vert_exag=3.0, dx=10.0, dy=10.0)
    for c in range(3):
        tex[:, :, c] = np.clip(tex[:, :, c] * (1 - blend) + shade * blend, 0, 1)
    alpha = np.ones((h, w, 1), dtype=np.float32)
    return np.concatenate([tex, alpha], axis=2)


def render_frame(X, Y, Z, tex_rgba, azim, elev_ang, date_str, fidx, ftotal, z_exag=4.0):
    dpi = 100
    fig = plt.figure(figsize=(12.8, 7.2), dpi=dpi, facecolor='#0a0a1a')
    ax = fig.add_axes([0, 0, 1, 1], projection='3d', facecolor='#0a0a1a')
    Z_plot = (Z - Z.min()) * z_exag
    ax.plot_surface(X, Y, Z_plot, facecolors=tex_rgba[:, :, :3],
                    rstride=1, cstride=1, linewidth=0, antialiased=True, shade=False)
    ax.view_init(elev=elev_ang, azim=azim)
    ax.set_axis_off()
    x_r = X.max() - X.min()
    y_r = Y.max() - Y.min()
    z_r = max(Z_plot.max() - Z_plot.min(), 10.0)
    ax.set_xlim(X.min() - x_r * 0.05, X.max() + x_r * 0.05)
    ax.set_ylim(Y.min() - y_r * 0.05, Y.max() + y_r * 0.05)
    ax.set_zlim(-z_r * 0.1, z_r * 1.2)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', pad_inches=0, facecolor='#0a0a1a')
    plt.close(fig)
    buf.seek(0)
    img = Image.open(buf).convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS)
    buf.close()
    return img


def add_hud(frame, date_str, lat, lon, azim, elev_ang, fidx, ftotal, source):
    frame = frame.copy()
    draw = ImageDraw.Draw(frame)
    W, H = frame.size
    white = (255, 255, 255)
    yellow = (255, 230, 50)
    green = (100, 255, 120)
    try:
        fl = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
        fm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
        fs = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except Exception:
        fl = fm = fs = ImageFont.load_default()

    # Date badge
    db = draw.textbbox((0, 0), date_str, font=fl)
    dw = db[2] - db[0]
    dx = (W - dw) // 2
    draw.rectangle([dx - 14, 16, dx + dw + 14, 66], fill=(0, 0, 0, 200))
    draw.text((dx, 20), date_str, fill=yellow, font=fl)

    # Coords
    coord = f"Lat: {lat:.5f}  Lon: {lon:.5f}"
    draw.rectangle([10, H - 74, 360, H - 10], fill=(0, 0, 0, 180))
    draw.text((16, H - 70), coord, fill=white, font=fm)
    draw.text((16, H - 46), f"Az: {azim:.0f}deg  El: {elev_ang:.0f}deg", fill=green, font=fs)
    draw.text((16, H - 26), source, fill=(180, 180, 180), font=fs)

    # Progress
    prog = (fidx + 1) / ftotal
    bx, by, bw, bh = W - 162, H - 30, 140, 14
    draw.rectangle([bx - 2, by - 2, bx + bw + 2, by + bh + 2], fill=(40, 40, 40))
    draw.rectangle([bx, by, bx + int(bw * prog), by + bh], fill=yellow)
    draw.text((bx, by - 20), f"Frame {fidx+1}/{ftotal}", fill=white, font=fs)

    # Corners
    pad, clen = 14, 24
    for cx, cy, dx2, dy2 in [(pad, pad, 1, 1), (W - pad, pad, -1, 1),
                               (pad, H - pad, 1, -1), (W - pad, H - pad, -1, -1)]:
        draw.line([(cx, cy), (cx + dx2 * clen, cy)], fill=white, width=2)
        draw.line([(cx, cy), (cx, cy + dy2 * clen)], fill=white, width=2)

    # North arrow
    nx, ny = W - 70, 60
    draw.ellipse([nx - 30, ny - 30, nx + 30, ny + 30], outline=white, width=2)
    na = math.radians(-azim)
    al = 22
    draw.line([(nx - al * math.sin(na), ny + al * math.cos(na)),
               (nx + al * math.sin(na), ny - al * math.cos(na))],
              fill=(255, 60, 60), width=3)
    draw.text((nx - 5, ny - 48), "N", fill=white, font=fs)

    return frame


def generate_3d_timelapse(lat, lon, buffer_m=800, start_date="2019-01-01",
                           end_date="2024-12-31", output_path="/tmp/3d_timelapse.mp4",
                           num_orbit_frames=36, num_dates=6, fps=12,
                           mesh_size=64, texture_size=512, z_exag=4.0, max_cloud=20.0):
    # Input validation
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitude must be between -90 and 90. Got {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Longitude must be between -180 and 180. Got {lon}")
    if buffer_m <= 0:
        raise ValueError(f"Buffer radius must be positive. Got {buffer_m}")

    from datetime import datetime
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid start date format. Must be YYYY-MM-DD. Got {start_date}")
    try:
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid end date format. Must be YYYY-MM-DD. Got {end_date}")

    print("\n" + "="*60)
    print("  3D Google Earth Historical Timelapse")
    print("="*60)
    print(f"  Lat={lat:.5f}  Lon={lon:.5f}  Buffer={buffer_m:.0f}m")
    print(f"  Dates: {start_date} -> {end_date}")
    print(f"  Output: {output_path}\n")

    bbox = compute_bbox_wgs84(lat, lon, buffer_m)
    minlon, minlat, maxlon, maxlat = bbox

    print("[1/5] Elevation DEM...")
    elevation = fetch_elevation(bbox, grid_size=mesh_size)

    print("[2/5] 3D Terrain Mesh...")
    X, Y, Z = create_mesh(elevation, (minlat, maxlat), (minlon, maxlon), lat)

    print("[3/5] Satellite Imagery...")
    esri_img = None
    try:
        esri_img = fetch_esri_imagery(bbox, size=texture_size)
    except Exception as e:
        print(f"     Esri failed: {e}")

    try:
        scenes = fetch_stac_scenes(bbox, start_date, end_date, max_cloud=max_cloud, max_items=num_dates)
    except Exception as e:
        print(f"     STAC failed: {e}")
        scenes = []

    texture_frames = []
    for scene in scenes:
        props = scene.get("properties", {})
        date_str = props.get("datetime", "")[:10]
        cloud = props.get("eo:cloud_cover", 0)
        print(f"  -> Sentinel-2 {date_str} (cloud={cloud:.1f}%)")
        try:
            img = fetch_sentinel_preview(scene, bbox, size=texture_size)
        except Exception:
            img = None
        if img is None and esri_img:
            year = int(date_str[:4]) if len(date_str) >= 4 else 2022
            shift = (year - 2019) / 6.0
            r, g, b = esri_img.split()
            ra = np.clip(np.array(r, np.float32) * (1.0 - 0.08 * shift), 0, 255).astype(np.uint8)
            ga = np.clip(np.array(g, np.float32) * (1.0 + 0.06 * shift), 0, 255).astype(np.uint8)
            img = Image.merge("RGB", [Image.fromarray(ra), Image.fromarray(ga), b])
        if img is not None:
            texture_frames.append((date_str, img))

    if not texture_frames:
        base = esri_img or Image.new("RGB", (texture_size, texture_size), (100, 150, 80))
        texture_frames = [("Latest Imagery", base)]
    print(f"  OK: {len(texture_frames)} texture dates")

    print(f"\n[4/5] Rendering {num_orbit_frames * len(texture_frames)} 3D frames...")
    all_frames = []
    total = num_orbit_frames * len(texture_frames)
    rendered = 0

    for tex_idx, (date_str, tex_img) in enumerate(texture_frames):
        tex_rgba = blend_hillshade(tex_img, elevation, blend=0.35)
        for cam_i in range(num_orbit_frames):
            t = (cam_i / num_orbit_frames) * 360.0
            azim = t
            elev_ang = 32.0 + 6.0 * math.sin(math.radians(t * 2))
            frame = render_frame(X, Y, Z, tex_rgba, azim, elev_ang,
                                  date_str, rendered, total, z_exag)
            source = "Sentinel-2 / Esri World Imagery" if len(texture_frames) > 1 else "Esri World Imagery"
            frame = add_hud(frame, date_str, lat, lon, azim, elev_ang, rendered, total, source)
            all_frames.append(frame)
            rendered += 1
            if rendered % 12 == 0 or rendered == total:
                print(f"  Rendered {rendered}/{total}", end="\r", flush=True)

    print(f"\n  OK: {rendered} frames rendered")

    print(f"\n[5/5] Exporting video...")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    frames_np = [np.array(f) for f in all_frames]

    try:
        import imageio.v2 as iio
        writer = iio.get_writer(output_path, fps=fps, codec='libx264', pixelformat='yuv420p', quality=8)
        for arr in frames_np:
            writer.append_data(arr)
        writer.close()
    except Exception:
        imageio.mimwrite(output_path, frames_np, fps=fps)

    size_mb = os.path.getsize(output_path) / 1e6
    print(f"  MP4: {output_path} ({size_mb:.1f} MB)")

    gif_path = output_path.replace(".mp4", "_preview.gif")
    try:
        pv = [f.resize((640, 360), Image.Resampling.LANCZOS) for f in all_frames[::max(1, len(all_frames)//40)]]
        pv[0].save(gif_path, save_all=True, append_images=pv[1:],
                   duration=int(1000 / (fps // 2 or 1)), loop=0, optimize=True)
        print(f"  GIF preview: {gif_path} ({os.path.getsize(gif_path)/1e6:.1f} MB)")
    except Exception as e:
        print(f"  GIF failed: {e}")

    print("\n" + "="*60)
    print("  DONE!")
    print(f"  Video: {output_path}")
    print(f"  GIF: {gif_path}")
    print("="*60)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="3D Google Earth-style timelapse generator")
    parser.add_argument("--lat", type=float, default=37.75737)
    parser.add_argument("--lon", type=float, default=30.12993)
    parser.add_argument("--buffer", type=float, default=800.0)
    parser.add_argument("--start", type=str, default="2019-01-01")
    parser.add_argument("--end", type=str, default="2024-12-31")
    parser.add_argument("--output", type=str, default="/tmp/3d_timelapse.mp4")
    parser.add_argument("--frames", type=int, default=36)
    parser.add_argument("--dates", type=int, default=6)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--mesh-size", type=int, default=64)
    parser.add_argument("--texture-size", type=int, default=512)
    parser.add_argument("--z-exag", type=float, default=4.0)
    parser.add_argument("--max-cloud", type=float, default=20.0)
    args = parser.parse_args()
    try:
        generate_3d_timelapse(lat=args.lat, lon=args.lon, buffer_m=args.buffer,
                              start_date=args.start, end_date=args.end,
                              output_path=args.output, num_orbit_frames=args.frames,
                              num_dates=args.dates, fps=args.fps, mesh_size=args.mesh_size,
                              texture_size=args.texture_size, z_exag=args.z_exag,
                              max_cloud=args.max_cloud)
    except PermissionError as e:
        print(f"Permission denied: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
