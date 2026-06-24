import math
from typing import Tuple
from shapely.geometry import base
from shapely.ops import transform
from pyproj import Transformer, CRS
from src.config import logger
from src.exceptions import GeometryError

def get_utm_epsg(longitude: float, latitude: float) -> int:
    """Verilen enlem/boylam koordinatına göre en uygun UTM EPSG kodunu belirler."""
    if not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
        raise GeometryError(f"Geçersiz WGS84 koordinatları: Boylam={longitude}, Enlem={latitude}")
        
    # Boylama göre UTM zonunu bulma
    zone = int((longitude + 180) / 6) + 1
    
    # Kuzey/Güney Yarımküreye göre EPSG kodu belirleme
    # EPSG: 32600 + zon (Kuzey Yarımküre)
    # EPSG: 32700 + zon (Güney Yarımküre)
    if latitude >= 0:
        epsg = 32600 + zone
    else:
        epsg = 32700 + zone
        
    logger.debug(f"Koordinat ({longitude}, {latitude}) için hesaplanan UTM EPSG: {epsg}")
    return epsg

def project_geometry(geometry: base.BaseGeometry, from_crs: int = 4326, to_crs: int = 32636) -> base.BaseGeometry:
    """Bir Shapely geometrisini bir CRS sisteminden diğerine dönüştürür.
    
    Varsayılan olarak enlem/boylamdan (4326) metre bazlı projeksiyona çeviri yapar.
    """
    try:
        transformer = Transformer.from_crs(
            CRS.from_user_input(from_crs),
            CRS.from_user_input(to_crs),
            always_xy=True
        )
        projected_geom = transform(transformer.transform, geometry)
        return projected_geom
    except Exception as e:
        logger.error(f"Geometri projeksiyon dönüşüm hatası ({from_crs} -> {to_crs}): {e}")
        raise GeometryError(f"Koordinat dönüşümü yapılamadı: {str(e)}")

def get_geometry_area_hectares(geometry_wgs84: base.BaseGeometry) -> float:
    """WGS84 formatındaki bir poligon geometrisinin alanını hektar cinsinden hesaplar.
    
    Bunun için poligonun merkez noktasına göre UTM projeksiyonuna dönüşüm yapılır.
    """
    try:
        # Poligonun merkezini bul
        centroid = geometry_wgs84.centroid
        lon, lat = centroid.x, centroid.y
        
        # Uygun UTM zonunu bul
        utm_epsg = get_utm_epsg(lon, lat)
        
        # Geometriyi UTM'e projekte et
        projected_geom = project_geometry(geometry_wgs84, from_crs=4326, to_crs=utm_epsg)
        
        # Alanı hesapla (metrekare cinsinden döner, 10,000'e bölerek hektara çevrilir)
        area_m2 = projected_geom.area
        area_ha = area_m2 / 10000.0
        
        logger.info(f"Tarla alanı hesaplandı: {area_m2:.2f} m² ({area_ha:.4f} Hektar)")
        return area_ha
    except Exception as e:
        logger.error(f"Alan hesaplama hatası: {e}")
        raise GeometryError(f"Tarla alanı hesaplanırken hata oluştu: {str(e)}")
