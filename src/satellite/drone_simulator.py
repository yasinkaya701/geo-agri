import os
import json
import time
import zipfile
import io
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import Tuple, Dict, Any, List
from src.config import logger
from src.geometry.projection import project_geometry

class DroneFlightSimulator:
    """3D perspective drone flight simulator for synthetic video and data generation."""
    
    @staticmethod
    def solve_homography(src_pts: List[Tuple[float, float]], dst_pts: List[Tuple[float, float]]) -> List[float]:
        """Calculates perspective transform coefficients for PIL.
        Maps dst_pts to src_pts (inverse mapping for transform).
        """
        matrix = []
        for i in range(4):
            x_dst, y_dst = dst_pts[i]
            x_src, y_src = src_pts[i]
            matrix.append([x_dst, y_dst, 1, 0, 0, 0, -x_dst * x_src, -y_dst * x_src])
            matrix.append([0, 0, 0, x_dst, y_dst, 1, -x_dst * y_src, -y_dst * y_src])
            
        A = np.array(matrix)
        B = np.array([
            src_pts[0][0], src_pts[0][1],
            src_pts[1][0], src_pts[1][1],
            src_pts[2][0], src_pts[2][1],
            src_pts[3][0], src_pts[3][1]
        ])
        
        coeffs = np.linalg.solve(A, B)
        return list(coeffs)

    def generate_flight_path(
        self,
        center_x: float,
        center_y: float,
        radius_x: float,
        radius_y: float,
        altitude: float,
        pitch_deg: float,
        path_type: str = "Orbital Scan",
        num_frames: int = 24
    ) -> List[Dict[str, Any]]:
        """Generates a list of camera poses (Xc, Yc, Zc, yaw_rad, pitch_rad) along the flight path."""
        poses = []
        pitch_rad = np.radians(pitch_deg)
        
        for idx in range(num_frames):
            t = (idx / num_frames) * 2.0 * np.pi
            
            if path_type == "Orbital Scan":
                # Circle around center
                Xc = center_x + radius_x * np.cos(t)
                Yc = center_y + radius_y * np.sin(t)
                Zc = altitude
                # Look towards the center
                dx = center_x - Xc
                dy = center_y - Yc
                yaw_rad = np.arctan2(dy, dx)
                
            elif path_type == "Lawnmower Mapping":
                # Zigzag path
                # grid size: e.g. 4 passes
                num_passes = 4
                pass_idx = int(t * num_passes / (2.0 * np.pi))
                fraction = (t * num_passes / (2.0 * np.pi)) - pass_idx
                
                # Alternate direction
                if pass_idx % 2 == 0:
                    y_fraction = fraction
                else:
                    y_fraction = 1.0 - fraction
                    
                x_pos = -1.0 + (pass_idx / (num_passes - 1)) * 2.0 # from -1 to 1
                y_pos = -1.0 + y_fraction * 2.0
                
                Xc = center_x + x_pos * radius_x
                Yc = center_y + y_pos * radius_y
                Zc = altitude
                
                # Lawnmower mapping cameras look nadir (straight down) or slightly forward
                yaw_rad = np.pi / 2.0 if pass_idx % 2 == 0 else -np.pi / 2.0
                
            else: # "Linear Flyover"
                # Straight line pass
                x_pos = -1.5 + (idx / (num_frames - 1)) * 3.0 # from -1.5 to 1.5
                Xc = center_x + x_pos * radius_x
                Yc = center_y
                Zc = altitude
                yaw_rad = 0.0 # looking East
                
            poses.append({
                "frame_idx": idx,
                "Xc": Xc,
                "Yc": Yc,
                "Zc": Zc,
                "yaw": yaw_rad,
                "pitch": pitch_rad,
                "pitch_deg": pitch_deg,
                "yaw_deg": np.degrees(yaw_rad) % 360
            })
            
        return poses

    def render_frame(
        self,
        base_img: Image.Image,
        pose: Dict[str, Any],
        img_bounds: Tuple[float, float, float, float], # minx, miny, maxx, maxy of base_img in degrees/meters
        fov_h_deg: float = 60.0,
        fov_v_deg: float = 45.0,
        screen_size: Tuple[int, int] = (640, 480)
    ) -> Tuple[Image.Image, Dict[str, Any]]:
        """Renders a single 3D perspective frame from a camera pose."""
        W_img, H_img = base_img.size
        minx, miny, maxx, maxy = img_bounds
        
        # Scale factors to convert world coordinate to base_img pixel coordinates
        scale_x = W_img / (maxx - minx)
        scale_y = H_img / (maxy - miny)
        
        # Helper to convert world coordinate to base_img pixel coordinate
        def world_to_pixel(wx: float, wy: float) -> Tuple[float, float]:
            px = (wx - minx) * scale_x
            # pixel y goes down, world y goes up
            py = H_img - (wy - miny) * scale_y
            return px, py
            
        # Camera parameters
        Xc, Yc, Zc = pose["Xc"], pose["Yc"], pose["Zc"]
        yaw = pose["yaw"]
        pitch = pose["pitch"]
        
        fov_h = np.radians(fov_h_deg)
        fov_v = np.radians(fov_v_deg)
        
        # Screen corners in normalized camera coordinates
        # Top-Left, Top-Right, Bottom-Right, Bottom-Left
        screen_pts = [(-1.0, 1.0), (1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)]
        ground_pixel_pts = []
        
        for sx, sy in screen_pts:
            # Ray in camera space
            rx = sx * np.tan(fov_h / 2.0)
            ry = sy * np.tan(fov_v / 2.0)
            rz = -1.0
            
            # Rotate pitch around camera's X-axis
            rx1 = rx
            ry1 = ry * np.cos(pitch) - rz * np.sin(pitch)
            rz1 = ry * np.sin(pitch) + rz * np.cos(pitch)
            
            # Rotate yaw around Z-axis
            rx2 = rx1 * np.cos(yaw) - ry1 * np.sin(yaw)
            ry2 = rx1 * np.sin(yaw) + ry1 * np.cos(yaw)
            rz2 = rz1
            
            # Intersect with ground Z = 0
            if rz2 >= -0.01:
                # Ray is pointing upwards or horizon, fallback to a far point
                t = 1000.0
            else:
                t = -Zc / rz2
                
            wx = Xc + t * rx2
            wy = Yc + t * ry2
            
            px, py = world_to_pixel(wx, wy)
            # Clip pixel coords to base image bounds + safe margin
            px = np.clip(px, -W_img, 2*W_img)
            py = np.clip(py, -H_img, 2*H_img)
            ground_pixel_pts.append((px, py))
            
        # Target coords (screen viewport corners)
        screen_w, screen_h = screen_size
        target_pts = [(0, 0), (screen_w, 0), (screen_w, screen_h), (0, screen_h)]
        
        # Compute Homography coefficients
        coeffs = self.solve_homography(ground_pixel_pts, target_pts)
        
        # Warp image
        frame = base_img.transform(screen_size, Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BILINEAR)
        
        # Create HUD metadata
        hud_data = {
            "altitude_m": Zc,
            "pitch_deg": pose["pitch_deg"],
            "yaw_deg": pose["yaw_deg"],
            "pos_x": Xc,
            "pos_y": Yc,
            "fov": fov_h_deg,
            "ground_corners": ground_pixel_pts
        }
        
        return frame, hud_data

    def draw_hud(
        self,
        frame: Image.Image,
        hud: Dict[str, Any],
        date_str: str,
        frame_idx: int,
        total_frames: int
    ) -> Image.Image:
        """Draws a green sci-fi Drone HUD overlay on the frame (telemetry, compass, pitch ladder)."""
        draw = ImageDraw.Draw(frame)
        w, h = frame.size
        
        # Use default font
        font = ImageFont.load_default()
        
        # HUD color (Neon Green)
        hud_color = (0, 255, 100)
        
        # 1. Outer corner borders (bracket effect)
        pad = 20
        length = 30
        # Top-Left
        draw.line([(pad, pad), (pad + length, pad)], fill=hud_color, width=2)
        draw.line([(pad, pad), (pad, pad + length)], fill=hud_color, width=2)
        # Top-Right
        draw.line([(w - pad, pad), (w - pad - length, pad)], fill=hud_color, width=2)
        draw.line([(w - pad, pad), (w - pad, pad + length)], fill=hud_color, width=2)
        # Bottom-Left
        draw.line([(pad, h - pad), (pad + length, h - pad)], fill=hud_color, width=2)
        draw.line([(pad, h - pad), (pad, h - pad - length)], fill=hud_color, width=2)
        # Bottom-Right
        draw.line([(w - pad, h - pad), (w - pad - length, h - pad)], fill=hud_color, width=2)
        draw.line([(w - pad, h - pad), (w - pad, h - pad - length)], fill=hud_color, width=2)
        
        # 2. Crosshair in the center
        cx, cy = w // 2, h // 2
        draw.line([(cx - 15, cy), (cx - 5, cy)], fill=hud_color, width=1)
        draw.line([(cx + 5, cy), (cx + 15, cy)], fill=hud_color, width=1)
        draw.line([(cx, cy - 15), (cx, cy - 5)], fill=hud_color, width=1)
        draw.line([(cx, cy + 5), (cx, cy + 15)], fill=hud_color, width=1)
        draw.ellipse([(cx - 2, cy - 2), (cx + 2, cy + 2)], fill=hud_color)
        
        # 3. Compass tape at the top
        compass_y = 25
        draw.line([(w // 2 - 100, compass_y), (w // 2 + 100, compass_y)], fill=hud_color, width=1)
        # Ticks and labels
        yaw_deg = hud["yaw_deg"]
        # Center tick
        draw.line([(w // 2, compass_y), (w // 2, compass_y - 6)], fill=hud_color, width=2)
        draw.text((w // 2 - 15, compass_y - 20), f"{int(yaw_deg):03d}°", fill=hud_color, font=font)
        
        # Cardinal directions
        cardinals = [("N", 0), ("E", 90), ("S", 180), ("W", 270)]
        for name, deg in cardinals:
            diff = (deg - yaw_deg + 180) % 360 - 180
            if abs(diff) < 45:
                tick_x = w // 2 + int(diff * 2.0) # 2 pixels per degree
                draw.line([(tick_x, compass_y), (tick_x, compass_y + 4)], fill=hud_color, width=1)
                draw.text((tick_x - 4, compass_y + 6), name, fill=hud_color, font=font)
                
        # 4. Telemetry stats on left and right columns
        # Left column: Flight telemetry
        col_x1 = 30
        draw.text((col_x1, 60), "SYS: UAV-ACTIVE", fill=hud_color, font=font)
        draw.text((col_x1, 75), f"ALT: {hud['altitude_m']:.1f} m", fill=hud_color, font=font)
        draw.text((col_x1, 90), f"SPD: {12.4 + np.sin(frame_idx/2.0)*1.5:.1f} m/s", fill=hud_color, font=font)
        draw.text((col_x1, 105), f"PITCH: {hud['pitch_deg']:.1f}°", fill=hud_color, font=font)
        
        # Right column: GPS and target info
        col_x2 = w - 180
        draw.text((col_x2, 60), f"LAT: {hud['pos_y']:.6f}°", fill=hud_color, font=font)
        draw.text((col_x2, 75), f"LON: {hud['pos_x']:.6f}°", fill=hud_color, font=font)
        draw.text((col_x2, 90), f"DATE: {date_str}", fill=hud_color, font=font)
        draw.text((col_x2, 105), f"CAM: FOV {hud['fov']}°", fill=hud_color, font=font)
        
        # 5. Artificial Horizon / Pitch ladder (horizon bar)
        pitch_val = hud["pitch_deg"]
        ladder_offset = int(pitch_val * 1.5)
        draw.line([(cx - 60, cy + ladder_offset), (cx - 20, cy + ladder_offset)], fill=hud_color, width=1)
        draw.line([(cx + 20, cy + ladder_offset), (cx + 60, cy + ladder_offset)], fill=hud_color, width=1)
        
        # 6. Recording state indicator
        draw.ellipse([(35, h - 35), (45, h - 25)], fill=(255, 0, 0) if (frame_idx % 2 == 0) else None, outline=(255, 0, 0))
        draw.text((55, h - 33), "REC · UAV FLYOVER", fill=(255, 0, 0), font=font)
        
        # Progress indicator
        draw.text((w - 120, h - 33), f"FRAME {frame_idx+1}/{total_frames}", fill=hud_color, font=font)
        
        return frame

    def create_uav_flight_dataset(
        self,
        base_img: Image.Image,
        centroid_lon: float,
        centroid_lat: float,
        radius_m: float,
        altitude: float,
        pitch_deg: float,
        fov_deg: float,
        path_type: str,
        num_frames: int,
        date_str: str,
        out_gif_path: str,
        out_zip_path: str,
        fps: int = 5,
        relative_field_coords: List[Tuple[float, float]] = None,
        buffer_meters: float = None
    ) -> Tuple[str, str]:
        """Simulates UAV flyover, saves animated GIF, and exports an ML-ready ZIP dataset."""
        # 1. Coordinate Bounds of Base Image in Projected Meters
        half_w_m = buffer_meters if buffer_meters is not None else (radius_m * 2.0)
        bounds = (-half_w_m, -half_w_m, half_w_m, half_w_m)
        
        # Flight path generation (centered at 0,0)
        poses = self.generate_flight_path(
            center_x=0.0,
            center_y=0.0,
            radius_x=radius_m,
            radius_y=radius_m,
            altitude=altitude,
            pitch_deg=pitch_deg,
            path_type=path_type,
            num_frames=num_frames
        )
        
        frames = []
        metadata_records = []
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for idx, pose in enumerate(poses):
                # Render perspective frame
                frame, hud_data = self.render_frame(
                    base_img=base_img,
                    pose=pose,
                    img_bounds=bounds,
                    fov_h_deg=fov_deg,
                    fov_v_deg=fov_deg * 0.75,
                    screen_size=(640, 480)
                )
                
                # Copy frame for saving to dataset before HUD overlay (raw ML training data)
                raw_frame = frame.copy()
                
                # Draw field outline in neon cyan if coordinates are provided
                if relative_field_coords:
                    try:
                        screen_coords = []
                        Xc, Yc, Zc = pose["Xc"], pose["Yc"], pose["Zc"]
                        yaw = pose["yaw"]
                        pitch = pose["pitch"]
                        fov_h = np.radians(fov_deg)
                        fov_v = np.radians(fov_deg * 0.75)
                        
                        for rx, ry in relative_field_coords:
                            # Translate
                            dx = rx - Xc
                            dy = ry - Yc
                            dz = 0.0 - Zc
                            
                            # Rotate Z
                            cos_y, sin_y = np.cos(-yaw), np.sin(-yaw)
                            dx1 = dx * cos_y - dy * sin_y
                            dy1 = dx * sin_y + dy * cos_y
                            
                            # Rotate X
                            cos_p, sin_p = np.cos(-pitch), np.sin(-pitch)
                            dx2 = dx1
                            dy2 = dy1 * cos_p - dz * sin_p
                            dz2 = dy1 * sin_p + dz * cos_p
                            
                            if dz2 < -0.1: # in front of camera
                                sx = dx2 / (-dz2 * np.tan(fov_h / 2.0))
                                sy = dy2 / (-dz2 * np.tan(fov_v / 2.0))
                                col = (sx + 1.0) * 640 / 2.0
                                row = (1.0 - sy) * 480 / 2.0
                                screen_coords.append((col, row))
                                
                        if len(screen_coords) > 1:
                            draw_outline = ImageDraw.Draw(frame)
                            draw_outline.polygon(screen_coords, outline=(0, 230, 255), width=2) # Neon Cyan
                    except Exception as draw_outline_err:
                        logger.warning(f"Could not draw field outline on 3D frame: {draw_outline_err}")
                
                # Draw sci-fi HUD on preview frame
                preview_frame = self.draw_hud(
                    frame=frame,
                    hud=hud_data,
                    date_str=date_str,
                    frame_idx=idx,
                    total_frames=num_frames
                )
                frames.append(preview_frame)
                
                # Save raw image to ZIP dataset
                buf = io.BytesIO()
                raw_frame.save(buf, format="JPEG", quality=90)
                zf.writestr(f"images/frame_{idx:03d}.jpg", buf.getvalue())
                
                # Save HUD preview to ZIP dataset
                buf_hud = io.BytesIO()
                preview_frame.save(buf_hud, format="JPEG", quality=90)
                zf.writestr(f"preview/hud_frame_{idx:03d}.jpg", buf_hud.getvalue())
                
                # Map pose to real lat/lon
                lat_m_deg = 111000.0
                lon_m_deg = 111000.0 * np.cos(np.radians(centroid_lat))
                
                real_lat = centroid_lat + (pose["Yc"] / lat_m_deg)
                real_lon = centroid_lon + (pose["Xc"] / lon_m_deg)
                
                metadata_records.append({
                    "frame": f"frame_{idx:03d}.jpg",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + idx)),
                    "camera_latitude": real_lat,
                    "camera_longitude": real_lon,
                    "camera_altitude_m": pose["Zc"],
                    "camera_yaw_deg": pose["yaw_deg"],
                    "camera_pitch_deg": pose["pitch_deg"],
                    "camera_fov_h_deg": fov_deg,
                    "camera_fov_v_deg": fov_deg * 0.75
                })
                
            # Save metadata JSON to ZIP dataset
            meta_json = {
                "dataset_name": f"Synthetic UAV Dataset - {path_type}",
                "center_latitude": centroid_lat,
                "center_longitude": centroid_lon,
                "flight_path": path_type,
                "altitude_m": altitude,
                "pitch_deg": pitch_deg,
                "frames": metadata_records
            }
            zf.writestr("metadata.json", json.dumps(meta_json, indent=4, ensure_ascii=False))
            
        # Save ZIP file
        os.makedirs(os.path.dirname(out_zip_path), exist_ok=True)
        with open(out_zip_path, 'wb') as f:
            f.write(zip_buffer.getvalue())
            
        # Save GIF file
        os.makedirs(os.path.dirname(out_gif_path), exist_ok=True)
        duration_ms = int(1000 / fps)
        frames[0].save(
            out_gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=duration_ms,
            loop=0
        )
        
        logger.info(f"Synthetic UAV flight dataset generated successfully: GIF={out_gif_path}, ZIP={out_zip_path}")
        return out_gif_path, out_zip_path
