import numpy as np
import xarray as xr
import rioxarray
import rasterio
from shapely.geometry import base
from typing import Dict, Any, Tuple, Optional
from src.config import logger
from src.exceptions import RasterProcessingError
from src.geometry.clipping import clip_xarray_with_geometry

def load_and_mask_bands(
    item: Any, 
    geometry_wgs84: base.BaseGeometry,
    max_field_cloud_percent: float = 30.0
) -> Optional[Dict[str, xr.DataArray]]:
    """Tek bir Sentinel-2 STAC öğesi için Red, NIR ve SCL bantlarını yükler,
    tarlaya göre kırpar ve bulut maskelemesini uygular.
    
    Eğer tarlanın bulutluluk oranı sınır değeri aşıyorsa None döner.
    """
    date_str = item.properties.get("datetime", "")[:10]
    logger.info(f"[{date_str}] Bant yükleme işlemi başladı...")
    
    # İlgili bantların URL'lerini (varlıklarını) çekme
    assets = item.assets
    required_bands = ["B02", "B03", "B04", "B08", "SCL"]
    for b in required_bands:
        if b not in assets:
            logger.warning(f"[{date_str}] Gerekli {b} bandı eksik. Atlanıyor.")
            return None
        
    blue_url = assets["B02"].href
    green_url = assets["B03"].href
    red_url = assets["B04"].href
    nir_url = assets["B08"].href
    scl_url = assets["SCL"].href
    
    try:
        # Optimized GDAL parameters for fast remote COG reading
        with rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="YES",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
            VSI_CACHE=True
        ):
            # 1. Bantları pencereli okuma için uzaktan aç (rioxarray lazily opens COGs)
            # Sadece tarlanın sınırlarında okuyarak ağ trafiğini ve bellek kullanımını azaltıyoruz.
            logger.info(f"[{date_str}] Uzak raster dosyaları açılıyor...")
            blue_raw = rioxarray.open_rasterio(blue_url, masked=True)
            green_raw = rioxarray.open_rasterio(green_url, masked=True)
            red_raw = rioxarray.open_rasterio(red_url, masked=True)
            nir_raw = rioxarray.open_rasterio(nir_url, masked=True)
            scl_raw = rioxarray.open_rasterio(scl_url, masked=True)
            
            # 2. Bantları tarla sınırına göre kırp (clipping)
            logger.info(f"[{date_str}] Tarla sınırlarına göre kırpma yapılıyor...")
            blue_clip = clip_xarray_with_geometry(blue_raw, geometry_wgs84)
            green_clip = clip_xarray_with_geometry(green_raw, geometry_wgs84)
            red_clip = clip_xarray_with_geometry(red_raw, geometry_wgs84)
            nir_clip = clip_xarray_with_geometry(nir_raw, geometry_wgs84)
            scl_clip = clip_xarray_with_geometry(scl_raw, geometry_wgs84)
            
            # 3. SCL (20m) bandını Red (10m) bandı boyutuna eşitle (resampling)
            # SCL bandının çözünürlüğü farklı olduğu için grid hizalaması gereklidir.
            logger.info(f"[{date_str}] SCL maskesi Red bandı çözünürlüğüne (10m) eşleniyor...")
            scl_resampled = scl_clip.rio.reproject_match(red_clip)
            
            # 4. Bulut ve Gölge Maskesi Oluşturma
            # SCL Sınıfları:
            # 0: NO_DATA, 1: SATURATED_OR_DEFECTIVE, 3: CLOUD_SHADOWS
            # 8: CLOUD_MEDIUM_PROBABILITY, 9: CLOUD_HIGH_PROBABILITY, 10: THIN_CIRRUS
            cloud_shadow_values = [0, 1, 3, 8, 9, 10]
            
            # Bulutlu/gölgeli alanları True yapan maske
            is_cloud = scl_resampled.isin(cloud_shadow_values)
            
            # Tarla içindeki toplam geçerli piksel sayısı (kırpılmış alandaki NaN olmayanlar)
            valid_field_mask = red_clip.notnull()
            total_field_pixels = int(valid_field_mask.sum().item())
            
            if total_field_pixels == 0:
                logger.warning(f"[{date_str}] Tarla içinde geçerli piksel bulunamadı. Atlanıyor.")
                return None
                
            # Bulutlu tarla piksel sayısı
            cloudy_field_pixels = int((is_cloud & valid_field_mask).sum().item())
            field_cloud_percent = (cloudy_field_pixels / total_field_pixels) * 100.0
            
            logger.info(f"[{date_str}] Tarla içi bulutluluk oranı: {field_cloud_percent:.2f}% (Tolerans: {max_field_cloud_percent}%)")
            
            # Sınır değer kontrolü
            if field_cloud_percent > max_field_cloud_percent:
                logger.warning(f"[{date_str}] Tarla içi bulutluluk sınırı aşıldı ({field_cloud_percent:.2f}% > {max_field_cloud_percent}%). Bu tarih atlanıyor.")
                return None
                
            # 5. Maskeyi uygula (Bulutsuz temiz pikselleri koru, bulutluları NaN yap)
            clear_mask = ~is_cloud
            blue_masked = blue_clip.where(clear_mask)
            green_masked = green_clip.where(clear_mask)
            red_masked = red_clip.where(clear_mask)
            nir_masked = nir_clip.where(clear_mask)
            
            # Sıkıştırma ve kapatma işlemlerini kolaylaştırmak için xarray verilerini döndürelim
            # Band boyutları 1, H, W formatındadır, squeeze() ile 1 boyutunu (band boyutu) yok edebiliriz.
            return {
                "blue": blue_masked.squeeze(drop=True),
                "green": green_masked.squeeze(drop=True),
                "red": red_masked.squeeze(drop=True),
                "nir": nir_masked.squeeze(drop=True),
                "scl": scl_resampled.squeeze(drop=True),
                "cloud_percent": field_cloud_percent
            }
        
    except Exception as e:
        logger.error(f"[{date_str}] Görüntü okuma/işleme hatası: {e}")
        raise RasterProcessingError(f"[{date_str}] Uydu verisi işlenirken hata oluştu: {str(e)}")


def load_uav_ground_texture(
    item: Any,
    geometry_wgs84: base.BaseGeometry,
    buffer_meters: float = 300.0
) -> Optional[Dict[str, xr.DataArray]]:
    """Uçuş simülatörü için tarlanın çevresini de kapsayan temiz bir dikdörtgen RGB zemin görseli yükler.
    Herhangi bir poligon maskelemesi uygulamaz, böylece tarlanın etrafındaki yollar ve diğer tarlalar da görünür.
    """
    date_str = item.properties.get("datetime", "")[:10]
    logger.info(f"[{date_str}] UAV Zemin Kaplaması yükleniyor (Tampon: {buffer_meters}m)...")
    
    assets = item.assets
    required_bands = ["B02", "B03", "B04"]
    for b in required_bands:
        if b not in assets:
            logger.warning(f"[{date_str}] UAV Zemin Kaplaması için {b} bandı eksik.")
            return None
            
    blue_url = assets["B02"].href
    green_url = assets["B03"].href
    red_url = assets["B04"].href
    
    try:
        from src.geometry.projection import project_geometry
        with rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="YES",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
            VSI_CACHE=True
        ):
            # Uzaktan aç
            blue_raw = rioxarray.open_rasterio(blue_url, masked=True)
            green_raw = rioxarray.open_rasterio(green_url, masked=True)
            red_raw = rioxarray.open_rasterio(red_url, masked=True)
            
            # Verinin CRS sistemine dönüştür
            raster_crs = red_raw.rio.crs
            try:
                target_epsg = raster_crs.to_epsg()
            except Exception:
                target_epsg = None
            target_crs_input = target_epsg if target_epsg is not None else raster_crs.to_string()
            
            # Geometriyi verinin CRS'ine dönüştür
            projected_geom = project_geometry(geometry_wgs84, from_crs=4326, to_crs=target_crs_input)
            minx, miny, maxx, maxy = projected_geom.bounds
            
            # BBOX sınırlarını buffer_meters kadar genişletelim
            clipped_blue = blue_raw.rio.clip_box(
                minx - buffer_meters, miny - buffer_meters, maxx + buffer_meters, maxy + buffer_meters,
                crs=target_crs_input
            )
            clipped_green = green_raw.rio.clip_box(
                minx - buffer_meters, miny - buffer_meters, maxx + buffer_meters, maxy + buffer_meters,
                crs=target_crs_input
            )
            clipped_red = red_raw.rio.clip_box(
                minx - buffer_meters, miny - buffer_meters, maxx + buffer_meters, maxy + buffer_meters,
                crs=target_crs_input
            )
            
            return {
                "blue": clipped_blue.squeeze(drop=True),
                "green": clipped_green.squeeze(drop=True),
                "red": clipped_red.squeeze(drop=True)
            }
            
    except Exception as e:
        logger.error(f"UAV Zemin Kaplaması yüklenirken hata: {e}")
        return None


def load_esri_ground_texture(
    centroid_lat: float,
    centroid_lon: float,
    buffer_meters: float = 300.0
) -> Optional[Any]:
    """ESRI World Imagery Export API'sinden yüksek çözünürlüklü uydu görüntüsü indirir.
    Aspect-ratio düzeltmesi yaparak fiziksel olarak kare alan elde eder.
    """
    import urllib.request
    import math
    import io
    from PIL import Image
    from src.config import logger

    logger.info(f"ESRI World Imagery indiriliyor: Lat={centroid_lat:.5f}, Lon={centroid_lon:.5f}, Tampon={buffer_meters:.1f}m...")
    try:
        # Enlem/boylam derece başına metre dönüşümü
        lat_m_deg = 111132.954 - 559.822 * math.cos(2 * math.radians(centroid_lat))
        lon_m_deg = 111412.84 * math.cos(math.radians(centroid_lat))
        
        delta_lat = buffer_meters / lat_m_deg
        delta_lon = buffer_meters / lon_m_deg
        
        minx = centroid_lon - delta_lon
        miny = centroid_lat - delta_lat
        maxx = centroid_lon + delta_lon
        maxy = centroid_lat + delta_lat
        
        url = (
            f"https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?"
            f"bbox={minx},{miny},{maxx},{maxy}&bboxSR=4326&imageSR=4326&size=1024,1024&format=jpg&f=image"
        )
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read()
            img = Image.open(io.BytesIO(data))
            img.load()
            logger.info(f"ESRI World Imagery başarıyla indirildi. Boyut: {img.size}")
            return img
    except Exception as e:
        logger.error(f"ESRI World Imagery indirme hatası: {e}")
        return None

