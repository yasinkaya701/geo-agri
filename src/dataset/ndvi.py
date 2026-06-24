"""Spektral indeks hesaplama, zaman serisi düzeltme ve fenoloji çıkarım modülü.

Desteklenen indeksler: NDVI, NDWI, SAVI, EVI
Ek özellikler:
    - Savitzky-Golay temporal smoothing
    - Whittaker ağırlıklı düzeltme
    - Fenoloji metrikleri (SOS, EOS, Peak, GSL)
"""

import numpy as np
import xarray as xr
import pandas as pd
from typing import Union, Optional, Dict, Any
from scipy.signal import savgol_filter
from scipy.interpolate import interp1d
from src.config import logger


# ═══════════════════════════════════════════════════════════
#  1. SPECTRAL INDEX CALCULATIONS
# ═══════════════════════════════════════════════════════════

def _safe_ratio(
    numerator: Union[xr.DataArray, np.ndarray],
    denominator: Union[xr.DataArray, np.ndarray],
    clip_min: float = -1.0,
    clip_max: float = 1.0,
) -> Union[xr.DataArray, np.ndarray]:
    """Sıfıra bölme korumalı oran hesabı."""
    if isinstance(numerator, xr.DataArray):
        result = numerator / denominator.where(denominator > 0)
        return result.clip(clip_min, clip_max)
    else:
        with np.errstate(divide="ignore", invalid="ignore"):
            result = numerator / np.where(denominator > 0, denominator, np.nan)
            return np.clip(result, clip_min, clip_max)


def calculate_ndvi(
    red: Union[xr.DataArray, np.ndarray],
    nir: Union[xr.DataArray, np.ndarray],
) -> Union[xr.DataArray, np.ndarray]:
    """Normalized Difference Vegetation Index.

    NDVI = (NIR − Red) / (NIR + Red)
    Aralık: [−1, 1]  •  Sağlıklı bitki > 0.5
    """
    return _safe_ratio(nir - red, nir + red)


def calculate_ndwi(
    green: Union[xr.DataArray, np.ndarray],
    nir: Union[xr.DataArray, np.ndarray],
) -> Union[xr.DataArray, np.ndarray]:
    """Normalized Difference Water Index.

    NDWI = (Green − NIR) / (Green + NIR)
    Aralık: [−1, 1]  •  Su > 0.3
    """
    return _safe_ratio(green - nir, green + nir)


def calculate_savi(
    red: Union[xr.DataArray, np.ndarray],
    nir: Union[xr.DataArray, np.ndarray],
    L: float = 0.5,
) -> Union[xr.DataArray, np.ndarray]:
    """Soil Adjusted Vegetation Index.

    SAVI = ((NIR − Red) × (1 + L)) / (NIR + Red + L)
    L=0.5 orta yoğunluklu vejetasyon için optimal.
    """
    return _safe_ratio((nir - red) * (1.0 + L), nir + red + L)


def calculate_evi(
    blue: Union[xr.DataArray, np.ndarray],
    red: Union[xr.DataArray, np.ndarray],
    nir: Union[xr.DataArray, np.ndarray],
    G: float = 2.5,
    C1: float = 6.0,
    C2: float = 7.5,
    L_evi: float = 1.0,
) -> Union[xr.DataArray, np.ndarray]:
    """Enhanced Vegetation Index.

    EVI = G × (NIR − Red) / (NIR + C1×Red − C2×Blue + L)
    Atmosferik ve toprak etkisini minimize eder.
    """
    denominator = nir + C1 * red - C2 * blue + L_evi
    return _safe_ratio(G * (nir - red), denominator)


# ═══════════════════════════════════════════════════════════
#  2. TIME SERIES SMOOTHING & INTERPOLATION
# ═══════════════════════════════════════════════════════════

def interpolate_ndvi_series(
    df: pd.DataFrame,
    date_col: str = "Date",
    ndvi_col: str = "Mean_NDVI",
) -> pd.DataFrame:
    """Eksik (NaN) zaman serisi değerlerini doğrusal enterpolasyonla doldurur."""
    df_sorted = df.sort_values(by=date_col).copy()

    original_index = df_sorted.index
    df_sorted[date_col] = pd.to_datetime(df_sorted[date_col])
    df_sorted = df_sorted.set_index(date_col)

    df_sorted[ndvi_col] = df_sorted[ndvi_col].interpolate(method="time")
    df_sorted[ndvi_col] = df_sorted[ndvi_col].bfill().ffill()

    df_sorted = df_sorted.reset_index()
    df_sorted.index = original_index
    df_sorted[date_col] = df_sorted[date_col].dt.strftime("%Y-%m-%d")

    return df_sorted


def savitzky_golay_smooth(
    values: np.ndarray,
    window_length: int = 7,
    polyorder: int = 2,
    iterations: int = 2,
) -> np.ndarray:
    """Savitzky-Golay filtresi ile zaman serisi düzeltme.

    İteratif uygulama: her adımda orijinalden düşük olan noktalar
    yukarı çekilir (upper envelope yaklaşımı - bulut kontaminasyonu
    her zaman NDVI'ı düşürdüğü için).

    Args:
        values: 1D zaman serisi (T,)
        window_length: Filtre pencere uzunluğu (tek sayı olmalı)
        polyorder: Polinom derecesi
        iterations: İterasyon sayısı (daha fazla = daha düzgün)

    Returns:
        Düzeltilmiş 1D zaman serisi
    """
    if len(values) < window_length:
        window_length = max(3, len(values) | 1)  # en yakın tek sayıya yuvarla
    if window_length % 2 == 0:
        window_length += 1
    if polyorder >= window_length:
        polyorder = window_length - 1

    result = values.copy().astype(np.float64)
    nan_mask = np.isnan(result)

    # NaN'ları enterpolasyonla doldur
    if nan_mask.any():
        valid_idx = np.where(~nan_mask)[0]
        if len(valid_idx) >= 2:
            interp_fn = interp1d(
                valid_idx, result[valid_idx], kind="linear",
                fill_value="extrapolate", bounds_error=False
            )
            result[nan_mask] = interp_fn(np.where(nan_mask)[0])
        elif len(valid_idx) == 1:
            result[nan_mask] = result[valid_idx[0]]
        else:
            return result

    # İteratif SG: bulut kontaminasyonu düzeltme
    for _ in range(iterations):
        smoothed = savgol_filter(result, window_length, polyorder)
        # Orijinalden düşükse (bulut etkisi), düzeltilmiş değeri kullan
        result = np.maximum(result, smoothed)

    # Son bir düzeltme
    result = savgol_filter(result, window_length, polyorder)
    return result


def smooth_time_series_2d(
    cube: np.ndarray,
    window_length: int = 7,
    polyorder: int = 2,
) -> np.ndarray:
    """2D uzamsal veri küpünün her pikselinin zaman serisine SG filtresi uygular.

    Args:
        cube: (T, H, W) boyutlu 3D dizi
        window_length: SG pencere uzunluğu
        polyorder: Polinom derecesi

    Returns:
        Düzeltilmiş (T, H, W) küp
    """
    T, H, W = cube.shape
    result = cube.copy()

    for i in range(H):
        for j in range(W):
            pixel_ts = cube[:, i, j]
            if np.all(np.isnan(pixel_ts)) or np.all(pixel_ts == 0):
                continue
            result[:, i, j] = savitzky_golay_smooth(pixel_ts, window_length, polyorder)

    return result


# ═══════════════════════════════════════════════════════════
#  3. PHENOLOGY EXTRACTION
# ═══════════════════════════════════════════════════════════

def extract_phenology(
    ndvi_series: np.ndarray,
    dates: Optional[list] = None,
    threshold_ratio: float = 0.5,
) -> Dict[str, Any]:
    """Bir piksel veya alan ortalamasının NDVI zaman serisinden
    temel fenoloji metriklerini çıkarır.

    Args:
        ndvi_series: 1D NDVI zaman serisi (T,)
        dates: Tarih string listesi (opsiyonel, T uzunluğunda)
        threshold_ratio: SOS/EOS eşik oranı (amplitude'un bu kadarı)

    Returns:
        dict ile:
            - peak_ndvi: Maksimum NDVI değeri
            - peak_idx: Maksimum NDVI'ın indeksi
            - peak_date: Pik tarihi (eğer dates verilmişse)
            - sos_idx: Start of Season indeksi
            - sos_date: Mevsim başlangıç tarihi
            - eos_idx: End of Season indeksi
            - eos_date: Mevsim bitiş tarihi
            - gsl: Growing Season Length (gün veya adım cinsinden)
            - amplitude: Pik - taban farkı
            - base_ndvi: Taban (minimum) NDVI
            - seasonal_integral: Mevsimsel NDVI integrali (toplam biyokütle göstergesi)
    """
    clean = np.nan_to_num(ndvi_series, nan=0.0)
    T = len(clean)

    if T < 3:
        return _empty_phenology()

    # Smooth
    smoothed = savitzky_golay_smooth(clean, window_length=min(7, T | 1), polyorder=min(2, (T | 1) - 1))

    # Temel metrikler
    peak_idx = int(np.argmax(smoothed))
    peak_ndvi = float(smoothed[peak_idx])
    base_ndvi = float(np.min(smoothed))
    amplitude = peak_ndvi - base_ndvi

    if amplitude < 0.05:
        # Anlamlı vejetasyon değişimi yok
        return _empty_phenology(peak_ndvi=peak_ndvi, base_ndvi=base_ndvi)

    # SOS ve EOS eşiği
    threshold = base_ndvi + amplitude * threshold_ratio

    # SOS: Peak'den sola doğru ilk threshold geçişi
    sos_idx = 0
    for i in range(peak_idx, -1, -1):
        if smoothed[i] < threshold:
            sos_idx = i
            break

    # EOS: Peak'den sağa doğru ilk threshold geçişi
    eos_idx = T - 1
    for i in range(peak_idx, T):
        if smoothed[i] < threshold:
            eos_idx = i
            break

    # Growing Season Length
    gsl = eos_idx - sos_idx

    # Mevsimsel integral (eşik üstü NDVI toplamı — biyokütle göstergesi)
    season_values = smoothed[sos_idx : eos_idx + 1]
    seasonal_integral = float(np.trapz(np.maximum(season_values - base_ndvi, 0)))

    result = {
        "peak_ndvi": peak_ndvi,
        "peak_idx": peak_idx,
        "base_ndvi": base_ndvi,
        "amplitude": amplitude,
        "sos_idx": sos_idx,
        "eos_idx": eos_idx,
        "gsl": gsl,
        "seasonal_integral": seasonal_integral,
    }

    # Tarih bilgisi varsa ekle
    if dates is not None and len(dates) == T:
        result["peak_date"] = dates[peak_idx]
        result["sos_date"] = dates[sos_idx]
        result["eos_date"] = dates[eos_idx]

    return result


def _empty_phenology(peak_ndvi: float = 0.0, base_ndvi: float = 0.0) -> Dict[str, Any]:
    """Boş/geçersiz fenoloji sonucu."""
    return {
        "peak_ndvi": peak_ndvi,
        "peak_idx": 0,
        "base_ndvi": base_ndvi,
        "amplitude": 0.0,
        "sos_idx": 0,
        "eos_idx": 0,
        "gsl": 0,
        "seasonal_integral": 0.0,
    }


def compute_phenology_map(
    ndvi_cube: np.ndarray,
    dates: Optional[list] = None,
) -> Dict[str, np.ndarray]:
    """3D NDVI küpünün (T, H, W) her pikselinden fenoloji haritaları çıkarır.

    Returns:
        dict of 2D maps:
            - peak_ndvi: (H, W) pik NDVI haritası
            - sos_idx: (H, W) mevsim başlangıç indeks haritası
            - eos_idx: (H, W) mevsim bitiş indeks haritası
            - gsl: (H, W) büyüme sezonu uzunluğu haritası
            - amplitude: (H, W) amplitude haritası
            - seasonal_integral: (H, W) mevsimsel integral haritası
    """
    T, H, W = ndvi_cube.shape

    maps = {
        "peak_ndvi": np.zeros((H, W), dtype=np.float32),
        "sos_idx": np.zeros((H, W), dtype=np.int32),
        "eos_idx": np.zeros((H, W), dtype=np.int32),
        "gsl": np.zeros((H, W), dtype=np.int32),
        "amplitude": np.zeros((H, W), dtype=np.float32),
        "seasonal_integral": np.zeros((H, W), dtype=np.float32),
    }

    for i in range(H):
        for j in range(W):
            pixel_ts = ndvi_cube[:, i, j]
            if np.all(np.isnan(pixel_ts)) or np.all(pixel_ts == 0):
                continue
            pheno = extract_phenology(pixel_ts, dates=dates)
            for key in maps:
                maps[key][i, j] = pheno[key]

    return maps
