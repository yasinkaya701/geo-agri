import xarray as xr
from shapely.geometry import base
from src.config import logger
from src.exceptions import RasterProcessingError
from src.geometry.projection import project_geometry

def clip_xarray_with_geometry(data_array: xr.DataArray, geometry_wgs84: base.BaseGeometry) -> xr.DataArray:
    """xarray DataArray nesnesini belirtilen Shapely geometrisiyle kırpar (clip).
    
    Geometrinin koordinat sistemi (WGS84), veri kümesinin koordinat sistemine (CRS)
    otomatik olarak dönüştürülür.
    """
    try:
        # Veri kümesinin CRS'ini al (rioxarray vasıtasıyla)
        raster_crs = data_array.rio.crs
        if raster_crs is None:
            raise RasterProcessingError("Veri kümesinin CRS (koordinat sistemi) bilgisi bulunamadı.")
            
        # Geometriyi verinin CRS'ine dönüştür
        # raster_crs.to_epsg() veya to_string() kullanılabilir
        try:
            target_epsg = raster_crs.to_epsg()
        except Exception:
            target_epsg = None
            
        if target_epsg is None:
            # EPSG alınamazsa string formatını deneyelim
            target_crs_input = raster_crs.to_string()
        else:
            target_crs_input = target_epsg
            
        logger.info(f"Geometri, veri CRS sistemine dönüştürülüyor: EPSG:4326 -> {target_crs_input}")
        projected_geom = project_geometry(geometry_wgs84, from_crs=4326, to_crs=target_crs_input)
        
        # Get bounding box of the projected geometry
        minx, miny, maxx, maxy = projected_geom.bounds
        
        # Clip box first (extremely fast, translated directly to a windowed read in GDAL/rasterio)
        # We add a 20-meter buffer (2 pixels in Sentinel-2 10m bands) to ensure we don't crop any edge pixel of the polygon.
        buffer = 20.0
        clipped_box = data_array.rio.clip_box(
            minx - buffer, miny - buffer, maxx + buffer, maxy + buffer,
            crs=target_crs_input
        )
        
        # Now clip the tiny in-memory array with the polygon (takes milliseconds!)
        clipped_array = clipped_box.rio.clip([projected_geom], crs=target_crs_input, drop=True)
        
        logger.info(f"Kırpma başarılı (clip_box optimizasyonu ile). Orijinal boyut: {data_array.shape}, Kırpılmış boyut: {clipped_array.shape}")
        return clipped_array
        
    except Exception as e:
        logger.error(f"Kırpma işlemi başarısız oldu: {e}")
        raise RasterProcessingError(f"Görüntü tarla sınırlarına göre kırpılamadı: {str(e)}")
