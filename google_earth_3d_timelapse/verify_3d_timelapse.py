#!/usr/bin/env python3
"""Automated verification script for 3D timelapse pipeline."""
import sys
import os
sys.path.insert(0, '/Users/yasinkaya/TARIM UYDU')

from google_earth_3d_timelapse.generate_3d_timelapse import generate_3d_timelapse

OUT_MP4 = "/tmp/verify_3d_timelapse.mp4"
OUT_GIF = OUT_MP4.replace(".mp4", "_preview.gif")

print("=== 3D Timelapse Verification Test ===")
result = generate_3d_timelapse(
    lat=37.75737, lon=30.12993, buffer_m=400,
    start_date="2021-01-01", end_date="2023-12-31",
    output_path=OUT_MP4,
    num_orbit_frames=4, num_dates=2, fps=4,
    mesh_size=32, texture_size=256, z_exag=4.0
)

assert os.path.exists(OUT_MP4), f"MP4 not found: {OUT_MP4}"
assert os.path.getsize(OUT_MP4) > 10_000, f"MP4 too small: {os.path.getsize(OUT_MP4)} bytes"
assert os.path.exists(OUT_GIF), f"GIF not found: {OUT_GIF}"
assert os.path.getsize(OUT_GIF) > 5_000, f"GIF too small: {os.path.getsize(OUT_GIF)} bytes"

mp4_mb = os.path.getsize(OUT_MP4) / 1e6
gif_mb = os.path.getsize(OUT_GIF) / 1e6
print(f"\n[PASS] MP4 exists: {OUT_MP4} ({mp4_mb:.2f} MB)")
print(f"[PASS] GIF exists: {OUT_GIF} ({gif_mb:.2f} MB)")
print("[PASS] All acceptance criteria met.")
