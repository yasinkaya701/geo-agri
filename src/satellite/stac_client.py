import pystac_client
import planetary_computer
from shapely.geometry import base
from typing import List, Dict, Any
from src.config import PLANETARY_COMPUTER_STAC_URL, logger
from src.exceptions import STACQueryError

class StacClient:
    """Microsoft Planetary Computer STAC API istemcisi.
    
    Sentinel-2 uydu verilerini sorgular ve taranan öğelerin URL imzalarını (SAS token) üretir.
    """
    
    def __init__(self) -> None:
        # İstemciyi doğrudan başlatıyoruz. Sorgulama esnasında sign_inplace modifier'ını kullanacağız.
        try:
            logger.info("STAC Kataloğu açılıyor...")
            self.client = pystac_client.Client.open(
                PLANETARY_COMPUTER_STAC_URL,
                modifier=planetary_computer.sign_inplace
            )
            logger.info("STAC Kataloğu başarıyla bağlandı.")
        except Exception as e:
            logger.error(f"STAC kataloğuna bağlanılamadı: {e}")
            raise STACQueryError(f"Planetary Computer STAC servisine bağlanılamadı: {str(e)}")

    def search_sentinel_data(
        self, 
        geometry_wgs84: base.BaseGeometry, 
        start_date: str, 
        end_date: str, 
        max_cloud_cover: float = 20.0
    ) -> List[Any]:
        """Verilen poligon geometrisi, tarih aralığı ve maksimum bulutluluk oranına göre
        Sentinel-2 Level-2A uydu görüntülerini arar.
        
        Tarih formatı: YYYY-MM-DD
        """
        try:
            # Poligonun bounding box'ını hesapla: (min_lon, min_lat, max_lon, max_lat)
            bbox = list(geometry_wgs84.bounds)
            logger.info(f"STAC Araması Başlatılıyor... BBOX: {bbox}, Tarih: {start_date}/{end_date}, Max Bulut: {max_cloud_cover}%")
            
            # Zaman aralığı parametresini biçimlendir
            datetime_range = f"{start_date}/{end_date}"
            
            # STAC sorgusu
            search = self.client.search(
                collections=["sentinel-2-l2a"],
                bbox=bbox,
                datetime=datetime_range,
                # Bulutluluk filtresini query parametresi ile ekliyoruz
                query={"eo:cloud_cover": {"lt": max_cloud_cover}},
                sortby=[{"field": "properties.datetime", "direction": "asc"}] # Tarihe göre eskiden yeniye sıralı
            )
            
            items = list(search.item_collection())
            logger.info(f"Sorgu tamamlandı. Kriterlere uygun {len(items)} adet uydu görüntüsü bulundu.")
            
            return items
            
        except Exception as e:
            logger.error(f"STAC Arama Hatası: {e}")
            raise STACQueryError(f"Sentinel-2 verileri sorgulanırken hata oluştu: {str(e)}")
