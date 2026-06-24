"""Drone görüntü analiz modülü.

İndirilen Ortofoto ve DSM GeoTIFF'lerini okur, vejetasyon indeksi (NDVI/VARI/GLI)
hesaplar, ağaç sayımı yapar, eğim/drenaj analizi gerçekleştirir.
Simülasyon modu için yapay GeoTIFF dosyaları üretebilir.
"""

import os
import numpy as np
import rasterio
from rasterio.transform import from_origin
import scipy.ndimage as ndimage
from typing import Dict, Any, Tuple, List, Optional
from src.config import logger

class DroneAnalyzer:
    """Drone veri analizleri ve coğrafi bilgi çıkarım sınıfı."""

    def __init__(self, orthophoto_path: str, dsm_path: str):
        self.orthophoto_path = orthophoto_path
        self.dsm_path = dsm_path

    def load_orthophoto(self) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Ortofoto dosyasını yükler. RGB veya RGB-NIR bandlarını okur."""
        if not os.path.exists(self.orthophoto_path):
            raise FileNotFoundError(f"Ortofoto dosyası bulunamadı: {self.orthophoto_path}")

        with rasterio.open(self.orthophoto_path) as src:
            meta = src.meta.copy()
            # Bantları oku (C, H, W)
            data = src.read()
            return data, meta

    def load_dsm(self) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Dijital Yüzey Modeli (DSM) yükler."""
        if not os.path.exists(self.dsm_path):
            raise FileNotFoundError(f"DSM dosyası bulunamadı: {self.dsm_path}")

        with rasterio.open(self.dsm_path) as src:
            meta = src.meta.copy()
            data = src.read(1)  # Tek band yükle (H, W)
            # NaN değerlerini maskeleyelim
            data = np.where(data == src.nodata, np.nan, data)
            return data, meta

    def calculate_vegetation_index(self, data: np.ndarray, index_type: str = "VARI") -> np.ndarray:
        """Kamera tipine göre vejetasyon indeksi hesaplar.
        
        Bant Sıralaması Varsayımı (RGB):
        - Band 1: Kırmızı (Red)
        - Band 2: Yeşil (Green)
        - Band 3: Mavi (Blue)
        Eğer 4 band varsa:
        - Band 4: NIR (Yakın Kızılötesi)
        """
        C, H, W = data.shape
        # Değerleri float yapıp normalize edelim (genelde 0-255 arasındadır)
        if data.dtype == np.uint8:
            data = data.astype(np.float32) / 255.0
        else:
            data = data.astype(np.float32)

        # 0'a bölme hatasını engellemek için eps
        eps = 1e-6

        if index_type == "NDVI" and C >= 4:
            # 4. band NIR, 1. band Red
            red = data[0]
            nir = data[3]
            return (nir - red) / (nir + red + eps)
        
        elif index_type == "VARI":
            # VARI = (Green - Red) / (Green + Red - Blue)
            red = data[0]
            green = data[1]
            blue = data[2]
            return (green - red) / (green + red - blue + eps)
            
        elif index_type == "GLI":
            # GLI = (2 * Green - Red - Blue) / (2 * Green + Red + Blue)
            red = data[0]
            green = data[1]
            blue = data[2]
            return (2 * green - red - blue) / (2 * green + red + blue + eps)
            
        elif index_type == "ExG":
            # ExG = 2 * Green - Red - Blue (Excess Green)
            red = data[0]
            green = data[1]
            blue = data[2]
            return 2 * green - red - blue
            
        else:
            # RGB kamera ise ve NDVI istendiyse VARI'ye fallback yap
            if index_type == "NDVI":
                logger.warning("Görüntüde NIR bandı yok. NDVI yerine VARI hesaplanıyor.")
                return self.calculate_vegetation_index(data, "VARI")
            # Genel fallback (VARI)
            return self.calculate_vegetation_index(data, "VARI")

    def count_plants(
        self,
        index_array: np.ndarray,
        threshold: float = 0.05,
        min_distance: int = 5,
        sigma: float = 1.0
    ) -> List[Tuple[int, int]]:
        """Vejetasyon indeks haritası üzerinden bitki/ağaç sayımı yapar (Local Maxima)."""
        # NaN temizleme
        clean_idx = np.nan_to_num(index_array, nan=-1.0)
        
        # Maskeleme (Eşik değer altı toprak veya gölge)
        mask = clean_idx > threshold
        
        # Gürültüyü engellemek için hafif blur uygulayalım
        blurred = ndimage.gaussian_filter(clean_idx, sigma=sigma)
        
        # Local Maxima Filtresi (scipy ndimage ile)
        # min_distance pencere boyutunu belirler
        size = 2 * min_distance + 1
        local_max = (blurred == ndimage.maximum_filter(blurred, size=size)) & mask
        
        # Nokta koordinatlarını al
        y_coords, x_coords = np.where(local_max)
        
        peaks = list(zip(x_coords, y_coords))
        logger.info(f"Ağaç/Bitki sayımı tamamlandı: Toplam {len(peaks)} adet tespit edildi.")
        return peaks

    def analyze_topography(self, dsm: np.ndarray, pixel_resolution: float = 0.05) -> Tuple[np.ndarray, np.ndarray]:
        """DSM üzerinden eğim (slope) ve drenaj birikim çukurlarını analiz eder."""
        # NaN değerlerini enterpole edelim
        nan_mask = np.isnan(dsm)
        dsm_clean = dsm.copy()
        if nan_mask.any():
            dsm_clean = np.nan_to_num(dsm_clean, nan=np.nanmean(dsm))
        
        # Eğim hesabı (gradyan ile)
        dy, dx = np.gradient(dsm_clean, pixel_resolution)
        slope = np.arctan(np.sqrt(dx**2 + dy**2)) * (180.0 / np.pi)
        
        # Basit çukur (depression) drenaj analizi
        # Lokal minimum noktaları su birikintisi potansiyeline sahiptir
        size = 15
        local_min = (dsm_clean == ndimage.minimum_filter(dsm_clean, size=size))
        # Kenarları ve dümdüz alanları çıkaralım
        local_min[:5, :] = False
        local_min[-5:, :] = False
        local_min[:, :5] = False
        local_min[:, -5:] = False
        
        return slope, local_min

    # ═══════════════════════════════════════════════════════════
    #  Mock / Simulation Data Generator
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def generate_mock_drone_data(
        output_dir: str,
        lat: float,
        lon: float,
        size_px: int = 512,
        res_m: float = 0.05
    ) -> Tuple[str, str]:
        """Test amaçlı yapay bir ortofoto (RGB) ve DSM GeoTIFF'i üretir."""
        os.makedirs(output_dir, exist_ok=True)
        
        ortho_path = os.path.join(output_dir, "sim_orthophoto.tif")
        dsm_path = os.path.join(output_dir, "sim_dsm.tif")

        # 1. Koordinat dönüşüm transformu (5cm çözünürlük)
        transform = from_origin(lon, lat, res_m / 111320.0, res_m / 110540.0)

        # 2. Yapay veri üretimi (Hills, Trees, Soil)
        # Arka plan toprak (açık kahverengi/sarı)
        rgb = np.zeros((3, size_px, size_px), dtype=np.uint8)
        rgb[0, :, :] = 139  # Red
        rgb[1, :, :] = 115  # Green
        rgb[2, :, :] = 85   # Blue
        
        # DSM (Yükseklik modeli) - Hafif eğimli arazi
        x = np.linspace(0, 10, size_px)
        y = np.linspace(0, 10, size_px)
        X, Y = np.meshgrid(x, y)
        dsm = 100.0 + 0.5 * X + 0.2 * Y + np.sin(X)*0.2  # Eğimli arazi tabanı
        
        # Rastgele ağaçlar yerleştirelim (Yeşil daireler)
        # Ağaçların olduğu yerlerde DSM yükselecek, RGB yeşillenecek
        np.random.seed(42)
        n_trees = 35
        for _ in range(n_trees):
            cx = np.random.randint(40, size_px - 40)
            cy = np.random.randint(40, size_px - 40)
            radius = np.random.randint(15, 30)
            tree_height = np.random.uniform(2.0, 4.5)
            
            # Maske oluştur
            Y_grid, X_grid = np.ogrid[:size_px, :size_px]
            dist_from_center = np.sqrt((X_grid - cx)**2 + (Y_grid - cy)**2)
            tree_mask = dist_from_center <= radius
            
            # Ağaç rengi (Yeşil varyasyonları)
            g_val = np.random.randint(120, 180)
            r_val = np.random.randint(30, 70)
            b_val = np.random.randint(20, 50)
            
            # Yumuşak geçişli tepe
            h_profile = tree_height * np.cos((dist_from_center / radius) * (np.pi / 2))
            h_profile = np.where(tree_mask, h_profile, 0.0)
            
            # RGB uygula
            rgb[0, tree_mask] = r_val
            rgb[1, tree_mask] = g_val
            rgb[2, tree_mask] = b_val
            
            # DSM yükselt
            dsm[tree_mask] += h_profile[tree_mask]

        # 3. Ortofotoyu yazdır
        with rasterio.open(
            ortho_path, 'w',
            driver='GTiff',
            height=size_px, width=size_px,
            count=3, dtype=np.uint8,
            crs='EPSG:4326',
            transform=transform
        ) as dst:
            dst.write(rgb)

        # 4. DSM'i yazdır
        with rasterio.open(
            dsm_path, 'w',
            driver='GTiff',
            height=size_px, width=size_px,
            count=1, dtype=np.float32,
            crs='EPSG:4326',
            transform=transform
        ) as dst:
            dst.write(dsm.astype(np.float32), 1)

        logger.info(f"Simülasyon GeoTIFF'leri başarıyla oluşturuldu: {ortho_path}, {dsm_path}")
        return ortho_path, dsm_path
