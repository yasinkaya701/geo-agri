"""Google Earth Engine (GEE) ve geemap Entegrasyon Modülü.

Sentinel-2 uydusundan bulut arındırılmış True Color (RGB) ve NDVI zaman tüneli (timelapse)
GIF'leri üretir. GEE yetkilendirmesi olmadığında Pillow ile yapay büyüme GIF'i
üreten bir Simülasyon moduna sahiptir.
"""

import os
import time
from typing import Tuple, Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from shapely.geometry import shape
import matplotlib.cm as cm
from src.config import logger

# GEE ve geemap'i geçici olarak import edelim, hata verirse yakalayacağız
try:
    import ee
    import geemap
    GEE_AVAILABLE = True
except ImportError:
    GEE_AVAILABLE = False
    logger.warning("ee veya geemap kütüphaneleri bulunamadı. GEE Timelapse simülasyon modunda çalışacaktır.")

class GEETimelapseEngine:
    """GEE ve geemap ile zaman tüneli üretim motoru."""

    def __init__(self):
        self.initialized = False
        self.error_message = ""
        self._is_simulated = False

        if GEE_AVAILABLE:
            self.initialized, self.error_message = self.initialize_gee()
        else:
            self.initialized = False
            self.error_message = "earthengine-api veya geemap kütüphaneleri eksik."
            self._is_simulated = True

    @property
    def is_simulated(self) -> bool:
        return self._is_simulated or not self.initialized

    @is_simulated.setter
    def is_simulated(self, val: bool):
        self._is_simulated = val

    def initialize_gee(self) -> Tuple[bool, str]:
        """Earth Engine API'sini başlatır."""
        try:
            # Otomatik kimlik doğrulama için EARTHENGINE_TOKEN çevre değişkenini kontrol et
            ee_token = os.getenv("EARTHENGINE_TOKEN")
            if ee_token:
                cred_path = os.path.expanduser("~/.config/earthengine/credentials")
                if not os.path.exists(cred_path):
                    os.makedirs(os.path.dirname(cred_path), exist_ok=True)
                    with open(cred_path, "w") as f:
                        f.write(ee_token)
                    logger.info("EARTHENGINE_TOKEN çevre değişkeni ~/.config/earthengine/credentials dosyasına yazıldı.")

            project_id = os.getenv("GEE_PROJECT", "earth-500319")
            ee.Initialize(project=project_id)
            logger.info(f"Google Earth Engine başarıyla başlatıldı. Proje: {project_id}")
            return True, f"Earth Engine başarıyla başlatıldı ({project_id})."
        except Exception as e:
            err_msg = str(e)
            logger.warning(f"GEE başlatılamadı (Büyük ihtimalle kimlik doğrulama eksik): {err_msg}")
            return False, err_msg

    def create_timelapse(
        self,
        geometry_geojson: Dict[str, Any],
        out_gif_path: str,
        start_year: int = 2023,
        end_year: int = 2024,
        start_date: str = "03-01",
        end_date: str = "10-31",
        band_mode: str = "RGB",  # "RGB" veya "NDVI"
        fps: int = 4
    ) -> str:
        """Kullanıcının çizdiği tarla geometrisine göre Sentinel-2 timelapse GIF'i üretir."""
        if self.is_simulated:
            logger.info("GEE bağlantısı yok. Yerel STAC API ile gerçek zaman tüneli üretiliyor...")
            return self.create_real_stac_timelapse(
                geometry_geojson=geometry_geojson,
                out_gif_path=out_gif_path,
                start_year=start_year,
                end_year=end_year,
                start_date=start_date,
                end_date=end_date,
                band_mode=band_mode,
                fps=fps
            )

        try:
            # 1. GeoJSON geometrisini ee.Geometry'ye dönüştür
            # Sentinel-2 verilerini çekebilmek için Bounding Box veya Polygon geometrisi
            geom_type = geometry_geojson.get("type", "Feature")
            if geom_type == "Feature":
                geom_data = geometry_geojson.get("geometry", {})
            else:
                geom_data = geometry_geojson

            ee_geom = ee.Geometry(geom_data)
            
            # ROI alanını biraz genişletelim (yakınlaştırma oranını ayarlamak için buffer verilebilir)
            # Ancak tarla odaklı olacağı için bounding box sınırları yeterlidir.
            roi = ee_geom.bounds()

            # 2. Timelapse üretimi
            if band_mode == "RGB":
                logger.info(f"RGB Timelapse üretiliyor: {start_year}-{end_year}")
                geemap.sentinel2_timelapse(
                    roi=roi,
                    out_gif=out_gif_path,
                    start_year=start_year,
                    end_year=end_year,
                    start_date=start_date,
                    end_date=end_date,
                    frequency="month",
                    bands=["Red", "Green", "Blue"],
                    frames_per_second=fps,
                    title="True Color RGB (Sentinel-2)",
                    add_text=True,
                    text_color="white",
                    text_size=18,
                    progress_bar_color="emerald"
                )
            else:  # NDVI
                logger.info(f"NDVI Timelapse üretiliyor: {start_year}-{end_year}")
                
                # NDVI için özel ImageCollection hazırlayalım
                s2_col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
                    .filterBounds(roi) \
                    .filterDate(f"{start_year}-{start_date}", f"{end_year}-{end_date}") \
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))

                # Bulut maskeleme fonksiyonu
                def mask_clouds(img):
                    qa = img.select("QA60")
                    cloud_bit = 1 << 10
                    cirrus_bit = 1 << 11
                    mask = qa.bitwiseAnd(cloud_bit).eq(0).and_(qa.bitwiseAnd(cirrus_bit).eq(0))
                    return img.updateMask(mask)

                # NDVI hesaplama ve RGB'ye dönüştürme (visualize)
                # geemap.create_timelapse tek bandı renklendirmek için visualize edilmesini bekler
                ndvi_palette = ["#FFFFFF", "#CE7E45", "#DF923D", "#F1B555", "#FCD163", "#99B718", "#74A00F", "#52840D", "#114D04"]
                
                def process_ndvi(img):
                    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
                    # visualize ile 3 kanallı renkli haritaya dönüştür
                    visualized = ndvi.visualize(min=-0.1, max=0.8, palette=ndvi_palette)
                    
                    # Tarih özelliğini koruyalım (Pillow etiketlemesi için)
                    date_str = img.date().format("YYYY-MM-dd")
                    return visualized.set("system:time_start", img.get("system:time_start")).set("date", date_str)

                processed_col = s2_col.map(mask_clouds).map(process_ndvi)
                
                # geemap.create_timelapse ile GIF oluştur
                geemap.create_timelapse(
                    collection=processed_col,
                    roi=roi,
                    out_gif=out_gif_path,
                    frames_per_second=fps,
                    add_text=True,
                    text_color="white",
                    text_size=18,
                    progress_bar_color="emerald",
                    title="NDVI Plant Health (Sentinel-2)"
                )

            if os.path.exists(out_gif_path) and os.path.getsize(out_gif_path) > 0:
                logger.info(f"GEE Timelapse başarıyla tamamlandı: {out_gif_path}")
                return out_gif_path
            else:
                raise Exception("Timelapse GIF dosyası oluşturulamadı.")

        except Exception as e:
            logger.error(f"GEE Timelapse hatası: {e}. Yerel STAC API ile gerçek zaman tüneline dönülüyor...")
            return self.create_real_stac_timelapse(
                geometry_geojson=geometry_geojson,
                out_gif_path=out_gif_path,
                start_year=start_year,
                end_year=end_year,
                start_date=start_date,
                end_date=end_date,
                band_mode=band_mode,
                fps=fps
            )

    def create_real_stac_timelapse(
        self,
        geometry_geojson: Dict[str, Any],
        out_gif_path: str,
        start_year: int,
        end_year: int,
        start_date: str,
        end_date: str,
        band_mode: str,
        fps: int
    ) -> str:
        """Planetary Computer STAC API'den gerçek Sentinel-2 verilerini çeker,
        tarlayı maskeler, RGB veya NDVI olarak kareleri renklendirir ve gerçek bir timelapse GIF üretir.
        """
        logger.info(f"Gerçek STAC Timelapse üretiliyor: {start_year}-{end_year} ({start_date} -> {end_date}), Mod={band_mode}")
        
        # 1. GeoJSON geometrisini shapely shape'e çevir
        geom_type = geometry_geojson.get("type", "Feature")
        if geom_type == "Feature":
            geom_data = geometry_geojson.get("geometry", {})
        else:
            geom_data = geometry_geojson
            
        geom = shape(geom_data)
        
        # 2. STAC Client kullanarak ara
        from src.satellite.stac_client import StacClient
        from src.satellite.bands_loader import load_and_mask_bands
        
        stac = StacClient()
        
        # Her yıl için arama yapalım ve her aydan en az bulutlu görüntüyü seçelim
        all_items = []
        for y in range(start_year, end_year + 1):
            s_str = f"{y}-{start_date}"
            e_str = f"{y}-{end_date}"
            logger.info(f"STAC taraması yapılıyor: {s_str} -> {e_str}")
            try:
                items = stac.search_sentinel_data(
                    geometry_wgs84=geom,
                    start_date=s_str,
                    end_date=e_str,
                    max_cloud_cover=60.0  # toleranslı arama
                )
                if items:
                    # Görüntüleri aylara göre gruplayalım ve her ay için en az bulutlusunu seçelim
                    monthly_best = {}
                    for item in items:
                        dt = item.properties.get("datetime", "")
                        if not dt:
                            continue
                        month_key = dt[:7] # YYYY-MM
                        if month_key not in monthly_best:
                            monthly_best[month_key] = item
                        else:
                            curr_cc = item.properties.get("eo:cloud_cover", 100.0)
                            best_cc = monthly_best[month_key].properties.get("eo:cloud_cover", 100.0)
                            if curr_cc < best_cc:
                                monthly_best[month_key] = item
                    
                    # Seçilen en iyi aylık görüntüleri ekle
                    for month_key in sorted(monthly_best.keys()):
                        all_items.append(monthly_best[month_key])
            except Exception as e:
                logger.error(f"STAC arama hatası ({y}): {e}")
                
        if not all_items:
            logger.warning("Herhangi bir gerçek uydu görüntüsü bulunamadı. Simülasyon verisi üretiliyor...")
            return self.generate_mock_timelapse(out_gif_path, start_year, end_year, band_mode, fps)
            
        # Kronolojik sıralayalım
        all_items = sorted(all_items, key=lambda x: x.properties.get("datetime", ""))
        
        # 3. Görüntüleri indir ve maskele
        frames = []
        
        for idx, item in enumerate(all_items):
            date_str = item.properties.get("datetime", "")[:10]
            logger.info(f"Kare indiriliyor [{idx+1}/{len(all_items)}]: {date_str}")
            try:
                loaded = load_and_mask_bands(item, geom, max_field_cloud_percent=100.0)
                if loaded is not None:
                    # Görüntüyü oluştur
                    # shape: (1, H, W) veya squeeze edilmemiş olabilir; loader squeeze ediyor
                    h = loaded["red"].shape[0] if len(loaded["red"].shape) >= 2 else 0
                    w = loaded["red"].shape[1] if len(loaded["red"].shape) >= 2 else 0
                    if len(loaded["red"].shape) < 2:
                        # squeeze edilmiştir, shape (H, W)'dur
                        h, w = loaded["red"].shape
                    
                    if h == 0 or w == 0:
                        continue
                        
                    if band_mode == "RGB":
                        r = loaded["red"].values
                        g = loaded["green"].values
                        b = loaded["blue"].values
                        
                        r = np.nan_to_num(r, nan=0.0)
                        g = np.nan_to_num(g, nan=0.0)
                        b = np.nan_to_num(b, nan=0.0)
                        
                        rgb = np.dstack([r, g, b])
                        rgb = np.clip(rgb / 3000.0, 0, 1)
                        img_np = (rgb * 255).astype(np.uint8)
                        
                    else: # NDVI
                        from src.dataset.ndvi import calculate_ndvi
                        r = np.nan_to_num(loaded["red"].values, nan=0.0)
                        nir = np.nan_to_num(loaded["nir"].values, nan=0.0)
                        
                        ndvi = calculate_ndvi(r, nir)
                        ndvi = np.nan_to_num(ndvi, nan=-0.1)
                        
                        ndvi_norm = (ndvi + 0.1) / 0.9
                        ndvi_norm = np.clip(ndvi_norm, 0, 1)
                        
                        from matplotlib import colormaps
                        cmap = colormaps["RdYlGn"]
                        rgba_img = cmap(ndvi_norm)
                        img_np = (rgba_img[:, :, :3] * 255).astype(np.uint8)
                        
                    # 1. Aspect Ratio Koruyarak Boyutlandırma ve Ortalama
                    target_w, target_h = 480, 320 # Alt 40 piksel bilgi paneli için ayrıldı
                    
                    aspect = w / h
                    target_aspect = target_w / target_h
                    
                    if aspect > target_aspect:
                        new_w = target_w
                        new_h = int(target_w / aspect)
                    else:
                        new_h = target_h
                        new_w = int(target_h * aspect)
                        
                    scale_x = new_w / w
                    scale_y = new_h / h
                    
                    paste_x = (target_w - new_w) // 2
                    paste_y = (target_h - new_h) // 2
                    
                    # Pillow Resmine dönüştür
                    pil_cropped = Image.fromarray(img_np)
                    pil_resized = pil_cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    
                    # 480x360 boyutlu ana görsel tuvalini oluştur (Slate Koyu Arka Plan)
                    canvas = Image.new("RGB", (480, 360), color=(15, 23, 42))
                    canvas.paste(pil_resized, (paste_x, paste_y))
                    
                    # 2. Resmi Kadastro Sınırını (Polygon Outline) Çiz
                    try:
                        from src.geometry.projection import project_geometry
                        raster_crs = loaded["red"].rio.crs
                        projected_geom = project_geometry(geom, from_crs=4326, to_crs=raster_crs)
                        
                        exterior_coords = list(projected_geom.exterior.coords)
                        x_coords = loaded["red"].coords["x"].values
                        y_coords = loaded["red"].coords["y"].values
                        dx = x_coords[1] - x_coords[0] if len(x_coords) > 1 else 10.0
                        dy = y_coords[1] - y_coords[0] if len(y_coords) > 1 else -10.0
                        
                        canvas_coords = []
                        for pt_x, pt_y in exterior_coords:
                            col = (pt_x - (x_coords[0] - dx / 2.0)) / dx
                            row = (pt_y - (y_coords[0] - dy / 2.0)) / dy
                            
                            final_x = col * scale_x + paste_x
                            final_y = row * scale_y + paste_y
                            canvas_coords.append((final_x, final_y))
                            
                        # Tuval üzerine poligon sınırını çiz
                        draw_poly = ImageDraw.Draw(canvas)
                        if len(canvas_coords) > 1:
                            draw_poly.polygon(canvas_coords, outline=(16, 185, 129), width=2) # Zümrüt Yeşili Sınır
                    except Exception as poly_err:
                        logger.warning(f"Zaman tüneli karesine tarla sınırı çizilemedi: {poly_err}")
                        
                    # 3. Bilgi watermark paneli ekle (Pillow)
                    draw = ImageDraw.Draw(canvas)
                    # Alt bilgi paneli arka planı
                    draw.rectangle([(0, 320), (480, 360)], fill=(15, 23, 42))
                    
                    # Bilgi yazıları
                    mode_text = "Hassas Sağlık (NDVI)" if band_mode == "NDVI" else "Gerçek Renk (RGB)"
                    draw.text((15, 360 - 28), f"Tarih: {date_str}", fill=(255, 255, 255))
                    draw.text((480 - 200, 360 - 28), f"{mode_text}", fill=(16, 185, 129))
                    
                    # İlerleme çubuğu (Progress bar)
                    bar_w = int((idx + 1) / len(all_items) * 480)
                    draw.rectangle([(0, 360 - 4), (bar_w, 360)], fill=(16, 185, 129))
                    
                    frames.append(canvas)
            except Exception as e:
                logger.error(f"Kare yüklenirken hata oluştu ({date_str}): {e}")
                
        if not frames:
            logger.warning("Hiçbir kare başarıyla yüklenemedi. Simülasyon verisi üretiliyor...")
            return self.generate_mock_timelapse(out_gif_path, start_year, end_year, band_mode, fps)
            
        # GIF olarak kaydet
        os.makedirs(os.path.dirname(out_gif_path), exist_ok=True)
        duration_ms = int(1000 / fps)
        frames[0].save(
            out_gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=duration_ms,
            loop=0
        )
        
        logger.info(f"Gerçek STAC Timelapse üretimi tamamlandı: {out_gif_path}")
        return out_gif_path


    # ═══════════════════════════════════════════════════════════
    #  Mock / Simulation Timelapse Generator (Using Pillow)
    # ═══════════════════════════════════════════════════════════

    def generate_mock_timelapse(
        self,
        output_path: str,
        start_year: int,
        end_year: int,
        band_mode: str,
        fps: int
    ) -> str:
        """Pillow ile tarlanın mevsimsel gelişimini simüle eden yapay büyüme GIF'i üretir."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Kareleri hazırlayalım (Mevsimsel döngüyü simüle etmek için 12 kare)
        frames = []
        width, height = 480, 360
        
        months = [
            ("03-15", "Mart"), ("04-15", "Nisan"), ("05-15", "Mayıs"), 
            ("06-15", "Haziran"), ("07-15", "Temmuz"), ("08-15", "Ağustos"), 
            ("09-15", "Eylül"), ("10-15", "Ekim")
        ]
        
        # Seçilen yıllara göre kareleri çoğaltalım
        years = list(range(start_year, end_year + 1))
        timeline = []
        for y in years:
            for m_code, m_name in months:
                timeline.append((f"{y}-{m_code}", m_name))

        # Toplam kare sayısı
        total_frames = len(timeline)
        
        for idx, (date_str, m_name) in enumerate(timeline):
            # 1. Boş resim oluştur
            img = Image.new("RGB", (width, height), color=(139, 115, 85)) # Toprak rengi arka plan
            draw = ImageDraw.Draw(img)
            
            # 2. Tarla şekli çizelim (Merkezde bir poligon)
            field_coords = [(120, 100), (360, 80), (400, 260), (80, 240)]
            
            # Mevsimsel bitki rengini belirle (Büyüme evresi simülasyonu)
            # Mart: Kahverengi, Mayıs-Haziran: Canlı Yeşil, Ağustos: Sarı/Kurak, Ekim: Çıplak
            cycle_pos = (idx % len(months)) / len(months)
            
            if band_mode == "RGB":
                if cycle_pos < 0.15: # İlkbahar başlangıcı
                    field_color = (150, 130, 90) # Soluk kahverengi
                elif cycle_pos < 0.35: # Büyüme
                    field_color = (76, 154, 42) # Açık yeşil
                elif cycle_pos < 0.65: # Olgunlaşma/Pik
                    field_color = (16, 100, 4) # Koyu yeşil
                elif cycle_pos < 0.85: # Hasat / Kuruma
                    field_color = (204, 175, 75) # Altın/Sarı
                else: # Sonbahar / Sürülmüş
                    field_color = (120, 95, 65) # Toprak
            else: # NDVI Modu (Renklendirilmiş NDVI Paleti)
                # NDVI: -0.1 (Kırmızı) -> 0.8 (Koyu Yeşil)
                if cycle_pos < 0.15:
                    field_color = (252, 209, 99) # Sarı-Turuncu (NDVI ~0.15)
                elif cycle_pos < 0.35:
                    field_color = (153, 183, 24) # Açık Yeşil (NDVI ~0.4)
                elif cycle_pos < 0.65:
                    field_color = (17, 77, 4) # Koyu Orman Yeşili (NDVI ~0.75)
                elif cycle_pos < 0.85:
                    field_color = (223, 146, 61) # Turuncu (NDVI ~0.2)
                else:
                    field_color = (206, 126, 69) # Kahverengi-Kırmızı (NDVI ~0.1)

            # Tarlayı çiz
            draw.polygon(field_coords, fill=field_color, outline=(255, 255, 255), width=2)
            
            # Etraftaki diğer küçük tarlaları simüle et
            draw.polygon([(20, 20), (100, 10), (110, 80), (10, 90)], fill=(130, 120, 90), outline=(200, 200, 200))
            draw.polygon([(380, 20), (460, 30), (450, 120), (370, 100)], fill=(90, 140, 50) if cycle_pos < 0.6 else (160, 150, 80), outline=(200, 200, 200))
            
            # 3. Bilgi paneli ve tarih yazısı ekleyelim
            # Panel arka planı
            draw.rectangle([(0, height - 40), (width, height)], fill=(15, 23, 42))
            
            # Yazılar
            mode_text = "Hassas Sağlık (NDVI)" if band_mode == "NDVI" else "Gerçek Renk (RGB)"
            sim_badge = " (SİMÜLASYON)"
            
            # Font yüklemeye çalışalım
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
                
            draw.text((15, height - 28), f"Tarih: {date_str} ({m_name})", fill=(255, 255, 255), font=font)
            draw.text((width - 240, height - 28), f"{mode_text}{sim_badge}", fill=(16, 185, 129), font=font)
            
            # İlerleme çubuğu (Progress bar)
            bar_w = int((idx + 1) / total_frames * width)
            draw.rectangle([(0, height - 4), (bar_w, height)], fill=(16, 185, 129)) # Emerald yeşili progress
            
            frames.append(img)
            
        # GIF olarak kaydet
        duration_ms = int(1000 / fps)
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=duration_ms,
            loop=0
        )
        
        logger.info(f"Simülasyon GIF üretimi tamamlandı: {output_path}")
        return output_path


def convert_gif_to_mp4(gif_path: str, mp4_path: str, fps: int = 4) -> str:
    """imageio-ffmpeg kullanarak GIF dosyasını MP4 videoya dönüştürür."""
    import imageio
    try:
        reader = imageio.get_reader(gif_path)
        fps_val = reader.get_meta_data().get('fps', fps)
        writer = imageio.get_writer(mp4_path, fps=fps_val, codec='libx264', pixelformat='yuv420p')
        for frame in reader:
            writer.append_data(frame)
        writer.close()
        reader.close()
        logger.info(f"GIF başarıyla MP4'e dönüştürüldü: {mp4_path}")
        return mp4_path
    except Exception as e:
        logger.error(f"MP4 dönüştürme hatası: {e}")
        raise e


def extract_gif_frames_to_zip(gif_path: str, zip_path: str) -> str:
    """GIF karesini tek tek JPG fotoğrafları olarak ayıklayıp ZIP arşivi yapar."""
    import zipfile
    import io
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
            img = Image.open(gif_path)
            frame_idx = 0
            try:
                while True:
                    frame = img.copy().convert("RGB")
                    buf = io.BytesIO()
                    frame.save(buf, format="JPEG", quality=90)
                    zip_ref.writestr(f"foto_{frame_idx:03d}.jpg", buf.getvalue())
                    frame_idx += 1
                    img.seek(img.tell() + 1)
            except EOFError:
                pass  # GIF sonu
        logger.info(f"GIF kareleri başarıyla {zip_path} dosyasına ziplelendi. Toplam: {frame_idx} foto.")
        return zip_path
    except Exception as e:
        logger.error(f"Kare ayıklama ve zipleme hatası: {e}")
        raise e

