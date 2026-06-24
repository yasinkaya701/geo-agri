import requests
from typing import List, Dict, Any, Optional
from src.config import TKGM_MEGSIS_URL, DEFAULT_HEADERS, logger
from src.exceptions import TKGMError

class MegsisClient:
    """TKGM MEGSIS API istemcisi.
    
    Türkiye genelindeki il, ilçe, mahalle hiyerarşisini çeker ve ada/parsel bazlı
    resmi tarla geometrilerini sorgular.
    """
    
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _get(self, endpoint: str) -> Any:
        """API istek yardımcısı. Hata kontrolü ve loglama yapar."""
        url = f"{TKGM_MEGSIS_URL}/{endpoint}"
        try:
            logger.info(f"TKGM API İsteği gönderiliyor: {url}")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            logger.error(f"TKGM HTTP Hatası: {e}")
            if e.response is not None and e.response.status_code == 404:
                raise TKGMError("Girdiğiniz Ada/Parsel bu mahallede bulunamadı. Lütfen numaraları kontrol edin veya harita üzerinden çizmeyi deneyin.")
            raise TKGMError(f"TKGM servisi hata döndürdü (Kod: {e.response.status_code if e.response else 'Bilinmeyen'}).")
        except requests.RequestException as e:
            logger.error(f"TKGM Bağlantı Hatası: {e}")
            raise TKGMError(f"TKGM servisine bağlanılamadı. İnternet bağlantınızı veya servis durumunu kontrol edin. Hata: {str(e)}")

    def get_provinces(self) -> List[Dict[str, Any]]:
        """Tüm illerin listesini [{ 'id': int, 'name': str }] formatında çeker."""
        data = self._get("idariYapi/ilListe")
        provinces = []
        if "features" in data:
            for feat in data["features"]:
                props = feat.get("properties", {})
                p_id = props.get("id")
                p_name = props.get("text")
                if p_id is not None and p_name:
                    provinces.append({"id": int(p_id), "name": str(p_name).strip()})
        # İlleri alfabetik sıralayalım
        provinces.sort(key=lambda x: x["name"])
        return provinces

    def get_districts(self, province_id: int) -> List[Dict[str, Any]]:
        """Seçilen il id'sine göre ilçelerin listesini çeker."""
        data = self._get(f"idariYapi/ilceListe/{province_id}")
        districts = []
        if "features" in data:
            for feat in data["features"]:
                props = feat.get("properties", {})
                d_id = props.get("id")
                d_name = props.get("text")
                if d_id is not None and d_name:
                    districts.append({"id": int(d_id), "name": str(d_name).strip()})
        districts.sort(key=lambda x: x["name"])
        return districts

    def get_neighborhoods(self, district_id: int) -> List[Dict[str, Any]]:
        """Seçilen ilçe id'sine göre mahallelerin listesini çeker."""
        data = self._get(f"idariYapi/mahalleListe/{district_id}")
        neighborhoods = []
        if "features" in data:
            for feat in data["features"]:
                props = feat.get("properties", {})
                m_id = props.get("id")
                m_name = props.get("text")
                if m_id is not None and m_name:
                    neighborhoods.append({"id": int(m_id), "name": str(m_name).strip()})
        neighborhoods.sort(key=lambda x: x["name"])
        return neighborhoods

    def get_parcel(self, neighborhood_id: int, ada: str, parsel: str) -> Dict[str, Any]:
        """Verilen mahalle, ada ve parsel numarasına ait resmi sınır poligonunu ve öznitelikleri çeker.
        
        Dönen değer GeoJSON Feature formatındadır.
        """
        # Ada/parsel bazen sadece sayı olabildiği gibi string de olabilir
        # URL'e eklemeden önce temizleyelim
        ada_clean = str(ada).strip()
        parsel_clean = str(parsel).strip()
        
        if not ada_clean or not parsel_clean:
            raise TKGMError("Ada ve parsel bilgileri boş bırakılamaz.")
            
        data = self._get(f"parsel/{neighborhood_id}/{ada_clean}/{parsel_clean}")
        
        # Geçerli bir geometri dönüp dönmediğini kontrol edelim
        if not data or "geometry" not in data or data["geometry"] is None:
            logger.warning(f"Belirtilen kadastro kaydı bulunamadı: Mahalle: {neighborhood_id}, Ada/Parsel: {ada_clean}/{parsel_clean}")
            raise TKGMError(f"Belirtilen ada/parsel ({ada_clean}/{parsel_clean}) için kadastro geometrisi bulunamadı.")
            
        return data

    def get_parcel_by_coordinates(self, lat: float, lon: float) -> Dict[str, Any]:
        """Verilen enlem ve boylam koordinatına ait resmi sınır poligonunu ve öznitelikleri sorgular.
        
        Dönen değer GeoJSON Feature formatındadır.
        """
        try:
            logger.info(f"Koordinata göre parsel sorgulanıyor: Enlem={lat}, Boylam={lon}")
            data = self._get(f"parsel/{lat}/{lon}/")
            
            # Geçerli bir geometri dönüp dönmediğini kontrol edelim
            if not data or "geometry" not in data or data["geometry"] is None:
                logger.warning(f"Belirtilen koordinatta kadastro kaydı bulunamadı: Enlem={lat}, Boylam={lon}")
                raise TKGMError(f"Belirtilen koordinatlarda ({lat}, {lon}) resmi kadastro geometrisi bulunamadı.")
                
            return data
        except TKGMError:
            raise
        except Exception as e:
            logger.error(f"Koordinat sorgu hatası: {e}")
            raise TKGMError(f"Koordinata göre parsel sorgusu başarısız: {str(e)}")

