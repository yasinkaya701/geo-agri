import logging
import os
from pathlib import Path

# Proje Kök Dizini
ROOT_DIR = Path(__file__).resolve().parent.parent

# Cache ve Veri Saklama Dizinleri
CACHE_DIR = ROOT_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# API Endpoint'leri
PLANETARY_COMPUTER_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
TKGM_MEGSIS_URL = "https://cbsapi.tkgm.gov.tr/megsiswebapi.v3/api"

# Veritabanı ve Redis Konfigürasyonu
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://yasinkaya@localhost:5432/agtech_db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# HTTP İstek Başlıkları (TKGM ve STAC için)
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://parselsorgu.tkgm.gov.tr/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Logger Konfigürasyonu
def setup_logger(name: str = "tarim_uydu") -> logging.Logger:
    """Uygulama genelinde standart renkli loglama altyapısını kurar."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Konsol Handler'ı
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Log formatı
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    return logger

logger = setup_logger()
