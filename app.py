import os
import io
import json
import requests
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from shapely.geometry import shape, mapping
from typing import Dict, Any, List

# ─────────────────────────────────────────────────────────────
# Sayfa Konfigürasyonu (Tüm streamlit komutlarından önce)
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GEO-AGRI · Agricultural Remote Sensing Platform",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

from src.config import logger
from src.ui.styles import inject_custom_styles, app_header, geo_card, end_card, stat_row, section_label, divider
from src.ui.cesium_flyover import render_drone_flyover_tab
from src.ui.components import render_tkgm_selectors, render_folium_map
from src.ui.plots import plot_ndvi_time_series, plot_pixel_distribution
from src.geometry.projection import get_geometry_area_hectares
from src.satellite.stac_client import StacClient
from src.satellite.bands_loader import load_and_mask_bands
from src.dataset.ndvi import (
    calculate_ndvi, 
    interpolate_ndvi_series,
    calculate_ndwi,
    calculate_savi,
    calculate_evi
)
from src.dataset.filters import (
    apply_sobel_edge,
    apply_gaussian_blur,
    apply_contrast_stretching,
    apply_grayscale
)
from src.dataset.exporter import (
    generate_field_average_df, 
    generate_pixel_level_df, 
    export_to_npz
)
from src.dataset.ml_generator import MLDatasetGenerator, DatasetConfig
from src.dataset.ndvi import (
    savitzky_golay_smooth,
    extract_phenology,
    smooth_time_series_2d,
    compute_phenology_map
)

# ─────────────────────────────────────────────────────────────
# CSS Enjeksiyonu
# ─────────────────────────────────────────────────────────────
inject_custom_styles()
app_header()

# Query parameters check for GPS location
query_params = st.query_params
if "gps_lat" in query_params and "gps_lon" in query_params:
    try:
        lat_val = float(query_params["gps_lat"])
        lon_val = float(query_params["gps_lon"])
        st.session_state.gps_lat_val = lat_val
        st.session_state.gps_lon_val = lon_val
        
        # Temizleyelim ki sayfa yenilendiğinde tekrar tetiklenmesin
        st.query_params.clear()
        
        # Resmi kadastro parselini otomatik sorgula!
        from src.tkgm.megsis_client import MegsisClient
        megsis = MegsisClient()
        try:
            parcel_geojson = megsis.get_parcel_by_coordinates(lat_val, lon_val)
            st.session_state.active_geojson = parcel_geojson
            st.session_state.active_geometry = shape(parcel_geojson["geometry"])
            st.session_state.tkgm_properties = parcel_geojson["properties"]
            st.session_state.field_source = "TKGM"
            st.toast("🎯 GPS konumuna ait resmi kadastro parseli başarıyla yüklendi!", icon="✅")
        except Exception as e:
            logger.warning(f"GPS koordinatında resmi parsel bulunamadı: {e}")
            from shapely.geometry import box
            buffer_deg = 0.0006
            bbox_geom = box(lon_val - buffer_deg, lat_val - buffer_deg, lon_val + buffer_deg, lat_val + buffer_deg)
            
            st.session_state.active_geometry = bbox_geom
            st.session_state.active_geojson = {
                "type": "Feature",
                "geometry": mapping(bbox_geom),
                "properties": {}
            }
            st.session_state.field_source = "One-Click Quick Start"
            st.session_state.tkgm_properties = {
                "ilAd": "Hızlı Konum (Tampon)",
                "ilceAd": "-",
                "mahalleAd": "-",
                "adaNo": "-",
                "parselNo": "-",
                "alan": f"{bbox_geom.area * 1e8:.2f}",
                "nitelik": "Hızlı Konum Analizi"
            }
            st.toast("ℹ️ GPS konumu için resmi parsel bulunamadı. Tampon bölge oluşturuldu.", icon="⚠️")
    except Exception as e:
        logger.error(f"GPS parametre işleme hatası: {e}")

# ─────────────────────────────────────────────────────────────
# GEE Helper Function
# ─────────────────────────────────────────────────────────────
def render_gee_timelapse_tab(geometry_geojson, key_suffix=""):
    import time
    st.markdown(f"""
    <div class="geo-card">
        <div class="geo-card-title">🛰️ Uydu Zaman Tüneli (GEE)</div>
        <div class="geo-card-desc">Google Earth Engine gücüyle seçilen alanın bulut arındırılmış Sentinel-2 timelapse animasyonunu, videosunu ve fotoğraf setini oluşturun.</div>
    """, unsafe_allow_html=True)
    
    from src.satellite.gee_timelapse import (
        GEETimelapseEngine,
        convert_gif_to_mp4,
        extract_gif_frames_to_zip
    )
    
    try:
        engine = GEETimelapseEngine()
        if getattr(engine, 'is_simulated', True):
            st.info("ℹ️ Sistem Yerel STAC Modundadır (Açık kaynaklı gerçek Sentinel-2 uydusu RGB/NDVI verileri kullanılır).")
        else:
            st.success("🟢 Google Earth Engine API Bağlantısı Aktif!")
    except Exception as _e:
        engine = None
        st.info(f"ℹ️ GEE engine başlatılamadı ({_e}). STAC modu aktif.")
        
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        g_start_year = st.slider("Başlangıç Yılı", 2016, 2026, 2023, key=f"gee_start_{key_suffix}")
    with col_g2:
        g_end_year = st.slider("Bitiş Yılı", 2016, 2026, 2024, key=f"gee_end_{key_suffix}")
    with col_g3:
        g_fps = st.slider("Hız (Kare/Saniye - FPS)", 1, 10, 4, key=f"gee_fps_{key_suffix}")
        
    col_g4, col_g5 = st.columns(2)
    with col_g4:
        g_mode = st.selectbox("Görselleştirme Modu", ["Gerçek Renk (RGB)", "Bitki Sağlığı (NDVI)"], key=f"gee_mode_{key_suffix}")
    with col_g5:
        g_months = st.selectbox("Mevsim Aralığı", ["Tüm Yıl (Ocak - Aralık)", "Büyüme Sezonu (Mart - Ekim)"], key=f"gee_months_{key_suffix}")
        
    s_date = "01-01"
    e_date = "12-31"
    if g_months == "Büyüme Sezonu (Mart - Ekim)":
        s_date = "03-01"
        e_date = "10-31"
        
    btn_gee = st.button("🎬 Zaman Tüneli & Video Oluştur", type="primary", use_container_width=True, key=f"gee_btn_{key_suffix}")
    
    gif_key = f"gee_gif_path_{key_suffix}"
    mp4_key = f"gee_mp4_path_{key_suffix}"
    zip_key = f"gee_zip_path_{key_suffix}"
    
    if btn_gee:
        with st.spinner("Uydu görüntüleri GEE üzerinde işleniyor, video ve fotoğraflar hazırlanıyor..."):
            try:
                ts_int = int(time.time())
                out_path_gif = f"/tmp/gee_timelapse_{key_suffix}_{ts_int}.gif"
                out_path_mp4 = f"/tmp/gee_timelapse_{key_suffix}_{ts_int}.mp4"
                out_path_zip = f"/tmp/gee_timelapse_{key_suffix}_{ts_int}_fotos.zip"
                
                band_mode_code = "NDVI" if g_mode == "Bitki Sağlığı (NDVI)" else "RGB"
                
                # 1. GIF üret
                gif_result = engine.create_timelapse(
                    geometry_geojson=geometry_geojson,
                    out_gif_path=out_path_gif,
                    start_year=g_start_year,
                    end_year=g_end_year,
                    start_date=s_date,
                    end_date=e_date,
                    band_mode=band_mode_code,
                    fps=g_fps
                )
                
                # 2. MP4 videoya dönüştür
                mp4_result = convert_gif_to_mp4(gif_result, out_path_mp4, fps=g_fps)
                
                # 3. Kareleri ziple
                zip_result = extract_gif_frames_to_zip(gif_result, out_path_zip)
                
                st.session_state[gif_key] = gif_result
                st.session_state[mp4_key] = mp4_result
                st.session_state[zip_key] = zip_result
                st.success("✅ Zaman tüneli, MP4 video ve fotoğraf arşivi başarıyla üretildi!")
            except Exception as e:
                st.error(f"Zaman tüneli oluşturulamadı: {e}")
                
    if gif_key in st.session_state and os.path.exists(st.session_state[gif_key]):
        g_path = st.session_state[gif_key]
        m_path = st.session_state[mp4_key]
        z_path = st.session_state[zip_key]
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Display options
        col_disp1, col_disp2 = st.columns(2)
        with col_disp1:
            st.markdown("**🎬 MP4 Video Önizleme**")
            if os.path.exists(m_path):
                st.video(m_path)
            else:
                st.info("Video dosyası bulunamadı.")
        with col_disp2:
            st.markdown("**🖼️ GIF Animasyon Önizleme**")
            st.image(g_path, use_container_width=True)
            
        # Download buttons
        st.markdown("<br>", unsafe_allow_html=True)
        col_dl1, col_dl2, col_dl3 = st.columns(3)
        
        band_mode_code = "NDVI" if g_mode == "Bitki Sağlığı (NDVI)" else "RGB"
        
        with col_dl1:
            with open(g_path, "rb") as f:
                st.download_button(
                    label="📥 GIF Animasyonu İndir",
                    data=f.read(),
                    file_name=f"tarla_timelapse_{g_start_year}_{g_end_year}_{band_mode_code.lower()}.gif",
                    mime="image/gif",
                    use_container_width=True
                )
        with col_dl2:
            if os.path.exists(m_path):
                with open(m_path, "rb") as f:
                    st.download_button(
                        label="🎬 MP4 Video İndir",
                        data=f.read(),
                        file_name=f"tarla_video_{g_start_year}_{g_end_year}_{band_mode_code.lower()}.mp4",
                        mime="video/mp4",
                        use_container_width=True
                    )
        with col_dl3:
            if os.path.exists(z_path):
                with open(z_path, "rb") as f:
                    st.download_button(
                        label="🖼️ Tüm Fotoğrafları İndir (.zip)",
                        data=f.read(),
                        file_name=f"tarla_fotograflar_{g_start_year}_{g_end_year}_{band_mode_code.lower()}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
            
    st.markdown("</div>", unsafe_allow_html=True)
            
    st.markdown("</div>", unsafe_allow_html=True)


def render_uav_simulator_tab(geometry_geojson, key_suffix=""):
    st.markdown(f"""
    <div class="geo-card">
        <div class="geo-card-title">🛸 3D Drone Uçuş Simülatörü & Sentetik Veri Fabrikası</div>
        <div class="geo-card-desc">Seçili alandan kalkan bir drone'un uçuş rotasını 3D perspektifle simüle edin, HUD telemetrisi ile video üretin ve ML modelleri için sentetik veri seti toplayın.</div>
    """, unsafe_allow_html=True)
    
    # Parametreleri al
    
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        uav_alt = st.slider("Uçuş Yüksekliği (Metre - Altitude)", 10, 150, 60, key=f"uav_alt_{key_suffix}")
        uav_pitch = st.slider("Kamera Eğimi (Derece - Pitch)", 0, 70, 45, key=f"uav_pitch_{key_suffix}", help="0: Nadir (tam dik aşağı), 60+: Oblique (eğik bakış)")
    with col_u2:
        uav_fov = st.slider("Görüş Açısı (FOV - Field of View)", 40, 90, 65, key=f"uav_fov_{key_suffix}")
        uav_path = st.selectbox("Uçuş Rotası (Path Type)", [
            "Dairesel Yörünge (Orbital Scan)",
            "Zigzag / Haritalama (Lawnmower Mapping)",
            "Düz Hat Geçişi (Linear Flyover)"
        ], key=f"uav_path_{key_suffix}")
        
    col_u3, col_u4 = st.columns(2)
    with col_u3:
        uav_frames = st.slider("Toplam Çekim Sayısı (Kare)", 12, 60, 24, key=f"uav_frames_{key_suffix}")
    with col_u4:
        uav_fps = st.slider("Video Hızı (FPS)", 2, 10, 5, key=f"uav_fps_{key_suffix}")
        
    btn_uav = st.button("🎮 3D Drone Uçuş Videosu & ML Veri Seti Üret", type="primary", use_container_width=True, key=f"uav_btn_{key_suffix}")
    
    gif_key = f"uav_gif_path_{key_suffix}"
    zip_key = f"uav_zip_path_{key_suffix}"
    
    if btn_uav:
        with st.spinner("3D perspektif hesaplanıyor ve drone uçuşu simüle ediliyor..."):
            try:
                from src.satellite.drone_simulator import DroneFlightSimulator
                from shapely.geometry import shape
                
                sim = DroneFlightSimulator()
                
                # 1. Koordinatları ve geometrileri UTM cinsinden parse et
                geom_shape = shape(geometry_geojson.get("geometry", geometry_geojson))
                centroid_lon, centroid_lat = geom_shape.centroid.x, geom_shape.centroid.y
                
                from src.geometry.projection import project_geometry
                target_crs = 3857
                if "processed_data" in st.session_state and st.session_state.processed_data:
                    target_crs = st.session_state.processed_data[-1]["bands"]["red"].rio.crs
                
                projected_geom = project_geometry(geom_shape, from_crs=4326, to_crs=target_crs)
                cx, cy = projected_geom.centroid.x, projected_geom.centroid.y
                
                relative_coords = []
                for vx, vy in projected_geom.exterior.coords:
                    relative_coords.append((vx - cx, vy - cy))
                    
                minx, miny, maxx, maxy = projected_geom.bounds
                radius_m = max(maxx - minx, maxy - miny) * 0.8
                if radius_m < 30:
                    radius_m = 50.0 # fallback
                    
                # 2. Gerçek Uydu Görüntüsünü STAC üzerinden geniş açılı (Tamponlu) İndir
                buffer_m = radius_m * 2.5
                if buffer_m < 200.0:
                    buffer_m = 200.0
                    
                stac_base_img = None
                esri_base_img = None
                date_str = "2024-06-01"
                
                # Harita indirme durumunu kullanıcıya gösterelim
                status_placeholder = st.empty()
                status_placeholder.markdown("🌍 **Esri World Imagery üzerinden yüksek çözünürlüklü uydu görüntüsü indiriliyor...**")
                
                try:
                    from src.satellite.bands_loader import load_esri_ground_texture
                    esri_base_img = load_esri_ground_texture(centroid_lat, centroid_lon, buffer_meters=buffer_m)
                    if esri_base_img:
                        date_str = "Esri World Imagery"
                        status_placeholder.markdown("✅ **Esri World Imagery (Yüksek Çözünürlük) başarıyla indirildi. 3D uçuş simüle ediliyor...**")
                except Exception as esri_err:
                    logger.warning(f"Could not load ground texture from ESRI: {esri_err}")
                
                if esri_base_img is None:
                    status_placeholder.markdown("🛰️ **Esri görüntüsü alınamadı. STAC Kataloğunda en temiz Sentinel-2 uydu karesi sorgulanıyor...**")
                    try:
                        from src.satellite.stac_client import StacClient
                        from src.satellite.bands_loader import load_uav_ground_texture
                        import pandas as pd
                        
                        stac = StacClient()
                        
                        # Son 6 ayın görüntülerine bakalım
                        end_dt_val = st.session_state.get("end_date", pd.to_datetime("2024-10-31"))
                        start_dt_val = end_dt_val - pd.DateOffset(months=6)
                        
                        items = stac.search_sentinel_data(
                            geometry_wgs84=geom_shape,
                            start_date=start_dt_val.strftime("%Y-%m-%d"),
                            end_date=end_dt_val.strftime("%Y-%m-%d"),
                            max_cloud_cover=25.0
                        )
                        
                        if items:
                            # En bulutsuz kareyi seç
                            best_item = sorted(items, key=lambda x: x.properties.get("eo:cloud_cover", 100.0))[0]
                            date_str = best_item.properties.get("datetime", "")[:10]
                            status_placeholder.markdown(f"📥 **Sentinel-2 uydu görüntüsü indiriliyor (Tarih: {date_str}, Bulut: {best_item.properties.get('eo:cloud_cover', 0.0):.2f}%)...**")
                            
                            loaded_uav = load_uav_ground_texture(best_item, geom_shape, buffer_meters=buffer_m)
                            if loaded_uav:
                                r = np.nan_to_num(loaded_uav["red"].values, nan=0.0)
                                g = np.nan_to_num(loaded_uav["green"].values, nan=0.0)
                                b = np.nan_to_num(loaded_uav["blue"].values, nan=0.0)
                                
                                rgb = np.dstack([r, g, b])
                                # Kontrast artırımı (2% - 98% percentile)
                                p_low, p_high = np.percentile(rgb, (2, 98))
                                rgb = np.clip((rgb - p_low) / (p_high - p_low + 1e-5), 0, 1)
                                img_np = (rgb * 255).astype(np.uint8)
                                stac_base_img = Image.fromarray(img_np)
                                status_placeholder.markdown("✅ **Sentinel-2 uydu görüntüsü başarıyla alındı. 3D render yapılıyor...**")
                    except Exception as stac_err:
                        logger.warning(f"Could not load ground texture from STAC: {stac_err}")
                        status_placeholder.markdown("⚠️ **Gerçek uydu görüntüsü alınamadı. Simüle edilmiş harita kullanılıyor...**")
                    
                if esri_base_img is not None:
                    base_img = esri_base_img
                elif stac_base_img is not None:
                    base_img = stac_base_img
                else:
                    # Fallback yapay harita üreteci
                    img_w, img_h = 1024, 1024
                    img = Image.new("RGB", (img_w, img_h), color=(139, 115, 85))
                    draw = ImageDraw.Draw(img)
                    draw.polygon([(50, 50), (450, 30), (400, 480), (80, 500)], fill=(76, 154, 42))
                    draw.polygon([(500, 80), (980, 50), (950, 400), (520, 450)], fill=(120, 160, 50))
                    draw.polygon([(80, 550), (420, 520), (450, 950), (100, 980)], fill=(16, 100, 4))
                    draw.polygon([(520, 500), (950, 480), (980, 950), (480, 920)], fill=(150, 130, 90))
                    draw.line([(0, 500), (1024, 480)], fill=(200, 200, 200), width=30)
                    draw.line([(500, 0), (480, 1024)], fill=(200, 200, 200), width=30)
                    for tree_pos in [(200, 200), (300, 250), (800, 800), (750, 850), (600, 150)]:
                        draw.ellipse([(tree_pos[0]-15, tree_pos[1]-15), (tree_pos[0]+15, tree_pos[1]+15)], fill=(10, 80, 2))
                    base_img = img
                    
                # 3D Uçuşa hazırlık için yumuşat ve büyüt
                base_img = base_img.resize((1024, 1024), Image.Resampling.LANCZOS)
                
                # 3. 3D Uçuş Simülasyonu ve Video Kaydı
                ts_int = int(time.time())
                out_path_gif = f"/tmp/uav_simulation_{key_suffix}_{ts_int}.gif"
                out_path_zip = f"/tmp/uav_dataset_{key_suffix}_{ts_int}.zip"
                out_path_mp4 = f"/tmp/uav_simulation_{key_suffix}_{ts_int}.mp4"
                
                path_code = "Orbital Scan"
                if uav_path == "Zigzag / Haritalama (Lawnmower Mapping)":
                    path_code = "Lawnmower Mapping"
                elif uav_path == "Düz Hat Geçişi (Linear Flyover)":
                    path_code = "Linear Flyover"
                
                gif_result, zip_result = sim.create_uav_flight_dataset(
                    base_img=base_img,
                    centroid_lon=centroid_lon,
                    centroid_lat=centroid_lat,
                    radius_m=radius_m,
                    altitude=uav_alt,
                    pitch_deg=uav_pitch,
                    fov_deg=uav_fov,
                    path_type=path_code,
                    num_frames=uav_frames,
                    date_str=date_str,
                    out_gif_path=out_path_gif,
                    out_zip_path=out_path_zip,
                    fps=uav_fps,
                    relative_field_coords=relative_coords,
                    buffer_meters=buffer_m
                )
                
                # MP4 formatına dönüştürme
                from src.satellite.gee_timelapse import convert_gif_to_mp4
                mp4_result = convert_gif_to_mp4(gif_result, out_path_mp4, fps=uav_fps)
                
                st.session_state[gif_key] = gif_result
                st.session_state[zip_key] = zip_result
                st.session_state[f"uav_mp4_path_{key_suffix}"] = mp4_result
                status_placeholder.empty()
                st.success("✅ 3D Drone uçuşu ve sentetik derin öğrenme veri seti başarıyla üretildi!")
            except Exception as e:
                st.error(f"Uçuş simülasyonu başarısız oldu: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
    if gif_key in st.session_state and os.path.exists(st.session_state[gif_key]):
        g_path = st.session_state[gif_key]
        z_path = st.session_state[zip_key]
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        col_disp1, col_disp2 = st.columns([2, 1])
        with col_disp1:
            st.markdown("**🎮 3D Drone Kokpit / Telemetri Önizleme**")
            st.image(g_path, use_container_width=True)
        with col_disp2:
            st.markdown("**📊 Veri Seti Detayları**")
            st.markdown(f"""
            - **Uçuş Yüksekliği:** {uav_alt} metre
            - **Kamera Eğimi (Pitch):** {uav_pitch}°
            - **Görüş Açısı (FOV):** {uav_fov}°
            - **Rota tipi:** {uav_path}
            - **Sentetik Kareler:** {uav_frames} adet (JPEG)
            - **Etiket formatı:** `metadata.json` (Coğrafi ve yönelim bilgileriyle)
            """)
            
            st.markdown("<br>", unsafe_allow_html=True)
            with open(g_path, "rb") as f:
                st.download_button(
                    label="📥 Uçuş Animasyonunu İndir (.gif)",
                    data=f.read(),
                    file_name=f"uav_flight_simulation.gif",
                    mime="image/gif",
                    use_container_width=True
                )
                
            mp4_path_key = f"uav_mp4_path_{key_suffix}"
            if mp4_path_key in st.session_state and os.path.exists(st.session_state[mp4_path_key]):
                with open(st.session_state[mp4_path_key], "rb") as f:
                    st.download_button(
                        label="🎥 Uçuş Videosunu İndir (.mp4)",
                        data=f.read(),
                        file_name=f"uav_flight_simulation.mp4",
                        mime="video/mp4",
                        use_container_width=True
                    )
                    
            if os.path.exists(z_path):
                with open(z_path, "rb") as f:
                    st.download_button(
                        label="📦 Sentetik ML Veri Setini İndir (.zip)",
                        data=f.read(),
                        file_name=f"synthetic_uav_dataset.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    
    st.markdown("</div>", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
#  3D GOOGLE EARTH TIMELAPSE TAB
# ═════════════════════════════════════════════════════════════

def render_3d_terrain_tab(geometry_geojson, key_suffix=""):
    """3D Google Earth Tarihsel Timelapse — GEE (earth-500319) destekli."""
    st.markdown(f"""
    <div class="geo-card">
        <div class="geo-card-title">🌍 3D Google Earth Tarihsel Timelapse</div>
        <div class="geo-card-desc">
            Gerçek Google Earth Engine verisi (SRTM yükseklik + Sentinel-2 tarihsel sahneler)
            ile seçili tarlanın 3D perspektif kamera dönüş videosu üretilir.
            Birebir Google Earth görünümü &nbsp;·&nbsp; GEE Proje: <code>earth-500319</code>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        t3d_start  = st.text_input("Başlangıç Tarihi", "2019-01-01", key=f"t3d_start_{key_suffix}")
        t3d_end    = st.text_input("Bitiş Tarihi",     "2024-12-31", key=f"t3d_end_{key_suffix}")
        t3d_buffer = st.slider("Görüntü Tamponu (m)", 300, 2000, 800, 50, key=f"t3d_buf_{key_suffix}")
        t3d_zoom   = st.slider("Görüş Alanı", 0.3, 0.9, 0.55, 0.05, key=f"t3d_zoom_{key_suffix}")
    with col_b:
        t3d_frames = st.slider("Orbit Frame (tarih başına)", 24, 72, 48, 12, key=f"t3d_frames_{key_suffix}")
        t3d_dates  = st.slider("Tarih Sayısı", 2, 8, 6, 1, key=f"t3d_dates_{key_suffix}")
        t3d_fps    = st.slider("Video FPS", 8, 24, 12, key=f"t3d_fps_{key_suffix}")
        t3d_tilt_min = st.slider("Min Tilt Açısı", 20, 55, 38, key=f"t3d_tmin_{key_suffix}")
        t3d_tilt_max = st.slider("Max Tilt Açısı", 40, 80, 62, key=f"t3d_tmax_{key_suffix}")

    st.info("GEE Kaynakları: SRTM 30m + Sentinel-2 SR Harmonized + Esri fallback")

    btn_3d = st.button("🌍 GEE 3D Timelapse Videosu Üret", type="primary",
                        use_container_width=True, key=f"t3d_btn_{key_suffix}")

    mp4_key = f"t3d_mp4_{key_suffix}"
    gif_key = f"t3d_gif_{key_suffix}"

    if btn_3d:
        prog_bar = st.progress(0, text="GEE bağlantısı kuruluyor...")
        status   = st.empty()
        try:
            import sys, time as _time
            sys.path.insert(0, os.path.dirname(__file__))
            from google_earth_3d_timelapse.gee_3d_timelapse import generate_gee_3d_timelapse
            from shapely.geometry import shape as shp_shape

            geom = shp_shape(geometry_geojson.get("geometry", geometry_geojson))
            lat  = geom.centroid.y
            lon  = geom.centroid.x

            ts      = int(_time.time())
            out_mp4 = f"/tmp/gee3d_{key_suffix}_{ts}.mp4"

            prog_bar.progress(10, text="SRTM yükseklik verisi indiriliyor...")
            status.markdown(f"**Koordinat:** {lat:.5f}N, {lon:.5f}E")

            mp4 = generate_gee_3d_timelapse(
                lat=lat, lon=lon,
                buffer_m=t3d_buffer,
                start_date=t3d_start,
                end_date=t3d_end,
                output_path=out_mp4,
                num_orbit_frames=t3d_frames,
                num_dates=t3d_dates,
                fps=t3d_fps,
                texture_size=1024,
                tilt_min=float(t3d_tilt_min),
                tilt_max=float(t3d_tilt_max),
                zoom=t3d_zoom,
            )
            gif = mp4.replace(".mp4", "_preview.gif")

            st.session_state[mp4_key] = mp4
            st.session_state[gif_key] = gif if os.path.exists(gif) else None

            prog_bar.progress(100, text="Tamamlandi!")
            status.empty()
            st.success("3D Google Earth videosu basariyla uretildi!")

        except Exception as e:
            prog_bar.empty()
            st.error(f"GEE Video hatasi: {e}")
            import traceback; logger.error(traceback.format_exc())

    if mp4_key in st.session_state and st.session_state[mp4_key] and os.path.exists(st.session_state[mp4_key]):
        mp4_path = st.session_state[mp4_key]
        gif_path = st.session_state.get(gif_key)

        col_v1, col_v2 = st.columns([2, 1])
        with col_v1:
            st.markdown("**3D Google Earth Timelapse Onizleme**")
            if gif_path and os.path.exists(gif_path):
                st.image(gif_path, use_container_width=True,
                         caption="GEE Sentinel-2 Tarihsel Orbit Animasyonu")
            else:
                st.info("MP4'u indirin.")
        with col_v2:
            st.markdown("**Indir**")
            with open(mp4_path, "rb") as f:
                st.download_button(
                    label="3D Video Indir (.mp4)",
                    data=f.read(),
                    file_name="gee_3d_timelapse.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                    key=f"dl_mp4_{key_suffix}"
                )
            if gif_path and os.path.exists(gif_path):
                with open(gif_path, "rb") as f:
                    st.download_button(
                        label="GIF Indir",
                        data=f.read(),
                        file_name="gee_3d_preview.gif",
                        mime="image/gif",
                        use_container_width=True,
                        key=f"dl_gif_{key_suffix}"
                    )
            mb = os.path.getsize(mp4_path) / 1e6
            st.markdown(f"Boyut: {mb:.1f} MB | Format: H.264 1280x720 | Kaynak: GEE earth-500319")

    st.markdown("</div>", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
#  SIDEBAR — Dashboard Navigation
# ═════════════════════════════════════════════════════════════

with st.sidebar:
    # Brand
    st.markdown("""
    <div class="sidebar-logo">
        <div class="sidebar-logo-icon">🛰️</div>
        <div>
            <div class="sidebar-logo-name">GEO-AGRI</div>
            <div class="sidebar-logo-ver">v2.0 · Agricultural RS</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ─── Analiz Modu ───
    st.markdown("""
    <p class="sidebar-section-label">🛠️ Analiz Modu</p>
    """, unsafe_allow_html=True)
    
    analysis_mode = st.radio(
        "Mod Seçin",
        ["Hızlı Yerel Gözlem (Mevsimlik)", "Dağıtık Veri Fabrikası (10 Yıllık)", "🛸 Drone Analiz Stüdyosu (WebODM)"],
        key="analysis_mode",
        label_visibility="collapsed"
    )
    
    st.markdown('<hr style="border-color:rgba(255,255,255,0.07);margin:12px 0;">', unsafe_allow_html=True)
    
    # ─── Tarih Parametreleri ───
    if analysis_mode == "Hızlı Yerel Gözlem (Mevsimlik)":
        st.markdown("""
        <p class="sidebar-section-label">📅 Tarih Aralığı</p>
        """, unsafe_allow_html=True)
        
        col_s, col_e = st.columns(2)
        with col_s:
            start_date = st.date_input("Başlangıç", value=pd.to_datetime("2024-03-01"), key="start_date")
        with col_e:
            end_date = st.date_input("Bitiş", value=pd.to_datetime("2024-10-31"), key="end_date")
            
        st.markdown('<hr style="border-color:rgba(255,255,255,0.07);margin:12px 0;">', unsafe_allow_html=True)
        
        # ─── Bulut Toleransı ───
        st.markdown("""
        <p class="sidebar-section-label">☁️ Bulut Toleransı</p>
        """, unsafe_allow_html=True)
        
        max_cloud_cover = st.slider(
            "Sahne Bulutluluğu (%)", 
            min_value=0.0, max_value=100.0, value=20.0, step=5.0,
            help="Sentinel-2 karesinin maksimum bulutluluk oranı."
        )
        
        max_field_cloud_percent = st.slider(
            "Tarla İçi Bulut (%)", 
            min_value=0.0, max_value=100.0, value=30.0, step=5.0,
            help="Tarla sınırları içindeki bulutlu piksel toleransı."
        )
        
        st.markdown('<hr style="border-color:rgba(255,255,255,0.07);margin:12px 0;">', unsafe_allow_html=True)
        
        # ─── Zaman Serisi ───
        st.markdown("""
        <p class="sidebar-section-label">📈 Zaman Serisi</p>
        """, unsafe_allow_html=True)
        
        interpolate_empty = st.checkbox(
            "Enterpolasyon Uygula", 
            value=True,
            help="NaN değerleri doğrusal zaman enterpolasyonu ile tamamlar."
        )
    elif analysis_mode == "🛸 Drone Analiz Stüdyosu (WebODM)":
        st.markdown("""
        <p class="sidebar-section-label">🔗 WebODM Bağlantısı</p>
        """, unsafe_allow_html=True)
        
        odm_simulated = st.checkbox("Simülasyon Modu (Mock)", value=True, help="Sunucu olmadan test etmek için aktif edin.", key="odm_simulated")
        
        col_h, col_p = st.columns([2, 1])
        with col_h:
            odm_host = st.text_input("Sunucu IP", value="localhost", key="odm_host_input")
        with col_p:
            odm_port = st.number_input("Port", value=3000, key="odm_port_input")
            
        st.markdown('<hr style="border-color:rgba(255,255,255,0.07);margin:12px 0;">', unsafe_allow_html=True)
        
        st.markdown("""
        <p class="sidebar-section-label">⚙️ İşlem Ayarları</p>
        """, unsafe_allow_html=True)
        
        odm_quality = st.selectbox("Kalite Profili", ["Hızlı Önizleme (Düşük)", "Standart (Orta)", "Yüksek Detay (Premium)"], key="odm_quality")
        odm_dsm = st.checkbox("Dijital Yüzey Modeli (DSM)", value=True, key="odm_dsm_check")
        odm_res = st.number_input("Çözünürlük (m/piksel)", value=0.05, min_value=0.01, max_value=0.5, step=0.01, key="odm_res_input")
    else:
        st.markdown("""
        <p class="sidebar-section-label">📅 Yıl Aralığı</p>
        """, unsafe_allow_html=True)
        
        col_ys, col_ye = st.columns(2)
        with col_ys:
            start_year = st.number_input("Başlangıç", min_value=2016, max_value=2026, value=2016, step=1, key="start_year")
        with col_ye:
            end_year = st.number_input("Bitiş", min_value=2016, max_value=2026, value=2026, step=1, key="end_year")
            
        st.markdown('<hr style="border-color:rgba(255,255,255,0.07);margin:12px 0;">', unsafe_allow_html=True)
        
        st.markdown("""
        <p class="sidebar-section-label">⏱️ Zaman Çözünürlüğü</p>
        """, unsafe_allow_html=True)
        
        temporal_resolution = st.selectbox(
            "Çözünürlük",
            ["15 Günlük Periyotlar", "Aylık Periyotlar", "Ham Gözlemler (Günlük)"],
            key="temporal_resolution",
            label_visibility="collapsed"
        )
        
    st.markdown('<hr style="border-color:rgba(255,255,255,0.07);margin:12px 0;">', unsafe_allow_html=True)
    
    # ─── İndeks Seçimi ───
    st.markdown("""
    <p class="sidebar-section-label">🔬 Spektral İndeks</p>
    """, unsafe_allow_html=True)
    
    selected_index = st.selectbox(
        "İndeks",
        ["NDVI", "NDWI", "SAVI", "EVI"],
        key="selected_index",
        label_visibility="collapsed"
    )
    
    # ─── Plan Badge ───
    st.markdown('<br>', unsafe_allow_html=True)
    st.markdown("""
    <div class="plan-badge">
        <span class="plan-badge-label">Aktif Plan</span>
        <span class="plan-badge-value">✨ Enterprise</span>
        <span class="plan-badge-version">v2.0 · Sentinel-2 L2A</span>
    </div>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
#  TOP NAVIGATION BAR
# ═════════════════════════════════════════════════════════════
mode_raw = st.session_state.get("analysis_mode")
if mode_raw == "Hızlı Yerel Gözlem (Mevsimlik)":
    mode_label = "Hızlı Analiz"
elif mode_raw == "🛸 Drone Analiz Stüdyosu (WebODM)":
    mode_label = "Drone Stüdyosu"
else:
    mode_label = "Veri Fabrikası"

st.markdown(f"""
<div class="saas-topbar">
    <div class="saas-topbar-left">
        <div class="saas-topbar-logo">
            <span class="logo-dot"></span> GEO-AGRI
        </div>
        <div class="saas-topbar-sep"></div>
        <div class="saas-breadcrumb">
            Dashboard <span style="margin: 0 4px;">›</span> 
            <span class="crumb-active">{mode_label}</span>
        </div>
    </div>
    <div class="saas-topbar-right">
        <span class="status-dot"></span>
        <span class="status-label">Sistem Aktif</span>
        <span class="saas-badge">Enterprise</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
#  QUICK START — Geolocation & One-Click Dataset Generator
# ═════════════════════════════════════════════════════════════
# GPS HTML button
gps_button_html = """
<button id="gps-btn" style="
    width: 100%;
    padding: 12px 16px;
    background: linear-gradient(135deg, #10B981 0%, #059669 100%);
    color: white;
    border: none;
    border-radius: 8px;
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    box-shadow: 0 4px 6px -1px rgba(16, 185, 129, 0.2);
    transition: all 0.2s ease;
">
    📍 Cihaz Konumunu Al (GPS)
</button>
<script>
document.getElementById('gps-btn').addEventListener('click', function() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function(position) {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;
            const parentUrl = new URL(window.parent.location.href);
            parentUrl.searchParams.set("gps_lat", lat);
            parentUrl.searchParams.set("gps_lon", lon);
            window.parent.location.href = parentUrl.href;
        }, function(err) {
            alert("Konum alınamadı: " + err.message);
        });
    } else {
        alert("Tarayıcınız konum bilgisini desteklemiyor.");
    }
});
</script>
"""

st.markdown("""
<div class="geo-card" style="margin-bottom: 24px;">
    <div class="geo-card-title">⚡ Hızlı Başlangıç: Tek Tıkla Konum Analizi & ML Veri Seti</div>
    <div class="geo-card-desc">Enlem/Boylam girin veya cihazınızın GPS'ini alın. Tek tıkla uydu verilerini, zaman tüneli videosunu ve derin öğrenmeye hazır ML veri setini oluşturun.</div>
""", unsafe_allow_html=True)

col_quick1, col_quick2, col_quick3 = st.columns([1, 1, 2])
with col_quick1:
    quick_lat = st.number_input("Enlem (Lat)", value=st.session_state.get("gps_lat_val", 37.6432), format="%.6f", key="quick_lat_input")
with col_quick2:
    quick_lon = st.number_input("Boylam (Lon)", value=st.session_state.get("gps_lon_val", 30.1345), format="%.6f", key="quick_lon_input")
with col_quick3:
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    import streamlit.components.v1 as components
    components.html(gps_button_html, height=48)

btn_one_click = st.button("⚡ Hızlı Analiz Et & Veri Seti Çıkar", type="primary", use_container_width=True, key="quick_start_btn")

if btn_one_click:
    with st.status("Uçtan Uca Hızlı Pipeline Çalıştırılıyor...", expanded=True) as status_box:
        try:
            import time
            from shapely.geometry import box
            
            # 1. Resmi TKGM Kadastro API'sinden sorgula, bulamazsan tampon oluştur
            status_box.update(label="1/5 — Resmi kadastro sorgusu yapılıyor...", state="running")
            from src.tkgm.megsis_client import MegsisClient
            
            megsis = MegsisClient()
            try:
                parcel_geojson = megsis.get_parcel_by_coordinates(quick_lat, quick_lon)
                active_geom = shape(parcel_geojson["geometry"])
                
                st.session_state.active_geometry = active_geom
                st.session_state.active_geojson = parcel_geojson
                st.session_state.tkgm_properties = parcel_geojson["properties"]
                st.session_state.field_source = "TKGM"
                status_box.write("✅ Resmi kadastro parseli bulundu!")
            except Exception as e:
                logger.warning(f"Resmi parsel bulunamadı, tampon bölgeye geçiliyor: {e}")
                status_box.write("⚠️ Bu koordinat için resmi kadastro parseli bulunamadı. Tampon bölge oluşturuluyor...")
                
                buffer_deg = 0.0006
                bbox_geom = box(quick_lon - buffer_deg, quick_lat - buffer_deg, quick_lon + buffer_deg, quick_lat + buffer_deg)
                
                st.session_state.active_geometry = bbox_geom
                st.session_state.active_geojson = {
                    "type": "Feature",
                    "geometry": mapping(bbox_geom),
                    "properties": {}
                }
                st.session_state.field_source = "One-Click Quick Start"
                st.session_state.tkgm_properties = {
                    "ilAd": "Hızlı Konum (Tampon)",
                    "ilceAd": "-",
                    "mahalleAd": "-",
                    "adaNo": "-",
                    "parselNo": "-",
                    "alan": f"{bbox_geom.area * 1e8:.2f}",
                    "nitelik": "Hızlı Konum Analizi"
                }
            
            bbox = st.session_state.active_geometry
            
            # 2. Sentinel-2 L2A uydu verileri
            status_box.update(label="2/5 — Sentinel-2 L2A uydu verileri indiriliyor...", state="running")
            from src.satellite.stac_client import StacClient
            from src.satellite.bands_loader import load_and_mask_bands
            from src.dataset.ndvi import calculate_ndvi, generate_field_average_df
            
            stac = StacClient()
            items = stac.search_sentinel_data(
                geometry_wgs84=bbox,
                start_date="2024-03-01",
                end_date="2024-08-31",
                max_cloud_cover=30.0
            )
            
            if not items:
                raise Exception("Bu koordinat etrafında son 6 ayda bulutsuz uydu görüntüsü bulunamadı.")
                
            processed_data = []
            best_items = sorted(items, key=lambda x: x.properties.get("eo:cloud_cover", 100.0))[:8]
            
            for idx, item in enumerate(best_items):
                status_box.update(label=f"2/5 — Görüntü {idx+1}/{len(best_items)} indiriliyor...", state="running")
                loaded = load_and_mask_bands(item, bbox, max_field_cloud_percent=100.0)
                if loaded:
                    processed_data.append({
                        "date": item.properties.get("datetime", "")[:10],
                        "cloud_percent": loaded["cloud_percent"],
                        "bands": loaded
                    })
                    
            if not processed_data:
                raise Exception("Uydu verileri yüklenemedi.")
                
            st.session_state.processed_data = processed_data
            df_avg = generate_field_average_df(processed_data)
            st.session_state.df_avg = df_avg
            st.session_state.df_avg_interp = interpolate_ndvi_series(df_avg)
            
            # 3. ML Veri Seti oluştur
            status_box.update(label="3/5 — ML-Ready veri seti (NPY & JSON) üretiliyor...", state="running")
            from src.dataset.ml_generator import MLDatasetGenerator, DatasetConfig
            ml_config = DatasetConfig(
                patch_size=32,
                stride=16,
                normalization="minmax",
                aug_flip=True,
                aug_rotate=True
            )
            gen = MLDatasetGenerator(ml_config)
            dataset = gen.generate_from_processed(processed_data)
            st.session_state.ml_dataset_seas = dataset
            st.session_state.ml_gen_seas_obj = gen
            
            # 4. GEE / Mock Timelapse Video & Fotos
            status_box.update(label="4/5 — Büyüme timelapse videosu ve fotoğrafları hazırlanıyor...", state="running")
            from src.satellite.gee_timelapse import GEETimelapseEngine, convert_gif_to_mp4, extract_gif_frames_to_zip
            gee_engine = GEETimelapseEngine()
            
            ts_int = int(time.time())
            out_path_gif = f"/tmp/gee_timelapse_quick_{ts_int}.gif"
            out_path_mp4 = f"/tmp/gee_timelapse_quick_{ts_int}.mp4"
            out_path_zip = f"/tmp/gee_timelapse_quick_{ts_int}_fotos.zip"
            
            gif_result = gee_engine.create_timelapse(
                geometry_geojson=st.session_state.active_geojson,
                out_gif_path=out_path_gif,
                start_year=2023,
                end_year=2024,
                start_date="03-01",
                end_date="10-31",
                band_mode="NDVI",
                fps=4
            )
            
            mp4_result = convert_gif_to_mp4(gif_result, out_path_mp4, fps=4)
            zip_result = extract_gif_frames_to_zip(gif_result, out_path_zip)
            
            st.session_state["gee_gif_path_seasonal"] = gif_result
            st.session_state["gee_mp4_path_seasonal"] = mp4_result
            st.session_state["gee_zip_path_seasonal"] = zip_result
            
            # 5. Sonuçlar
            status_box.update(label="5/5 — Sonuçlar derleniyor...", state="complete")
            st.session_state.analysis_mode = "Hızlı Yerel Gözlem (Mevsimlik)"
            st.success("🎉 Tek Tıkla Analiz ve Veri Seti Başarıyla Oluşturuldu!")
            st.rerun()
            
        except Exception as e:
            st.error(f"Hızlı Analiz Hatası: {e}")
            status_box.update(label="Hata Oluştu", state="error")

st.markdown("</div>", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
#  MAIN DASHBOARD — Grid Layout
# ═════════════════════════════════════════════════════════════
col_left, col_right = st.columns([1, 2])

with col_left:
    st.markdown("""
    <div class="geo-card" style="padding-bottom: 8px !important;">
        <div class="geo-card-title">🏛️ Kadastro Sorgu</div>
    """, unsafe_allow_html=True)
    render_tkgm_selectors()
    st.markdown("</div>", unsafe_allow_html=True)

with col_right:
    st.markdown("""
    <div class="geo-card" style="padding-bottom: 8px !important;">
        <div class="geo-card-title">🗺️ Alan Belirleme</div>
    """, unsafe_allow_html=True)
    render_folium_map()
    st.markdown("</div>", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
#  FIELD METRICS & ANALYSIS TRIGGER
# ═════════════════════════════════════════════════════════════
if "active_geometry" in st.session_state:
    geom = st.session_state.active_geometry
    
    # Hektar hesapla
    try:
        area_ha = get_geometry_area_hectares(geom)
        st.session_state.area_ha = area_ha
    except Exception:
        st.session_state.area_ha = 0.0
        
    # KPI Strip
    st.markdown("""
    <div class="geo-card">
        <div class="geo-card-title">📊 Seçili Alan Özeti</div>
    """, unsafe_allow_html=True)
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric(
            label="Alan (Hektar)", 
            value=f"{st.session_state.area_ha:.3f}",
            delta=f"{st.session_state.area_ha * 10.0:.1f} Dönüm"
        )
    with col_m2:
        centroid = geom.centroid
        st.metric(label="Enlem", value=f"{centroid.y:.5f}°")
    with col_m3:
        st.metric(label="Boylam", value=f"{centroid.x:.5f}°")
    with col_m4:
        source_str = "TKGM API" if st.session_state.get("field_source") == "TKGM" else "Manuel Çizim"
        st.metric(label="Kaynak", value=source_str)
        
    # Analiz Butonu
    st.markdown("<br>", unsafe_allow_html=True)
    btn_analiz = st.button("🛰️ Analizi Başlat", type="primary", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    # ═════════════════════════════════════════════════════════
    #  ANALYSIS ENGINE
    # ═════════════════════════════════════════════════════════
    if btn_analiz:
        if st.session_state.get("analysis_mode") == "Dağıtık Veri Fabrikası (10 Yıllık)":
            # ─── Distributed Factory ───
            with st.status("Veri Fabrikası Çalışıyor...", expanded=True) as status_box:
                try:
                    import time
                    
                    # Step 1: Register
                    status_box.update(label="1/3 — Tarla kaydediliyor...", state="running")
                    
                    geom_geojson = st.session_state.active_geojson
                    geometry_data = geom_geojson.get("geometry", geom_geojson)
                        
                    payload = {
                        "user_id": "yasinkaya",
                        "name": st.session_state.tkgm_properties.get("nitelik", "Tarla"),
                        "geometry": geometry_data
                    }
                    
                    resp = requests.post("http://localhost:8000/api/fields/register", json=payload)
                    if resp.status_code != 201:
                        raise Exception(f"Alan kaydı başarısız: {resp.text}")
                    
                    reg_data = resp.json()
                    field_id = reg_data["field_id"]
                    st.session_state.registered_field_id = field_id
                    status_box.write(f"✅ Tarla kaydedildi — `{field_id}`")
                    
                    # Step 2: Trigger
                    status_box.update(label="2/3 — Celery görevi tetikleniyor...", state="running")
                    temp_res = st.session_state.get("temporal_resolution", "15 Günlük Periyotlar")
                    s_yr = st.session_state.get("start_year", 2016)
                    e_yr = st.session_state.get("end_year", 2026)
                    tr_quoted = requests.utils.quote(temp_res)
                    trigger_url = f"http://localhost:8000/api/tasks/trigger/{field_id}?start_year={int(s_yr)}&end_year={int(e_yr)}&temporal_resolution={tr_quoted}"
                    resp_trig = requests.post(trigger_url)
                    if resp_trig.status_code != 202:
                        raise Exception(f"Görev tetiklenemedi: {resp_trig.text}")
                        
                    trig_data = resp_trig.json()
                    task_id = trig_data["task_id"]
                    st.session_state.celery_task_id = task_id
                    status_box.write(f"🚀 Görev kuyruğa eklendi — `{task_id}`")
                    
                    # Step 3: Poll
                    status_box.update(label="3/3 — Uydu görüntüleri işleniyor...", state="running")
                    
                    progress_bar = st.progress(0)
                    progress_text = st.empty()
                    
                    # Shimmer loading
                    loading_placeholder = st.empty()
                    loading_placeholder.markdown("""
                    <div class="shimmer-box">
                        <span class="shimmer-icon">🛰️</span>
                        <div class="shimmer-title">Dağıtık İşçiler Çalışıyor</div>
                        <div class="shimmer-subtitle">Yıllık uydu küpleri oluşturuluyor...</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    while True:
                        status_resp = requests.get(f"http://localhost:8000/api/tasks/status/{task_id}")
                        if status_resp.status_code != 200:
                            raise Exception(f"Durum sorgulanamadı: {status_resp.text}")
                            
                        status_data = status_resp.json()
                        task_status = status_data["status"]
                        
                        if task_status == "PROGRESS":
                            details = status_data.get("progress_details", {})
                            prog_val = details.get("progress", 0) / 100.0
                            current_year = details.get("current_year", "")
                            msg = details.get("status_message", "")
                            progress_bar.progress(prog_val)
                            progress_text.markdown(
                                f"⏳ **{current_year}** · %{int(prog_val*100)} · <span style='color:#94A3B8; font-size:12px;'>{msg}</span>",
                                unsafe_allow_html=True
                            )
                        elif task_status == "SUCCESS":
                            progress_bar.progress(1.0)
                            progress_text.markdown("✅ **Tamamlandı**")
                            loading_placeholder.empty()
                            status_box.update(label="Analiz Tamamlandı", state="complete")
                            
                            st.session_state.factory_result = status_data["result"]
                            st.rerun()
                            break
                        elif task_status == "FAILURE":
                            loading_placeholder.empty()
                            err_msg = status_data.get("error", "Bilinmeyen hata")
                            status_box.update(label="Görev Başarısız", state="error")
                            raise Exception(f"Celery hatası: {err_msg}")
                        elif task_status == "PENDING":
                            progress_text.markdown("⏳ Kuyrukta bekleniyor...")
                        elif task_status == "STARTED":
                            progress_text.markdown("🚀 Görev başladı...")
                            
                        time.sleep(2)
                        
                except Exception as e:
                    st.markdown(f"""
                    <div class="saas-error">
                        <span style="font-size: 18px;">⚠️</span>
                        <div>
                            <strong style="display:block; font-weight:700; color: #B91C1C;">Veri Fabrikası Hatası</strong>
                            <span style="font-size: 13px; color: #DC2626;">{str(e)}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    status_box.update(label="Analiz Başarısız", state="error")
        else:
            # ─── Local / Seasonal Analysis ───
            stac_client = None
            try:
                if "stac_client" not in st.session_state:
                    with st.spinner("STAC kataloğuna bağlanılıyor..."):
                        st.session_state.stac_client = StacClient()
                stac_client = st.session_state.stac_client
            except Exception as e:
                st.markdown(f"""
                <div class="saas-error">
                    <span style="font-size: 18px;">⚠️</span>
                    <div>
                        <strong style="display:block; font-weight:700; color: #B91C1C;">STAC Bağlantı Hatası</strong>
                        <span style="font-size: 13px; color: #DC2626;">{str(e)}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
            if stac_client is not None:
                start_dt = st.session_state.get("start_date", pd.to_datetime("2024-03-01"))
                end_dt = st.session_state.get("end_date", pd.to_datetime("2024-10-31"))
                start_str = start_dt.strftime("%Y-%m-%d")
                end_str = end_dt.strftime("%Y-%m-%d")
                
                # Loading indicator
                loading_placeholder = st.empty()
                loading_placeholder.markdown("""
                <div class="shimmer-box">
                    <span class="shimmer-icon">🛰️</span>
                    <div class="shimmer-title">Sentinel-2 Taraması</div>
                    <div class="shimmer-subtitle">Planetary Computer üzerinden COG bantları taranıyor...</div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.status("Görüntü İşleme Motoru", expanded=True) as status_box:
                    try:
                        status_box.update(label="1/3 — Uydu görüntüleri aranıyor...", state="running")
                        items = stac_client.search_sentinel_data(
                            geometry_wgs84=geom,
                            start_date=start_str,
                            end_date=end_str,
                            max_cloud_cover=max_cloud_cover
                        )
                        
                        if not items:
                            st.warning("Seçilen aralıkta uydu görüntüsü bulunamadı.")
                            status_box.update(label="Veri Bulunamadı", state="error")
                            loading_placeholder.empty()
                        else:
                            status_box.update(label=f"2/3 — {len(items)} görüntü bulundu, bantlar yükleniyor...", state="running")
                            
                            processed_data = []
                            progress_bar = st.progress(0)
                            
                            for idx, item in enumerate(items):
                                date_str = item.properties.get("datetime", "")[:10]
                                progress_bar.progress((idx + 1) / len(items))
                                
                                status_box.write(f"⏳ [{date_str}] İndiriliyor...")
                                
                                loaded = load_and_mask_bands(
                                    item=item,
                                    geometry_wgs84=geom,
                                    max_field_cloud_percent=max_field_cloud_percent
                                )
                                
                                if loaded is not None:
                                    ndvi = calculate_ndvi(loaded["red"], loaded["nir"])
                                    loaded["ndvi"] = ndvi
                                    
                                    processed_data.append({
                                        "date": date_str,
                                        "cloud_percent": loaded["cloud_percent"],
                                        "bands": loaded
                                    })
                                    status_box.write(f"✅ [{date_str}] Bulut: {loaded['cloud_percent']:.1f}%")
                                else:
                                    status_box.write(f"❌ [{date_str}] Atlandı")
                                    
                            progress_bar.empty()
                            loading_placeholder.empty()
                            
                            if not processed_data:
                                st.warning("Tüm görüntüler elenmiştir. Bulut toleransını artırın.")
                                status_box.update(label="Veri Yetersiz", state="error")
                            else:
                                status_box.update(label="3/3 — Sonuçlar derleniyor...", state="running")
                                st.session_state.processed_data = processed_data
                                
                                df_avg = generate_field_average_df(processed_data)
                                st.session_state.df_avg = df_avg
                                
                                if interpolate_empty:
                                    st.session_state.df_avg_interp = interpolate_ndvi_series(df_avg)
                                else:
                                    st.session_state.df_avg_interp = None
                                    
                                status_box.update(label="Analiz Tamamlandı", state="complete")
                                st.rerun()
                                
                    except Exception as e:
                        loading_placeholder.empty()
                        st.markdown(f"""
                        <div class="saas-error">
                            <span style="font-size: 18px;">⚠️</span>
                            <div>
                                <strong style="display:block; font-weight:700; color: #B91C1C;">Analiz Hatası</strong>
                                <span style="font-size: 13px; color: #DC2626;">{str(e)}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        status_box.update(label="Hata Oluştu", state="error")

else:
    # ─── Empty State ───
    st.markdown("""
    <div class="empty-state">
        <span class="empty-state-icon">🛰️</span>
        <div class="empty-state-title">Analiz Alanı Belirlenmedi</div>
        <div class="empty-state-desc">
            Başlamak için harita üzerinden tarla sınırlarını çizin veya sol paneldeki kadastro sorgusunu kullanarak parseli otomatik yükleyin.
        </div>
    </div>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
#  RESULTS — Distributed Factory (10-Year)
# ═════════════════════════════════════════════════════════════
if st.session_state.get("analysis_mode") == "Dağıtık Veri Fabrikası (10 Yıllık)" and "factory_result" in st.session_state:
    
    # Section header
    st.markdown("""
    <div class="section-header">
        <div class="section-header-icon">📈</div>
        <div class="section-header-text">
            <h2>Analiz Sonuçları</h2>
            <span>10 yıllık tarihsel veri fabrikası çıktıları</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    selected_index = st.session_state.get("selected_index", "NDVI")
    
    result_data = st.session_state.factory_result
    field_id = result_data["field_id"]
    trends = result_data["trends"]
    cube_shape = result_data["cube_shape"]
    matrix_path = result_data["matrix_path"]
    
    cube = np.load(matrix_path) if os.path.exists(matrix_path) else None
    weight_path = os.path.join(os.path.dirname(matrix_path), "weight_mask.npy")
    weight_mask = np.load(weight_path) if os.path.exists(weight_path) else None
    dates_dict = result_data.get("dates", {})
    
    # ─── Cube index compute helpers ───
    def compute_cube_index(cube: np.ndarray, index_name: str) -> np.ndarray:
        blue = cube[:, :, 0, :, :]
        green = cube[:, :, 1, :, :]
        red = cube[:, :, 2, :, :]
        nir = cube[:, :, 3, :, :]
        
        if index_name == "NDVI":
            return calculate_ndvi(red, nir)
        elif index_name == "NDWI":
            return calculate_ndwi(green, nir)
        elif index_name == "SAVI":
            return calculate_savi(red, nir)
        elif index_name == "EVI":
            return calculate_evi(blue, red, nir)
        else:
            raise ValueError(f"Bilinmeyen indeks: {index_name}")

    def compute_cube_scalar_trends(index_cube: np.ndarray, weight_mask: np.ndarray) -> dict:
        trends_dict = {}
        N_years, TimeSteps = index_cube.shape[:2]
        for y in range(N_years):
            trends_dict[y] = []
            for t in range(TimeSteps):
                slice_data = index_cube[y, t]
                field_pixels = slice_data[weight_mask > 0]
                field_pixels = field_pixels[~np.isnan(field_pixels)]
                if len(field_pixels) > 0:
                    mean_val = float(np.mean(field_pixels))
                    trends_dict[y].append(0.0 if np.isnan(mean_val) else mean_val)
                else:
                    trends_dict[y].append(0.0)
        return trends_dict

    if cube is not None and weight_mask is not None:
        index_cube = compute_cube_index(cube, selected_index)
        dynamic_trends_dict = compute_cube_scalar_trends(index_cube, weight_mask)
    else:
        dynamic_trends_dict = {i: trends[str(year)] for i, year in enumerate(sorted([int(y) for y in trends.keys()]))}
        index_cube = None
        
    flat_trends = []
    flat_dates = []
    sorted_years = sorted([int(y) for y in trends.keys()])
    
    for y_idx, year in enumerate(sorted_years):
        year_trends = dynamic_trends_dict[y_idx]
        year_dates = dates_dict.get(str(year), [])
        if len(year_dates) != len(year_trends):
            year_dates = [pd.to_datetime(t).strftime("%Y-%m-%d") for t in pd.date_range(start=f"{year}-03-01", end=f"{year}-08-31", periods=len(year_trends))]
        for d, v in zip(year_dates, year_trends):
            flat_dates.append(pd.to_datetime(d))
            flat_trends.append(v)
            
    df_trends = pd.DataFrame({"Tarih": flat_dates, "Değer": flat_trends})
    
    # ─── KPI Strip ───
    st.markdown("""<div class="geo-card">""", unsafe_allow_html=True)
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    
    with col_k1:
        max_val = max(flat_trends) if flat_trends else 0
        max_idx = flat_trends.index(max_val) if flat_trends else 0
        st.metric(
            label=f"Maks. {selected_index}",
            value=f"{max_val:.3f}",
            delta=f"{flat_dates[max_idx].strftime('%Y-%m-%d')}" if flat_dates else ""
        )
    with col_k2:
        min_val = min([v for v in flat_trends if v > -0.99] or [0.0])
        min_idx = flat_trends.index(min_val) if min_val in flat_trends else 0
        st.metric(
            label=f"Min. {selected_index}",
            value=f"{min_val:.3f}",
            delta=f"{flat_dates[min_idx].strftime('%Y-%m-%d')}" if flat_dates else ""
        )
    with col_k3:
        avg_all = np.mean([v for v in flat_trends if not np.isnan(v)] or [0.0])
        st.metric(label=f"Ortalama {selected_index}", value=f"{avg_all:.3f}")
    with col_k4:
        st.metric(label="Veri Noktası", value=f"{len(flat_trends)}")
    st.markdown("""</div>""", unsafe_allow_html=True)
    
    # ─── Tabs ───
    tab_series, tab_maps, tab_pheno, tab_lab, tab_gee, tab_uav, tab_fly, tab_terrain, tab_ml, tab_download = st.tabs([
        f"📊 Zaman Serisi", 
        f"🖼️ Uzamsal Önizleme",
        "🌱 Fenoloji",
        "🔬 Filtre Lab",
        "🛰️ Zaman Tüneli (GEE)",
        "🛸 3D Drone Sim",
        "🚁 Canlı Drone Flyover",
        "🌍 3D GEE Video",
        "🧠 ML Dataset",
        "💾 Ham Veri"
    ])
    
    # ─── TAB 1: Time Series ───
    with tab_series:
        st.markdown(f"""
        <div class="geo-card">
            <div class="geo-card-title">📈 {selected_index} Zaman Serisi ({min(sorted_years)}–{max(sorted_years)})</div>
        """, unsafe_allow_html=True)
        
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_trends["Tarih"],
            y=df_trends["Değer"],
            mode="lines+markers",
            name=f"{selected_index}",
            line=dict(color="#10B981", width=2),
            fill="tozeroy",
            fillcolor="rgba(16,185,129,0.06)",
            marker=dict(size=3, color="#047857"),
            hovertemplate="<b>%{x|%d %b %Y}</b><br>" + f"{selected_index}: " + "%{y:.3f}<extra></extra>"
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", color="#94A3B8", size=11),
            xaxis=dict(
                gridcolor="rgba(255,255,255,0.04)",
                title="", zeroline=False,
                tickfont=dict(size=10, color="#475569"),
                linecolor="rgba(255,255,255,0.08)",
            ),
            yaxis=dict(
                gridcolor="rgba(255,255,255,0.04)",
                title=f"{selected_index}",
                range=[-0.1, 1.0],
                tickfont=dict(size=10, color="#475569"),
                titlefont=dict(size=11, color="#64748B"),
                zeroline=False,
                linecolor="rgba(255,255,255,0.08)",
            ),
            margin=dict(l=45, r=20, t=16, b=35),
            height=360,
            hovermode="x unified",
            hoverlabel=dict(
                bgcolor="#1A2035",
                bordercolor="#1F2740",
                font=dict(size=12, color="#E2E8F0", family="Inter"),
            ),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
    # ─── TAB 2: Spatial Preview ───
    with tab_maps:
        st.markdown(f"""
        <div class="geo-card">
            <div class="geo-card-title">🖼️ Uzamsal {selected_index} Haritası</div>
        """, unsafe_allow_html=True)
        
        if cube is not None:
            try:
                col_sel1, col_sel2 = st.columns(2)
                with col_sel1:
                    sel_year = st.selectbox("Yıl", sorted_years, key="factory_sel_year")
                
                year_idx = sorted_years.index(sel_year)
                year_dates = dates_dict.get(str(sel_year), [])
                if len(year_dates) != cube.shape[1]:
                    year_dates = [pd.to_datetime(t).strftime("%Y-%m-%d") for t in pd.date_range(start=f"{sel_year}-03-01", end=f"{sel_year}-08-31", periods=cube.shape[1])]
                
                with col_sel2:
                    sel_step_idx = st.slider("Adım", 0, len(year_dates) - 1, 0, key="factory_sel_step")
                    st.caption(f"📅 {year_dates[sel_step_idx]}")
                
                matrix_slice = index_cube[year_idx, sel_step_idx]
                
                col_img_left, col_img_right = st.columns([2, 1])
                with col_img_left:
                    fig_ndvi, ax_ndvi = plt.subplots(figsize=(6, 5))
                    fig_ndvi.patch.set_facecolor('none')
                    ax_ndvi.set_facecolor('none')
                    im = ax_ndvi.imshow(matrix_slice, cmap="RdYlGn", vmin=-0.1, vmax=0.9)
                    ax_ndvi.axis("off")
                    cbar = fig_ndvi.colorbar(im, ax=ax_ndvi, orientation='vertical', pad=0.05, shrink=0.8)
                    cbar.ax.tick_params(labelsize=8, colors='#64748B')
                    cbar.set_label(selected_index, color='#64748B', size=10)
                    plt.tight_layout()
                    st.pyplot(fig_ndvi)
                    plt.close(fig_ndvi)
                with col_img_right:
                    fig_hist = plot_pixel_distribution(matrix_slice, f"{sel_year} — {year_dates[sel_step_idx]}")
                    st.plotly_chart(fig_hist, use_container_width=True)
            except Exception as e:
                st.error(f"Önizleme hatası: {e}")
        else:
            st.warning("Veri küpü bulunamadı.")
            
        st.markdown("</div>", unsafe_allow_html=True)
        
    # ─── TAB 3: Filter Lab ───
    with tab_lab:
        st.markdown("""
        <div class="geo-card">
            <div class="geo-card-title">🔬 Görüntü İşleme Laboratuvarı</div>
            <div class="geo-card-desc">Çok bantlı uydu görüntülerine NumPy/SciPy tabanlı filtreler uygulayarak detay analizi yapın.</div>
        """, unsafe_allow_html=True)
        
        if cube is not None:
            available_dates_all = []
            for y_val in sorted_years:
                y_dates = dates_dict.get(str(y_val), [])
                if len(y_dates) != cube.shape[1]:
                    y_dates = [pd.to_datetime(t).strftime("%Y-%m-%d") for t in pd.date_range(start=f"{y_val}-03-01", end=f"{y_val}-08-31", periods=cube.shape[1])]
                available_dates_all.extend(y_dates)
                
            col_l1, col_l2, col_l3 = st.columns(3)
            with col_l1:
                selected_lab_date = st.selectbox("Tarih", available_dates_all, key="lab_date_sel_hist")
            with col_l2:
                lab_vis_type = st.selectbox("Görüntü Modu", ["True Color RGB", "False Color (NIR-R-G)", "NDVI", "NDWI", "SAVI", "EVI"], key="lab_vis_type_hist")
            with col_l3:
                lab_filter_type = st.selectbox("Filtre", ["Filtresiz", "Sobel Kenar", "Gaussian Blur", "Kontrast Germe", "Gri Tonlama"], key="lab_filter_type_hist")
                
            if lab_filter_type == "Gaussian Blur":
                blur_sigma = st.slider("Sigma", 0.5, 3.0, 1.0, 0.1, key="lab_blur_sigma_hist")
                
            # Access bands for chosen date
            def get_bands_historical(date_str):
                year_val = int(date_str[:4])
                y_dates = dates_dict.get(str(year_val), [])
                if len(y_dates) != cube.shape[1]:
                    y_dates = [pd.to_datetime(t).strftime("%Y-%m-%d") for t in pd.date_range(start=f"{year_val}-03-01", end=f"{year_val}-08-31", periods=cube.shape[1])]
                step_val = y_dates.index(date_str) if date_str in y_dates else 0
                y_idx = sorted_years.index(year_val)
                
                slice_val = cube[y_idx, step_val]
                blue_c = slice_val[0]
                green_c = slice_val[1]
                red_c = slice_val[2]
                nir_c = slice_val[3]
                
                return {
                    "blue": blue_c, "green": green_c, "red": red_c, "nir": nir_c,
                    "ndvi": calculate_ndvi(red_c, nir_c),
                    "ndwi": calculate_ndwi(green_c, nir_c),
                    "savi": calculate_savi(red_c, nir_c),
                    "evi": calculate_evi(blue_c, red_c, nir_c)
                }
                
            bands_data = get_bands_historical(selected_lab_date)
            
            is_color = False
            if lab_vis_type == "True Color RGB":
                rgb_c = np.dstack([np.nan_to_num(bands_data["red"]), np.nan_to_num(bands_data["green"]), np.nan_to_num(bands_data["blue"])])
                base_img = np.clip(rgb_c / 3000.0, 0.0, 1.0)
                is_color = True
            elif lab_vis_type == "False Color (NIR-R-G)":
                fcc_c = np.dstack([np.nan_to_num(bands_data["nir"]), np.nan_to_num(bands_data["red"]), np.nan_to_num(bands_data["green"])])
                base_img = np.clip(fcc_c / 3000.0, 0.0, 1.0)
                is_color = True
            else:
                base_img = np.nan_to_num(bands_data[lab_vis_type.lower()])
                is_color = False
                
            if lab_filter_type == "Filtresiz":
                filtered_img = base_img
            elif lab_filter_type == "Sobel Kenar":
                filtered_img = apply_sobel_edge(base_img)
            elif lab_filter_type == "Gaussian Blur":
                filtered_img = apply_gaussian_blur(base_img, sigma=blur_sigma if 'blur_sigma' in locals() else 1.0)
            elif lab_filter_type == "Kontrast Germe":
                filtered_img = apply_contrast_stretching(base_img)
            elif lab_filter_type == "Gri Tonlama":
                filtered_img = apply_grayscale(base_img)
                
            col_img_left, col_img_right = st.columns(2)
            with col_img_left:
                st.markdown(f"**Orijinal** · {lab_vis_type}")
                fig_o, ax_o = plt.subplots(figsize=(6, 5))
                fig_o.patch.set_facecolor('none')
                ax_o.set_facecolor('none')
                if is_color:
                    ax_o.imshow(base_img)
                else:
                    im_o = ax_o.imshow(base_img, cmap="RdYlGn", vmin=-0.1, vmax=0.9)
                    fig_o.colorbar(im_o, ax=ax_o, orientation='vertical', pad=0.05, shrink=0.8).ax.tick_params(labelsize=8, colors='#64748B')
                ax_o.axis("off")
                plt.tight_layout()
                st.pyplot(fig_o)
                plt.close(fig_o)
                
            with col_img_right:
                st.markdown(f"**Filtrelenmiş** · {lab_filter_type}")
                fig_f, ax_f = plt.subplots(figsize=(6, 5))
                fig_f.patch.set_facecolor('none')
                ax_f.set_facecolor('none')
                
                show_gray = not is_color or lab_filter_type == "Gri Tonlama" or (lab_filter_type == "Sobel Kenar" and len(filtered_img.shape) == 2)
                if show_gray:
                    disp_img = apply_grayscale(filtered_img) if len(filtered_img.shape) == 3 else filtered_img
                    im_f = ax_f.imshow(disp_img, cmap="gray")
                    fig_f.colorbar(im_f, ax=ax_f, orientation='vertical', pad=0.05, shrink=0.8).ax.tick_params(labelsize=8, colors='#64748B')
                else:
                    ax_f.imshow(filtered_img)
                ax_f.axis("off")
                plt.tight_layout()
                st.pyplot(fig_f)
                plt.close(fig_f)
                
            # Downloads
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                img_to_save = np.nan_to_num(filtered_img.copy())
                if img_to_save.max() - img_to_save.min() > 1e-5:
                    img_to_save = (img_to_save - img_to_save.min()) / (img_to_save.max() - img_to_save.min())
                img_to_save = (img_to_save * 255).astype(np.uint8)
                
                from PIL import Image
                pil_img = Image.fromarray(img_to_save)
                buf_png = io.BytesIO()
                pil_img.save(buf_png, format="PNG")
                st.download_button(
                    label="🖼️ PNG İndir",
                    data=buf_png.getvalue(),
                    file_name=f"filtered_{lab_vis_type}_{lab_filter_type}_{selected_lab_date}.png",
                    mime="image/png",
                    use_container_width=True
                )
            with col_d2:
                buf_npy = io.BytesIO()
                np.save(buf_npy, filtered_img)
                st.download_button(
                    label="💾 NPY İndir",
                    data=buf_npy.getvalue(),
                    file_name=f"filtered_{lab_vis_type}_{lab_filter_type}_{selected_lab_date}.npy",
                    mime="application/octet-stream",
                    use_container_width=True
                )
        else:
            st.warning("Veri küpü bulunamadı.")
        st.markdown("</div>", unsafe_allow_html=True)
        
    # ─── TAB 4: Data Export ───
    with tab_download:
        st.markdown("""
        <div class="geo-card">
            <div class="geo-card-title">📥 ML Veri Seti İhracatı</div>
            <div class="geo-card-desc">Derin öğrenme modelleriniz için 5D matris küpünü ve ilişkili verileri indirin.</div>
        """, unsafe_allow_html=True)
        
        if os.path.exists(matrix_path):
            st.markdown("""
            <div class="download-card">
                <div class="download-card-icon">📦</div>
                <div class="download-card-info">
                    <div class="download-card-title">5D Çok Bantlı Veri Küpü</div>
                    <div class="download-card-desc">NumPy array · (Yıl, Zaman, 4 Bant, 64, 64)</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            with open(matrix_path, "rb") as f:
                st.download_button(
                    label="📦 Veri Küpünü İndir (.npy)",
                    data=f.read(),
                    file_name=f"cube_5d_{field_id}.npy",
                    mime="application/octet-stream",
                    use_container_width=True
                )
            
        weight_path_dl = os.path.join(os.path.dirname(matrix_path), "weight_mask.npy")
        if os.path.exists(weight_path_dl):
            st.markdown("""
            <div class="download-card">
                <div class="download-card-icon">📐</div>
                <div class="download-card-info">
                    <div class="download-card-title">Ağırlık Maskesi</div>
                    <div class="download-card-desc">Spektral sızıntı ağırlık matrisi</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            with open(weight_path_dl, "rb") as f:
                st.download_button(
                    label="📐 Maske İndir (.npy)",
                    data=f.read(),
                    file_name=f"weight_mask_{field_id}.npy",
                    mime="application/octet-stream",
                    use_container_width=True
                )
            
        st.markdown("""
        <div class="download-card">
            <div class="download-card-icon">📊</div>
            <div class="download-card-info">
                <div class="download-card-title">Skaler Trendler</div>
                <div class="download-card-desc">JSON formatında yıllık NDVI trendleri</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        json_trends = json.dumps(trends, indent=2).encode('utf-8')
        st.download_button(
            label="📊 Trendleri İndir (JSON)",
            data=json_trends,
            file_name=f"trends_{field_id}.json",
            mime="application/json",
            use_container_width=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # ─── TAB: Phenology (Factory) ───
    with tab_pheno:
        st.markdown("""
        <div class="geo-card">
            <div class="geo-card-title">🌱 Fenoloji Analizi</div>
            <div class="geo-card-desc">Vejetasyon büyüme eğrisinden mevsim başlangıcı (SOS), bitiş (EOS), pik NDVI ve büyüme sezonu uzunluğu (GSL) çıkarımı.</div>
        """, unsafe_allow_html=True)

        if cube is not None and weight_mask is not None:
            try:
                # Alan ortalaması üzerinden fenoloji
                avg_ts = np.array(flat_trends, dtype=np.float64)
                date_strs = [d.strftime("%Y-%m-%d") for d in flat_dates]

                smoothed_ts = savitzky_golay_smooth(avg_ts, window_length=min(11, len(avg_ts) | 1), polyorder=2)
                pheno = extract_phenology(avg_ts, dates=date_strs)

                # KPI
                col_p1, col_p2, col_p3, col_p4 = st.columns(4)
                with col_p1:
                    st.metric("Pik NDVI", f"{pheno['peak_ndvi']:.3f}", delta=pheno.get('peak_date', ''))
                with col_p2:
                    st.metric("Mevsim Başlangıcı (SOS)", pheno.get('sos_date', f"Adım {pheno['sos_idx']}"))
                with col_p3:
                    st.metric("Mevsim Bitişi (EOS)", pheno.get('eos_date', f"Adım {pheno['eos_idx']}"))
                with col_p4:
                    st.metric("Büyüme Sezonu", f"{pheno['gsl']} adım")

                st.markdown("<br>", unsafe_allow_html=True)

                # SG smoothed vs raw
                import plotly.graph_objects as go
                fig_pheno = go.Figure()
                fig_pheno.add_trace(go.Scatter(x=list(range(len(avg_ts))), y=avg_ts, mode='markers', name='Ham Gözlem', marker=dict(color='#94A3B8', size=5)))
                fig_pheno.add_trace(go.Scatter(x=list(range(len(smoothed_ts))), y=smoothed_ts, mode='lines', name='SG Düzeltilmiş', line=dict(color='#10B981', width=2.5)))

                # SOS/EOS markers
                fig_pheno.add_vline(x=pheno['sos_idx'], line_dash='dash', line_color='#3B82F6', annotation_text='SOS')
                fig_pheno.add_vline(x=pheno['eos_idx'], line_dash='dash', line_color='#EF4444', annotation_text='EOS')
                fig_pheno.add_vline(x=pheno['peak_idx'], line_dash='dot', line_color='#F59E0B', annotation_text='Peak')

                fig_pheno.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(family='Inter, sans-serif', color='#334155'),
                    xaxis=dict(gridcolor='rgba(0,0,0,0.04)', title='Zaman Adımı'),
                    yaxis=dict(gridcolor='rgba(0,0,0,0.04)', title=f'{selected_index}', range=[-0.2, 1.0]),
                    height=350, margin=dict(l=40, r=20, t=20, b=30),
                    hovermode='x unified',
                    legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0.5, xanchor='center'),
                )
                st.plotly_chart(fig_pheno, use_container_width=True)

                # Ek metrikler
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    st.metric("Amplitude", f"{pheno['amplitude']:.3f}")
                with col_e2:
                    st.metric("Mevsimsel İntegral", f"{pheno['seasonal_integral']:.2f}")

            except Exception as e:
                st.error(f"Fenoloji hesaplama hatası: {e}")
        else:
            st.warning("Fenoloji hesabı için veri küpü gereklidir.")
        st.markdown("</div>", unsafe_allow_html=True)

    # ─── TAB: GEE Timelapse (Factory) ───
    with tab_gee:
        render_gee_timelapse_tab(st.session_state.active_geojson, key_suffix="factory")

    # ─── TAB: 3D Drone Simulator (Factory) ───
    with tab_uav:
        render_uav_simulator_tab(st.session_state.active_geojson, key_suffix="factory")

    # ─── TAB: Cesium Drone Flyover (Factory) ───
    with tab_fly:
        render_drone_flyover_tab(st.session_state.active_geojson, key_suffix="factory")

    # ─── TAB: 3D Google Earth Timelapse (Factory) ───
    with tab_terrain:
        render_3d_terrain_tab(st.session_state.active_geojson, key_suffix="factory")

    # ─── TAB: ML Dataset Studio (Factory) ───
    with tab_ml:
        st.markdown("""
        <div class="geo-card">
            <div class="geo-card-title">🧠 ML Dataset Studio</div>
            <div class="geo-card-desc">CV / CNN / Vision Transformer modelleri için üretim kalitesinde veri seti oluşturun. Patch extraction, multi-band stack, augmentation, train/val/test split.</div>
        """, unsafe_allow_html=True)

        if cube is not None:
            col_cfg1, col_cfg2, col_cfg3 = st.columns(3)
            with col_cfg1:
                ml_patch_size = st.selectbox("Patch Boyutu", [16, 32, 64], index=1, key="ml_patch_hist")
                ml_stride = st.selectbox("Stride (Örtüşme)", [8, 16, 32], index=1, key="ml_stride_hist")
            with col_cfg2:
                ml_norm = st.selectbox("Normalizasyon", ["Min-Max", "Z-Score", "Percentile", "Ham (Yok)"], key="ml_norm_hist")
                norm_map = {"Min-Max": "minmax", "Z-Score": "zscore", "Percentile": "percentile", "Ham (Yok)": "none"}
            with col_cfg3:
                ml_train = st.slider("Train %", 50, 90, 70, 5, key="ml_train_hist")
                ml_val = st.slider("Val %", 5, 30, 15, 5, key="ml_val_hist")

            st.markdown("**Kanallar**")
            ch_col1, ch_col2 = st.columns(2)
            with ch_col1:
                inc_bands = st.checkbox("Spektral Bantlar (B02-B08)", True, key="ml_bands_hist")
                inc_ndvi = st.checkbox("NDVI", True, key="ml_ndvi_hist")
                inc_ndwi = st.checkbox("NDWI", True, key="ml_ndwi_hist")
            with ch_col2:
                inc_savi = st.checkbox("SAVI", True, key="ml_savi_hist")
                inc_evi = st.checkbox("EVI", True, key="ml_evi_hist")

            st.markdown("**Augmentation**")
            aug_col1, aug_col2 = st.columns(2)
            with aug_col1:
                aug_flip = st.checkbox("Flip (Yatay/Dikey)", True, key="ml_flip_hist")
                aug_rotate = st.checkbox("90° Rotasyon", True, key="ml_rot_hist")
            with aug_col2:
                aug_noise = st.checkbox("Gaussian Noise", False, key="ml_noise_hist")
                aug_bright = st.checkbox("Brightness Jitter", False, key="ml_bright_hist")

            st.markdown("**Etiketleme (NDVI Eşikleri)**")
            lbl_col1, lbl_col2, lbl_col3 = st.columns(3)
            with lbl_col1:
                t1 = st.number_input("Çıplak →", value=0.15, step=0.05, key="ml_t1_hist")
            with lbl_col2:
                t2 = st.number_input("Seyrek →", value=0.35, step=0.05, key="ml_t2_hist")
            with lbl_col3:
                t3 = st.number_input("Orta →", value=0.55, step=0.05, key="ml_t3_hist")

            if st.button("🧠 Veri Seti Oluştur", type="primary", use_container_width=True, key="ml_gen_hist"):
                with st.spinner("ML veri seti üretiliyor..."):
                    try:
                        config = DatasetConfig(
                            patch_size=ml_patch_size,
                            stride=ml_stride,
                            include_bands=inc_bands,
                            include_ndvi=inc_ndvi,
                            include_ndwi=inc_ndwi,
                            include_savi=inc_savi,
                            include_evi=inc_evi,
                            normalization=norm_map[ml_norm],
                            aug_flip=aug_flip,
                            aug_rotate=aug_rotate,
                            aug_noise=aug_noise,
                            aug_brightness=aug_bright,
                            train_ratio=ml_train / 100.0,
                            val_ratio=ml_val / 100.0,
                            test_ratio=max(0.05, 1.0 - ml_train/100.0 - ml_val/100.0),
                            label_thresholds=[t1, t2, t3],
                        )
                        gen = MLDatasetGenerator(config)
                        dataset = gen.generate_from_cube(
                            cube, weight_mask, dates_dict, sorted_years
                        )
                        st.session_state.ml_dataset_hist = dataset
                        st.session_state.ml_gen_hist = gen
                    except Exception as e:
                        st.error(f"Veri seti üretim hatası: {e}")

            if "ml_dataset_hist" in st.session_state:
                ds = st.session_state.ml_dataset_hist
                meta = ds["metadata"]
                info = meta["dataset_info"]
                split = meta["split"]

                st.markdown("<br>", unsafe_allow_html=True)
                col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                with col_r1:
                    st.metric("Toplam Patch", f"{info['total_patches']:,}")
                with col_r2:
                    st.metric("Kanal", f"{info['n_channels']}")
                with col_r3:
                    st.metric("Train / Val / Test", f"{split['train']} / {split['val']} / {split['test']}")
                with col_r4:
                    st.metric("Sınıf Sayısı", f"{len(meta['class_distribution'])}")

                # Sınıf dağılımı
                st.markdown("**Sınıf Dağılımı**")
                for cls_name, cnt in meta["class_distribution"].items():
                    pct = cnt / info['total_patches'] * 100
                    st.markdown(f"- **{cls_name}**: {cnt} ({pct:.1f}%)")

                # Patch önizleme (4x4 grid)
                st.markdown("**Örnek Patchler (İlk 16)**")
                n_preview = min(16, len(ds['patches']))
                fig_prev, axes = plt.subplots(2, 8, figsize=(16, 4))
                for idx in range(n_preview):
                    row = idx // 8
                    col_i = idx % 8
                    patch = ds['patches'][idx]
                    # İlk 3 kanal RGB olarak göster (eğer varsa)
                    if patch.shape[0] >= 3:
                        rgb_p = np.transpose(patch[:3], (1, 2, 0))
                        rgb_p = np.clip(rgb_p, 0, 1) if config.normalization != 'none' else np.clip(rgb_p / 3000.0, 0, 1)
                        axes[row, col_i].imshow(rgb_p)
                    else:
                        axes[row, col_i].imshow(patch[0], cmap='RdYlGn')
                    axes[row, col_i].axis('off')
                    axes[row, col_i].set_title(f"L:{ds['labels'][idx]}", fontsize=8, color='#64748B')
                for idx in range(n_preview, 16):
                    axes[idx // 8, idx % 8].axis('off')
                fig_prev.patch.set_facecolor('none')
                plt.tight_layout()
                st.pyplot(fig_prev)
                plt.close(fig_prev)

                # Download ZIP
                gen = st.session_state.ml_gen_hist
                zip_bytes = gen.export_to_zip(ds)
                st.download_button(
                    label="📦 ML Dataset İndir (.zip)",
                    data=zip_bytes,
                    file_name=f"geoagri_ml_dataset_{ml_patch_size}px.zip",
                    mime="application/zip",
                    use_container_width=True
                )
        else:
            st.warning("ML dataset üretimi için veri küpü gereklidir.")
        st.markdown("</div>", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
#  RESULTS — Seasonal / Local Analysis
# ═════════════════════════════════════════════════════════════
elif st.session_state.get("analysis_mode") == "Hızlı Yerel Gözlem (Mevsimlik)" and "processed_data" in st.session_state and st.session_state.processed_data:
    
    # Section header
    st.markdown("""
    <div class="section-header">
        <div class="section-header-icon">📈</div>
        <div class="section-header-text">
            <h2>Analiz Sonuçları</h2>
            <span>Mevsimlik yerel gözlem verileri</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    selected_index = st.session_state.get("selected_index", "NDVI")
    
    processed_data = st.session_state.processed_data
    df_avg = st.session_state.df_avg
    
    # Dynamic interpolation
    if st.session_state.get("interpolate_empty", True):
        try:
            df_avg_interp = interpolate_ndvi_series(df_avg, ndvi_col=f"Mean_{selected_index}")
        except Exception as e:
            logger.warning(f"Enterpolasyon hatası: {e}")
            df_avg_interp = None
    else:
        df_avg_interp = None
    
    # ─── KPI Strip ───
    st.markdown("""<div class="geo-card">""", unsafe_allow_html=True)
    
    mean_col = f"Mean_{selected_index}"
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    
    max_idx = df_avg[mean_col].idxmax()
    max_row = df_avg.loc[max_idx]
    min_idx = df_avg[mean_col].idxmin()
    min_row = df_avg.loc[min_idx]
    avg_all = df_avg[mean_col].mean()
    
    with col_k1:
        st.metric(label=f"Maks. {selected_index}", value=f"{max_row[mean_col]:.3f}", delta=f"{max_row['Date']}")
    with col_k2:
        st.metric(label=f"Min. {selected_index}", value=f"{min_row[mean_col]:.3f}", delta=f"{min_row['Date']}")
    with col_k3:
        st.metric(label=f"Ortalama {selected_index}", value=f"{avg_all:.3f}")
    with col_k4:
        st.metric(label="Gözlem Sayısı", value=f"{len(df_avg)}")
    st.markdown("""</div>""", unsafe_allow_html=True)
        
    # ─── Tabs ───
    tab_series, tab_maps, tab_lab, tab_gee, tab_uav, tab_fly_s, tab_terrain_s, tab_ml, tab_download = st.tabs([
        f"📊 Zaman Serisi", 
        f"🖼️ Tarla Haritaları", 
        "🔬 Filtre Lab",
        "🛰️ Zaman Tüneli (GEE)",
        "🛸 3D Drone Sim",
        "🚁 Canlı Drone Flyover",
        "🌍 3D GEE Video",
        "🧠 ML Dataset",
        "💾 Veri İhracatı"
    ])
    
    # ─── TAB 1: Time Series ───
    with tab_series:
        st.markdown(f"""
        <div class="geo-card">
            <div class="geo-card-title">📈 {selected_index} Zaman Serisi</div>
        """, unsafe_allow_html=True)
        
        fig_series = plot_ndvi_time_series(df_avg, df_avg_interp, index_name=selected_index)
        st.plotly_chart(fig_series, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
    # ─── TAB 2: Spatial Maps ───
    with tab_maps:
        st.markdown("""
        <div class="geo-card">
            <div class="geo-card-title">🖼️ Uzamsal Büyüme Analizi</div>
        """, unsafe_allow_html=True)
        
        available_dates = [entry["date"] for entry in processed_data]
        selected_date = st.selectbox("Tarih", available_dates, key="seasonal_date_sel")
        
        selected_entry = next(entry for entry in processed_data if entry["date"] == selected_date)
        bands = selected_entry["bands"]
        
        col_img_left, col_img_right = st.columns(2)
        
        # RGB
        rgb = np.dstack([bands["red"].values, bands["green"].values, bands["blue"].values])
        rgb = np.clip(rgb / 3000.0, 0, 1)
        
        # Selected index
        from src.dataset.ndvi import calculate_ndvi, calculate_ndwi, calculate_savi, calculate_evi
        if selected_index == "NDVI":
            idx_val = bands["ndvi"].values
        elif selected_index == "NDWI":
            idx_val = calculate_ndwi(bands["green"], bands["nir"]).values
        elif selected_index == "SAVI":
            idx_val = calculate_savi(bands["red"], bands["nir"]).values
        elif selected_index == "EVI":
            idx_val = calculate_evi(bands["blue"], bands["red"], bands["nir"]).values
            
        with col_img_left:
            st.markdown("**RGB Görüntü**")
            fig_rgb, ax_rgb = plt.subplots(figsize=(6, 5))
            fig_rgb.patch.set_facecolor('none')
            ax_rgb.set_facecolor('none')
            ax_rgb.imshow(rgb)
            ax_rgb.axis("off")
            plt.tight_layout()
            st.pyplot(fig_rgb)
            plt.close(fig_rgb)
            
        with col_img_right:
            st.markdown(f"**{selected_index} Haritası**")
            fig_ndvi, ax_ndvi = plt.subplots(figsize=(6, 5))
            fig_ndvi.patch.set_facecolor('none')
            ax_ndvi.set_facecolor('none')
            im = ax_ndvi.imshow(idx_val, cmap="RdYlGn", vmin=-0.1, vmax=0.9)
            ax_ndvi.axis("off")
            cbar = fig_ndvi.colorbar(im, ax=ax_ndvi, orientation='vertical', pad=0.05, shrink=0.8)
            cbar.ax.tick_params(labelsize=8, colors='#64748B')
            cbar.set_label(selected_index, color='#64748B', size=10)
            plt.tight_layout()
            st.pyplot(fig_ndvi)
            plt.close(fig_ndvi)
            
        fig_hist = plot_pixel_distribution(idx_val, selected_date, index_name=selected_index)
        st.plotly_chart(fig_hist, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
    # ─── TAB 3: Filter Lab ───
    with tab_lab:
        st.markdown("""
        <div class="geo-card">
            <div class="geo-card-title">🔬 Görüntü İşleme Laboratuvarı</div>
            <div class="geo-card-desc">Çok bantlı görüntülere filtreler uygulayarak detay analizi yapın.</div>
        """, unsafe_allow_html=True)
        
        col_l1, col_l2, col_l3 = st.columns(3)
        with col_l1:
            selected_lab_date = st.selectbox("Tarih", available_dates, key="lab_date_sel_seas")
        with col_l2:
            lab_vis_type = st.selectbox("Mod", ["True Color RGB", "False Color (NIR-R-G)", "NDVI", "NDWI", "SAVI", "EVI"], key="lab_vis_type_seas")
        with col_l3:
            lab_filter_type = st.selectbox("Filtre", ["Filtresiz", "Sobel Kenar", "Gaussian Blur", "Kontrast Germe", "Gri Tonlama"], key="lab_filter_type_seas")
            
        if lab_filter_type == "Gaussian Blur":
            blur_sigma = st.slider("Sigma", 0.5, 3.0, 1.0, 0.1, key="lab_blur_sigma_seas")
            
        selected_lab_entry = next(entry for entry in processed_data if entry["date"] == selected_lab_date)
        bands_data = selected_lab_entry["bands"]
        
        blue_c = bands_data["blue"].values
        green_c = bands_data["green"].values
        red_c = bands_data["red"].values
        nir_c = bands_data["nir"].values
        
        from src.dataset.ndvi import calculate_ndvi, calculate_ndwi, calculate_savi, calculate_evi
        bands_dict = {
            "blue": blue_c, "green": green_c, "red": red_c, "nir": nir_c,
            "ndvi": bands_data["ndvi"].values,
            "ndwi": calculate_ndwi(green_c, nir_c),
            "savi": calculate_savi(red_c, nir_c),
            "evi": calculate_evi(blue_c, red_c, nir_c)
        }
        
        is_color = False
        if lab_vis_type == "True Color RGB":
            base_img = np.clip(np.dstack([np.nan_to_num(red_c), np.nan_to_num(green_c), np.nan_to_num(blue_c)]) / 3000.0, 0.0, 1.0)
            is_color = True
        elif lab_vis_type == "False Color (NIR-R-G)":
            base_img = np.clip(np.dstack([np.nan_to_num(nir_c), np.nan_to_num(red_c), np.nan_to_num(green_c)]) / 3000.0, 0.0, 1.0)
            is_color = True
        else:
            base_img = np.nan_to_num(bands_dict[lab_vis_type.lower()])
            is_color = False
            
        if lab_filter_type == "Filtresiz":
            filtered_img = base_img
        elif lab_filter_type == "Sobel Kenar":
            filtered_img = apply_sobel_edge(base_img)
        elif lab_filter_type == "Gaussian Blur":
            filtered_img = apply_gaussian_blur(base_img, sigma=blur_sigma if 'blur_sigma' in locals() else 1.0)
        elif lab_filter_type == "Kontrast Germe":
            filtered_img = apply_contrast_stretching(base_img)
        elif lab_filter_type == "Gri Tonlama":
            filtered_img = apply_grayscale(base_img)
            
        col_img_left, col_img_right = st.columns(2)
        with col_img_left:
            st.markdown(f"**Orijinal** · {lab_vis_type}")
            fig_o, ax_o = plt.subplots(figsize=(6, 5))
            fig_o.patch.set_facecolor('none')
            ax_o.set_facecolor('none')
            if is_color:
                ax_o.imshow(base_img)
            else:
                im_o = ax_o.imshow(base_img, cmap="RdYlGn", vmin=-0.1, vmax=0.9)
                fig_o.colorbar(im_o, ax=ax_o, orientation='vertical', pad=0.05, shrink=0.8).ax.tick_params(labelsize=8, colors='#64748B')
            ax_o.axis("off")
            plt.tight_layout()
            st.pyplot(fig_o)
            plt.close(fig_o)
            
        with col_img_right:
            st.markdown(f"**Filtrelenmiş** · {lab_filter_type}")
            fig_f, ax_f = plt.subplots(figsize=(6, 5))
            fig_f.patch.set_facecolor('none')
            ax_f.set_facecolor('none')
            
            show_gray = not is_color or lab_filter_type == "Gri Tonlama" or (lab_filter_type == "Sobel Kenar" and len(filtered_img.shape) == 2)
            if show_gray:
                disp_img = apply_grayscale(filtered_img) if len(filtered_img.shape) == 3 else filtered_img
                im_f = ax_f.imshow(disp_img, cmap="gray")
                fig_f.colorbar(im_f, ax=ax_f, orientation='vertical', pad=0.05, shrink=0.8).ax.tick_params(labelsize=8, colors='#64748B')
            else:
                ax_f.imshow(filtered_img)
            ax_f.axis("off")
            plt.tight_layout()
            st.pyplot(fig_f)
            plt.close(fig_f)
            
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            img_to_save = np.nan_to_num(filtered_img.copy())
            if img_to_save.max() - img_to_save.min() > 1e-5:
                img_to_save = (img_to_save - img_to_save.min()) / (img_to_save.max() - img_to_save.min())
            img_to_save = (img_to_save * 255).astype(np.uint8)
            
            from PIL import Image
            pil_img = Image.fromarray(img_to_save)
            buf_png = io.BytesIO()
            pil_img.save(buf_png, format="PNG")
            st.download_button(
                label="🖼️ PNG İndir",
                data=buf_png.getvalue(),
                file_name=f"filtered_{lab_vis_type}_{lab_filter_type}_{selected_lab_date}.png",
                mime="image/png",
                use_container_width=True
            )
        with col_d2:
            buf_npy = io.BytesIO()
            np.save(buf_npy, filtered_img)
            st.download_button(
                label="💾 NPY İndir",
                data=buf_npy.getvalue(),
                file_name=f"filtered_{lab_vis_type}_{lab_filter_type}_{selected_lab_date}.npy",
                mime="application/octet-stream",
                use_container_width=True
            )
            
        st.markdown("</div>", unsafe_allow_html=True)

    # ─── TAB: GEE Timelapse (Seasonal) ───
    with tab_gee:
        render_gee_timelapse_tab(st.session_state.active_geojson, key_suffix="seasonal")

    # ─── TAB: 3D Drone Simulator (Seasonal) ───
    with tab_uav:
        render_uav_simulator_tab(st.session_state.active_geojson, key_suffix="seasonal")

    # ─── TAB: Cesium Drone Flyover (Seasonal) ───
    with tab_fly_s:
        render_drone_flyover_tab(st.session_state.active_geojson, key_suffix="seasonal")

    # ─── TAB: 3D Google Earth Timelapse (Seasonal) ───
    with tab_terrain_s:
        render_3d_terrain_tab(st.session_state.active_geojson, key_suffix="seasonal")

    # ─── TAB: ML Dataset Studio (Seasonal) ───
    with tab_ml:
        st.markdown("""
        <div class="geo-card">
            <div class="geo-card-title">🧠 ML Dataset Studio</div>
            <div class="geo-card-desc">CV / CNN / Vision Transformer modelleri için üretim kalitesinde veri seti oluşturun. Patch extraction, multi-band stack, augmentation, train/val/test split.</div>
        """, unsafe_allow_html=True)

        if processed_data:
            col_cfg1, col_cfg2, col_cfg3 = st.columns(3)
            with col_cfg1:
                ml_patch_size = st.selectbox("Patch Boyutu", [16, 32, 64], index=1, key="ml_patch_seas")
                ml_stride = st.selectbox("Stride (Örtüşme)", [8, 16, 32], index=1, key="ml_stride_seas")
            with col_cfg2:
                ml_norm = st.selectbox("Normalizasyon", ["Min-Max", "Z-Score", "Percentile", "Ham (Yok)"], key="ml_norm_seas")
                norm_map = {"Min-Max": "minmax", "Z-Score": "zscore", "Percentile": "percentile", "Ham (Yok)": "none"}
            with col_cfg3:
                ml_train = st.slider("Train %", 50, 90, 70, 5, key="ml_train_seas")
                ml_val = st.slider("Val %", 5, 30, 15, 5, key="ml_val_seas")

            st.markdown("**Kanallar**")
            ch_col1, ch_col2 = st.columns(2)
            with ch_col1:
                inc_bands = st.checkbox("Spektral Bantlar (B02-B08)", True, key="ml_bands_seas")
                inc_ndvi = st.checkbox("NDVI", True, key="ml_ndvi_seas")
                inc_ndwi = st.checkbox("NDWI", True, key="ml_ndwi_seas")
            with ch_col2:
                inc_savi = st.checkbox("SAVI", True, key="ml_savi_seas")
                inc_evi = st.checkbox("EVI", True, key="ml_evi_seas")

            st.markdown("**Augmentation**")
            aug_col1, aug_col2 = st.columns(2)
            with aug_col1:
                aug_flip = st.checkbox("Flip (Yatay/Dikey)", True, key="ml_flip_seas")
                aug_rotate = st.checkbox("90° Rotasyon", True, key="ml_rot_seas")
            with aug_col2:
                aug_noise = st.checkbox("Gaussian Noise", False, key="ml_noise_seas")
                aug_bright = st.checkbox("Brightness Jitter", False, key="ml_bright_seas")

            st.markdown("**Etiketleme (NDVI Eşikleri)**")
            lbl_col1, lbl_col2, lbl_col3 = st.columns(3)
            with lbl_col1:
                t1 = st.number_input("Çıplak →", value=0.15, step=0.05, key="ml_t1_seas")
            with lbl_col2:
                t2 = st.number_input("Seyrek →", value=0.35, step=0.05, key="ml_t2_seas")
            with lbl_col3:
                t3 = st.number_input("Orta →", value=0.55, step=0.05, key="ml_t3_seas")

            if st.button("🧠 Veri Seti Oluştur", type="primary", use_container_width=True, key="ml_gen_seas"):
                with st.spinner("ML veri seti üretiliyor..."):
                    try:
                        config = DatasetConfig(
                            patch_size=ml_patch_size,
                            stride=ml_stride,
                            include_bands=inc_bands,
                            include_ndvi=inc_ndvi,
                            include_ndwi=inc_ndwi,
                            include_savi=inc_savi,
                            include_evi=inc_evi,
                            normalization=norm_map[ml_norm],
                            aug_flip=aug_flip,
                            aug_rotate=aug_rotate,
                            aug_noise=aug_noise,
                            aug_brightness=aug_bright,
                            train_ratio=ml_train / 100.0,
                            val_ratio=ml_val / 100.0,
                            test_ratio=max(0.05, 1.0 - ml_train/100.0 - ml_val/100.0),
                            label_thresholds=[t1, t2, t3],
                        )
                        gen = MLDatasetGenerator(config)
                        dataset = gen.generate_from_processed(processed_data)
                        st.session_state.ml_dataset_seas = dataset
                        st.session_state.ml_gen_seas_obj = gen
                    except Exception as e:
                        st.error(f"Veri seti üretim hatası: {e}")

            if "ml_dataset_seas" in st.session_state:
                ds = st.session_state.ml_dataset_seas
                meta = ds["metadata"]
                info = meta["dataset_info"]
                split = meta["split"]

                st.markdown("<br>", unsafe_allow_html=True)
                col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                with col_r1:
                    st.metric("Toplam Patch", f"{info['total_patches']:,}")
                with col_r2:
                    st.metric("Kanal", f"{info['n_channels']}")
                with col_r3:
                    st.metric("Train / Val / Test", f"{split['train']} / {split['val']} / {split['test']}")
                with col_r4:
                    st.metric("Sınıf Sayısı", f"{len(meta['class_distribution'])}")

                # Sınıf dağılımı
                st.markdown("**Sınıf Dağılımı**")
                for cls_name, cnt in meta["class_distribution"].items():
                    pct = cnt / info['total_patches'] * 100
                    st.markdown(f"- **{cls_name}**: {cnt} ({pct:.1f}%)")

                # Patch önizleme (4x4 grid)
                st.markdown("**Örnek Patchler (İlk 16)**")
                n_preview = min(16, len(ds['patches']))
                fig_prev, axes = plt.subplots(2, 8, figsize=(16, 4))
                for idx in range(n_preview):
                    row = idx // 8
                    col_i = idx % 8
                    patch = ds['patches'][idx]
                    # İlk 3 kanal RGB olarak göster (eğer varsa)
                    if patch.shape[0] >= 3:
                        rgb_p = np.transpose(patch[:3], (1, 2, 0))
                        rgb_p = np.clip(rgb_p, 0, 1) if config.normalization != 'none' else np.clip(rgb_p / 3000.0, 0, 1)
                        axes[row, col_i].imshow(rgb_p)
                    else:
                        axes[row, col_i].imshow(patch[0], cmap='RdYlGn')
                    axes[row, col_i].axis('off')
                    axes[row, col_i].set_title(f"L:{ds['labels'][idx]}", fontsize=8, color='#64748B')
                for idx in range(n_preview, 16):
                    axes[idx // 8, idx % 8].axis('off')
                fig_prev.patch.set_facecolor('none')
                plt.tight_layout()
                st.pyplot(fig_prev)
                plt.close(fig_prev)

                # Download ZIP
                gen = st.session_state.ml_gen_seas_obj
                zip_bytes = gen.export_to_zip(ds)
                st.download_button(
                    label="📦 ML Dataset İndir (.zip)",
                    data=zip_bytes,
                    file_name=f"geoagri_ml_dataset_seas_{ml_patch_size}px.zip",
                    mime="application/zip",
                    use_container_width=True
                )
        else:
            st.warning("ML dataset üretimi için işlenmiş veri gereklidir.")
        st.markdown("</div>", unsafe_allow_html=True)

    # ─── TAB 4: Data Export ───
    with tab_download:
        st.markdown("""
        <div class="geo-card">
            <div class="geo-card-title">📥 ML Veri Seti İhracatı</div>
            <div class="geo-card-desc">Zaman serisi ve uzamsal modeller için veri setlerini indirin.</div>
        """, unsafe_allow_html=True)
        
        # CSV - Time series
        st.markdown("""
        <div class="download-card">
            <div class="download-card-icon">📊</div>
            <div class="download-card-info">
                <div class="download-card-title">Zaman Serisi Ortalamaları</div>
                <div class="download-card-desc">CSV · Tarihsel ortalama, min, max spektral indeks değerleri</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        csv_avg = df_avg.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📊 CSV İndir",
            data=csv_avg,
            file_name="tarla_zaman_serisi.csv",
            mime="text/csv",
            use_container_width=True
        )
        
        st.markdown('<hr style="border-color:rgba(255,255,255,0.07);margin:12px 0;">', unsafe_allow_html=True)
        
        # CSV - Pixel level
        st.markdown("""
        <div class="download-card">
            <div class="download-card-icon">📐</div>
            <div class="download-card-info">
                <div class="download-card-title">Piksel Bazlı Detay Tablosu</div>
                <div class="download-card-desc">CSV · Her pikselin enlem, boylam ve spektral değerleri</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.checkbox("Piksel tablosu oluştur (büyük veri seti)", key="pixel_csv_check"):
            with st.spinner("Derleniyor..."):
                df_pixel = generate_pixel_level_df(processed_data)
                csv_pixel = df_pixel.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📐 Piksel CSV İndir",
                    data=csv_pixel,
                    file_name="tarla_piksel_verisi.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                st.dataframe(df_pixel.head(100), use_container_width=True)
                st.caption(f"Önizleme: 100 / {len(df_pixel)} satır")
                
        st.markdown('<hr style="border-color:rgba(255,255,255,0.07);margin:12px 0;">', unsafe_allow_html=True)
        
        # NPZ
        st.markdown("""
        <div class="download-card">
            <div class="download-card-icon">📦</div>
            <div class="download-card-info">
                <div class="download-card-title">3D Uzamsal-Zamansal Veri Küpü</div>
                <div class="download-card-desc">NPZ · (Zaman, Yükseklik, Genişlik) — CNN/ConvLSTM için ideal</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        try:
            npz_data, npz_name = export_to_npz(processed_data)
            st.download_button(
                label="📦 NPZ İndir",
                data=npz_data,
                file_name=npz_name,
                mime="application/octet-stream",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"NPZ hazırlanamadı: {e}")
            
        st.markdown("</div>", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
#  RESULTS — Drone Analysis Studio
# ═════════════════════════════════════════════════════════════
elif st.session_state.get("analysis_mode") == "🛸 Drone Analiz Stüdyosu (WebODM)":
    # Section header
    st.markdown("""
    <div class="section-header">
        <div class="section-header-icon">🛸</div>
        <div class="section-header-text">
            <h2>Drone Analiz Stüdyosu</h2>
            <span>WebODM entegrasyonu ile yüksek çözünürlüklü drone fotogrametrisi ve hassas tarım analizi</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ─── File Upload & Connection Status ───
    st.markdown("""<div class="geo-card">""", unsafe_allow_html=True)
    st.markdown('<div class="geo-card-title">🛸 Fotoğraf Seti Yükle & İşle</div>', unsafe_allow_html=True)
    st.markdown('<div class="geo-card-desc">Drone ile çekilmiş GPS etiketli görüntüleri içeren .zip dosyasını yükleyin.</div>', unsafe_allow_html=True)
    
    # Connection Check
    from src.satellite.odm_client import ODMClient
    from src.dataset.drone_analyzer import DroneAnalyzer
    
    host = st.session_state.get("odm_host_input", "localhost")
    port = st.session_state.get("odm_port_input", 3000)
    is_sim = st.session_state.get("odm_simulated", True)
    
    client = ODMClient(host=host, port=port)
    client.is_simulated = is_sim
    
    connected = client.check_connection()
    if connected:
        node_info = client.get_node_info()
        st.success(f"🟢 WebODM Sunucusuna Bağlanıldı! (Sürüm: {node_info.get('version', 'Bilinmiyor')})")
    else:
        st.error(f"🔴 WebODM Sunucusuna Bağlanılamadı ({host}:{port}). Lütfen Docker container'ınızın çalıştığından emin olun veya simülasyon modunu aktif edin.")
        
    uploaded_zip = st.file_uploader("Görüntü ZIP Dosyası (.zip)", type=["zip"], key="drone_zip_uploader")
    
    # Start button
    btn_col1, btn_col2 = st.columns([1, 4])
    with btn_col1:
        btn_start_odm = st.button("🚀 İşlemeyi Başlat", type="primary", disabled=not (connected and uploaded_zip is not None), use_container_width=True)
    with btn_col2:
        if uploaded_zip is None:
            st.info("💡 İşlemeyi başlatmak için lütfen önce bir ZIP dosyası yükleyin.")
        elif not connected:
            st.warning("⚠️ Sunucu bağlantısı olmadan işlem başlatılamaz. Simülasyon modunu açabilirsiniz.")
            
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Trigger processing
    if btn_start_odm and uploaded_zip is not None:
        with st.status("Fotogrametri Süreci Başlatılıyor...", expanded=True) as status_box:
            try:
                # 1. Görevi oluştur
                status_box.update(label="1/3 — Sunucuya yükleniyor ve görev oluşturuluyor...", state="running")
                zip_bytes = uploaded_zip.read()
                
                # Options mapping
                quality_map = {"Hızlı Önizleme (Düşük)": "low", "Standart (Orta)": "medium", "Yüksek Detay (Premium)": "high"}
                opts = {
                    "dsm": st.session_state.get("odm_dsm_check", True),
                    "orthophoto-resolution": st.session_state.get("odm_res_input", 0.05) * 100, # cm cinsinden
                    "dem-resolution": st.session_state.get("odm_res_input", 0.05) * 100,
                }
                
                task_id = client.create_task_from_zip(zip_bytes, opts)
                st.session_state.odm_task_id = task_id
                status_box.write(f"✅ Görev oluşturuldu! Görev ID: `{task_id}`")
                
                # 2. Döngüsel sorgulama (Poller)
                status_box.update(label="2/3 — Görüntüler işleniyor (Bu işlem zaman alabilir)...", state="running")
                progress_bar = st.progress(0)
                progress_text = st.empty()
                
                # Shimmer loading
                loading_placeholder = st.empty()
                loading_placeholder.markdown("""
                <div class="shimmer-box">
                    <span class="shimmer-icon">🛸</span>
                    <div class="shimmer-title">WebODM Fotogrametri Motoru Çalışıyor</div>
                    <div class="shimmer-subtitle">Fotoğraflar hizalanıyor ve ortofoto dikişi yapılıyor...</div>
                </div>
                """, unsafe_allow_html=True)
                
                import time
                while True:
                    stat = client.get_task_status(task_id)
                    status_str = stat["status"]
                    progress = stat["progress"]
                    
                    progress_bar.progress(progress / 100.0)
                    progress_text.text(f"İlerleme: %{progress} | Durum: {status_str}")
                    
                    if status_str == "COMPLETED":
                        status_box.write("✅ Fotogrametri başarıyla tamamlandı!")
                        break
                    elif status_str in ["FAILED", "CANCELLED"]:
                        raise Exception(f"WebODM Görev Hatası: {stat.get('error', 'Bilinmeyen Hata')}")
                    
                    time.sleep(1.5)
                
                # 3. İndir
                status_box.update(label="3/3 — Çıktılar indiriliyor...", state="running")
                loading_placeholder.empty()
                
                # Çıktı dizini
                output_dir = os.path.join("/tmp/webodm_outputs", task_id)
                assets = client.download_assets(task_id, output_dir)
                
                # Eğer simülasyondaysak mock GeoTIFF dosyalarını oluşturalım
                if is_sim:
                    lat_sim, lon_sim = 37.6432, 30.1345
                    # Aktif geometri varsa onun koordinatlarını kullanalım
                    if "active_geometry" in st.session_state:
                        centroid = st.session_state.active_geometry.centroid
                        lat_sim, lon_sim = centroid.y, centroid.x
                    
                    # Mock oluştur
                    ortho_mock, dsm_mock = DroneAnalyzer.generate_mock_drone_data(output_dir, lat_sim, lon_sim)
                    assets["orthophoto"] = ortho_mock
                    assets["dsm"] = dsm_mock
                
                st.session_state.odm_assets = assets
                status_box.update(label="İşlem Tamamlandı!", state="complete")
                st.success("🎉 Drone verileri başarıyla işlendi ve analiz için hazırlandı!")
                st.rerun()
                
            except Exception as e:
                loading_placeholder.empty()
                st.error(f"İşleme Hatası: {e}")
                status_box.update(label="Hata Oluştu", state="error")

    # ─── Render Results if available ───
    if "odm_assets" in st.session_state:
        assets = st.session_state.odm_assets
        
        ortho_path = assets.get("orthophoto")
        dsm_path = assets.get("dsm")
        
        # Load and analyze
        with st.spinner("Haritalar ve analizler yükleniyor..."):
            try:
                analyzer = DroneAnalyzer(ortho_path, dsm_path)
                ortho_data, ortho_meta = analyzer.load_orthophoto()
                
                # ─── Tabs ───
                tab_ortho, tab_veg, tab_count, tab_topo = st.tabs([
                    "🖼️ Ortofoto Haritası",
                    "🌱 Bitki Sağlığı (VARI/GLI)",
                    "🌳 Akıllı Ağaç Sayacı",
                    "📐 Topografya & Eğim"
                ])
                
                # 1. TAB: Orthophoto
                with tab_ortho:
                    st.markdown("""
                    <div class="geo-card">
                        <div class="geo-card-title">🖼️ Yüksek Çözünürlüklü Ortofoto</div>
                        <div class="geo-card-desc">Drone kamerasından üretilen gerçek renkli (RGB) mozaik harita</div>
                    """, unsafe_allow_html=True)
                    
                    # Plot orthophoto using matplotlib
                    fig_o, ax_o = plt.subplots(figsize=(10, 8))
                    fig_o.patch.set_facecolor('none')
                    ax_o.set_facecolor('none')
                    
                    # Transpose (C, H, W) to (H, W, C) for plotting
                    rgb_disp = np.transpose(ortho_data[:3], (1, 2, 0))
                    # Normalizasyon
                    if rgb_disp.max() > 1.0:
                        rgb_disp = np.clip(rgb_disp / 255.0, 0, 1)
                    
                    ax_o.imshow(rgb_disp)
                    ax_o.axis("off")
                    plt.tight_layout()
                    st.pyplot(fig_o)
                    plt.close(fig_o)
                    
                    # Metadata kartı
                    st.markdown("**Ortofoto Coğrafi Detaylar**")
                    col_meta1, col_meta2, col_meta3 = st.columns(3)
                    with col_meta1:
                        st.metric("Çözünürlük (Genişlik x Yükseklik)", f"{ortho_meta['width']} x {ortho_meta['height']} px")
                    with col_meta2:
                        st.metric("Koordinat Sistemi (CRS)", str(ortho_meta['crs']))
                    with col_meta3:
                        st.metric("Dosya Boyutu", f"{os.path.getsize(ortho_path) / (1024*1024):.2f} MB")
                    
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                # 2. TAB: Vegetation Indices
                with tab_veg:
                    st.markdown("""
                    <div class="geo-card">
                        <div class="geo-card-title">🌱 Hassas Bitki Sağlığı Analizi</div>
                        <div class="geo-card-desc">Santimetre çözünürlüklü vejetasyon indeks haritası (RGB kameralar için VARI/GLI)</div>
                    """, unsafe_allow_html=True)
                    
                    col_idx_sel, col_thr_sel = st.columns(2)
                    with col_idx_sel:
                        veg_idx_type = st.selectbox("İndeks Tipi", ["VARI (Önerilen - RGB)", "GLI", "ExG", "NDVI (Sadece 4-Band/NIR varsa)"], key="drone_idx_type")
                    with col_thr_sel:
                        veg_threshold = st.slider("Bitki Eşik Değeri", min_value=-0.5, max_value=0.5, value=0.08, step=0.01, key="drone_veg_threshold")
                        
                    # Calculate index
                    idx_map = analyzer.calculate_vegetation_index(ortho_data, veg_idx_type.split()[0])
                    
                    col_veg_l, col_veg_r = st.columns(2)
                    with col_veg_l:
                        st.markdown("**İndeks Görselleştirmesi**")
                        fig_v, ax_v = plt.subplots(figsize=(6, 5))
                        fig_v.patch.set_facecolor('none')
                        ax_v.set_facecolor('none')
                        im_v = ax_v.imshow(idx_map, cmap="RdYlGn", vmin=-0.2, vmax=0.4)
                        ax_v.axis("off")
                        cbar = fig_v.colorbar(im_v, ax=ax_v, orientation='vertical', shrink=0.8)
                        cbar.ax.tick_params(labelsize=8, colors='#64748B')
                        plt.tight_layout()
                        st.pyplot(fig_v)
                        plt.close(fig_v)
                    with col_veg_r:
                        st.markdown("**Vejetasyon Maskesi**")
                        fig_m, ax_m = plt.subplots(figsize=(6, 5))
                        fig_m.patch.set_facecolor('none')
                        ax_m.set_facecolor('none')
                        ax_m.imshow(idx_map > veg_threshold, cmap="Greens")
                        ax_m.axis("off")
                        plt.tight_layout()
                        st.pyplot(fig_m)
                        plt.close(fig_m)
                        
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                # 3. TAB: Akıllı Ağaç Sayacı
                with tab_count:
                    st.markdown("""
                    <div class="geo-card">
                        <div class="geo-card-title">🌳 Akıllı Ağaç ve Mahsul Sayacı</div>
                        <div class="geo-card-desc">Local Maxima algoritması kullanarak tarladaki bağımsız bitkileri/ağaçları otomatik olarak sayın.</div>
                    """, unsafe_allow_html=True)
                    
                    col_p1, col_p2, col_p3 = st.columns(3)
                    with col_p1:
                        count_min_dist = st.slider("Bitkiler Arası Min. Mesafe (piksel)", min_value=2, max_value=20, value=7, step=1, key="count_min_dist")
                    with col_p2:
                        count_sigma = st.slider("Canopy Yumuşatma (Sigma)", min_value=0.5, max_value=4.0, value=1.2, step=0.1, key="count_sigma")
                    with col_p3:
                        count_idx = st.session_state.get("drone_idx_type", "VARI (Önerilen - RGB)").split()[0]
                        # Re-calculate index just in case
                        local_idx_map = analyzer.calculate_vegetation_index(ortho_data, count_idx)
                    
                    # Detect plants
                    peaks = analyzer.count_plants(local_idx_map, threshold=veg_threshold, min_distance=count_min_dist, sigma=count_sigma)
                    
                    # Metric
                    st.metric("Toplam Tespit Edilen Ağaç / Bitki", f"{len(peaks)} adet")
                    
                    # Plot detections overlay
                    fig_c, ax_c = plt.subplots(figsize=(10, 8))
                    fig_c.patch.set_facecolor('none')
                    ax_c.set_facecolor('none')
                    
                    rgb_disp = np.transpose(ortho_data[:3], (1, 2, 0))
                    if rgb_disp.max() > 1.0:
                        rgb_disp = np.clip(rgb_disp / 255.0, 0, 1)
                        
                    ax_c.imshow(rgb_disp)
                    if peaks:
                        x_p, y_p = zip(*peaks)
                        ax_c.scatter(x_p, y_p, color='#10B981', edgecolor='white', s=25, label="Tespit Edilenler")
                        
                    ax_c.axis("off")
                    plt.tight_layout()
                    st.pyplot(fig_c)
                    plt.close(fig_c)
                    
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                # 4. TAB: Topography slope / DEM
                with tab_topo:
                    st.markdown("""
                    <div class="geo-card">
                        <div class="geo-card-title">📐 Dijital Yükseklik Modeli & Topografya</div>
                        <div class="geo-card-desc">DSM verilerini kullanarak arazinin yükseklik dağılımını, eğim haritasını ve drenaj riskli çukurları inceleyin.</div>
                    """, unsafe_allow_html=True)
                    
                    if dsm_path and os.path.exists(dsm_path):
                        dsm_data, dsm_meta = analyzer.load_dsm()
                        
                        # Calculate slope and pits
                        res_val = st.session_state.get("odm_res_input", 0.05)
                        slope, pits = analyzer.analyze_topography(dsm_data, pixel_resolution=res_val)
                        
                        col_t_l, col_t_r = st.columns(2)
                        with col_t_l:
                            st.markdown("**Yükseklik Haritası (DSM)**")
                            fig_dem, ax_dem = plt.subplots(figsize=(6, 5))
                            fig_dem.patch.set_facecolor('none')
                            ax_dem.set_facecolor('none')
                            im_dem = ax_dem.imshow(dsm_data, cmap="terrain")
                            ax_dem.axis("off")
                            cbar_d = fig_dem.colorbar(im_dem, ax=ax_dem, orientation='vertical', shrink=0.8)
                            cbar_d.set_label("Yükseklik (m)", color='#64748B', size=8)
                            cbar_d.ax.tick_params(labelsize=8, colors='#64748B')
                            plt.tight_layout()
                            st.pyplot(fig_dem)
                            plt.close(fig_dem)
                            
                        with col_t_r:
                            st.markdown("**Eğim Haritası (Slope %)**")
                            fig_sl, ax_sl = plt.subplots(figsize=(6, 5))
                            fig_sl.patch.set_facecolor('none')
                            ax_sl.set_facecolor('none')
                            im_sl = ax_sl.imshow(slope, cmap="inferno", vmin=0, vmax=45)
                            ax_sl.axis("off")
                            cbar_s = fig_sl.colorbar(im_sl, ax=ax_sl, orientation='vertical', shrink=0.8)
                            cbar_s.set_label("Eğim (Derece)", color='#64748B', size=8)
                            cbar_s.ax.tick_params(labelsize=8, colors='#64748B')
                            plt.tight_layout()
                            st.pyplot(fig_sl)
                            plt.close(fig_sl)
                            
                        # Show depressions / pits
                        st.markdown("**Drenaj & Su Birikintisi Riski Taşıyan Çukurlar**")
                        fig_p, ax_p = plt.subplots(figsize=(10, 4))
                        fig_p.patch.set_facecolor('none')
                        ax_p.set_facecolor('none')
                        ax_p.imshow(pits, cmap="Blues")
                        ax_p.axis("off")
                        plt.tight_layout()
                        st.pyplot(fig_p)
                        plt.close(fig_p)
                        st.caption("Açık mavi tonlu bölgeler, çevrelerine göre çukurda kalan ve su birikintisi potansiyeli yüksek olan alanları gösterir.")
                    else:
                        st.warning("Eğim analizi için DSM çıktısı bulunamadı.")
                        
                    st.markdown("</div>", unsafe_allow_html=True)
                    
            except Exception as e:
                st.error(f"Sonuçlar yüklenirken hata oluştu: {e}")
