import numpy as np
import pandas as pd
import xarray as xr
import io
from typing import List, Dict, Any, Tuple
from src.config import logger
from src.exceptions import RasterProcessingError
from src.dataset.ndvi import calculate_ndwi, calculate_savi, calculate_evi

def generate_field_average_df(processed_data: List[Dict[str, Any]]) -> pd.DataFrame:
    """İşlenmiş tarih bazlı uydu görüntülerinden ortalama değerleri çıkararak
    alan genelinde zaman serisi DataFrame'i üretir.
    """
    records = []
    for entry in processed_data:
        date = entry["date"]
        cloud_percent = entry["cloud_percent"]
        bands = entry["bands"]
        
        blue = bands["blue"]
        green = bands["green"]
        red = bands["red"]
        nir = bands["nir"]
        ndvi = bands["ndvi"]
        
        # Ek spektral indeksleri hesapla
        ndwi = calculate_ndwi(green, nir)
        savi = calculate_savi(red, nir)
        evi = calculate_evi(blue, red, nir)
        
        # Sadece NaN olmayan (tarla içi ve bulutsuz) değerlerin ortalamalarını alalım
        mean_blue = float(blue.mean().item())
        mean_green = float(green.mean().item())
        mean_red = float(red.mean().item())
        mean_nir = float(nir.mean().item())
        
        mean_ndvi = float(ndvi.mean().item())
        min_ndvi = float(ndvi.min().item())
        max_ndvi = float(ndvi.max().item())
        std_ndvi = float(ndvi.std().item())
        
        mean_ndwi = float(ndwi.mean().item())
        min_ndwi = float(ndwi.min().item())
        max_ndwi = float(ndwi.max().item())
        std_ndwi = float(ndwi.std().item())
        
        mean_savi = float(savi.mean().item())
        min_savi = float(savi.min().item())
        max_savi = float(savi.max().item())
        std_savi = float(savi.std().item())
        
        mean_evi = float(evi.mean().item())
        min_evi = float(evi.min().item())
        max_evi = float(evi.max().item())
        std_evi = float(evi.std().item())
        
        records.append({
            "Date": date,
            "Field_Cloud_Percent": cloud_percent,
            "Mean_Blue": mean_blue,
            "Mean_Green": mean_green,
            "Mean_Red": mean_red,
            "Mean_NIR": mean_nir,
            "Mean_NDVI": mean_ndvi,
            "Min_NDVI": min_ndvi,
            "Max_NDVI": max_ndvi,
            "Std_NDVI": std_ndvi,
            "Mean_NDWI": mean_ndwi,
            "Min_NDWI": min_ndwi,
            "Max_NDWI": max_ndwi,
            "Std_NDWI": std_ndwi,
            "Mean_SAVI": mean_savi,
            "Min_SAVI": min_savi,
            "Max_SAVI": max_savi,
            "Std_SAVI": std_savi,
            "Mean_EVI": mean_evi,
            "Min_EVI": min_evi,
            "Max_EVI": max_evi,
            "Std_EVI": std_evi
        })
        
    df = pd.DataFrame(records)
    # Tarihe göre sıralayalım
    if not df.empty:
        df = df.sort_values(by="Date").reset_index(drop=True)
    return df

def generate_pixel_level_df(processed_data: List[Dict[str, Any]]) -> pd.DataFrame:
    """Tüm tarihlerdeki tarla piksellerini düzleştirerek (flatten)
    piksel düzeyinde zaman serisi DataFrame'i oluşturur.
    
    Format: [Date, Latitude, Longitude, Blue, Green, Red, NIR, NDVI, NDWI, SAVI, EVI]
    """
    all_dfs = []
    for entry in processed_data:
        date = entry["date"]
        bands = entry["bands"]
        
        blue = bands["blue"]
        green = bands["green"]
        red = bands["red"]
        nir = bands["nir"]
        ndvi = bands["ndvi"]
        
        # Ek spektral indeksleri hesapla
        ndwi = calculate_ndwi(green, nir)
        savi = calculate_savi(red, nir)
        evi = calculate_evi(blue, red, nir)
        
        # xarray'i pandas DataFrame'e dönüştür
        df_blue = blue.to_dataframe(name="Blue")
        df_green = green.to_dataframe(name="Green")
        df_red = red.to_dataframe(name="Red")
        df_nir = nir.to_dataframe(name="NIR")
        df_ndvi = ndvi.to_dataframe(name="NDVI")
        df_ndwi = ndwi.to_dataframe(name="NDWI")
        df_savi = savi.to_dataframe(name="SAVI")
        df_evi = evi.to_dataframe(name="EVI")
        
        # İndekse göre birleştirme
        df_combined = df_blue.join(df_green).join(df_red).join(df_nir).join(df_ndvi).join(df_ndwi).join(df_savi).join(df_evi)
        
        # Sadece tarla içinde kalan (NaN olmayan) pikselleri filtrele
        df_combined = df_combined.dropna()
        
        if not df_combined.empty:
            df_combined = df_combined.reset_index()
            # Kolon adlarını standardize edelim
            df_combined = df_combined.rename(columns={"x": "Longitude", "y": "Latitude"})
            df_combined.insert(0, "Date", date)
            all_dfs.append(df_combined)
            
    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)
        final_df = final_df.sort_values(by=["Date", "Latitude", "Longitude"]).reset_index(drop=True)
        return final_df
    return pd.DataFrame()

def export_to_npz(processed_data: List[Dict[str, Any]]) -> Tuple[bytes, str]:
    """İşlenmiş uydu görüntülerini 3D uzamsal-zamansal numpy dizileri halinde sıkıştırır
    ve Streamlit üzerinden indirilmeye hazır byte verisi olarak döner.
    """
    if not processed_data:
        raise RasterProcessingError("Dışa aktarılacak veri bulunamadı.")
        
    # Tarihe göre sıralayalım
    sorted_data = sorted(processed_data, key=lambda x: x["date"])
    
    dates = [entry["date"] for entry in sorted_data]
    cloud_percents = [entry["cloud_percent"] for entry in sorted_data]
    
    # Tüm görüntüler aynı tarla bounding box'ına sahip olduğu için H ve W boyutları aynıdır
    first_bands = sorted_data[0]["bands"]
    h, w = first_bands["red"].shape
    
    t = len(sorted_data)
    
    # Boş 3D diziler oluştur (Zaman, Yükseklik, Genişlik)
    blue_stack = np.zeros((t, h, w), dtype=np.float32)
    green_stack = np.zeros((t, h, w), dtype=np.float32)
    red_stack = np.zeros((t, h, w), dtype=np.float32)
    nir_stack = np.zeros((t, h, w), dtype=np.float32)
    ndvi_stack = np.zeros((t, h, w), dtype=np.float32)
    ndwi_stack = np.zeros((t, h, w), dtype=np.float32)
    savi_stack = np.zeros((t, h, w), dtype=np.float32)
    evi_stack = np.zeros((t, h, w), dtype=np.float32)
    scl_stack = np.zeros((t, h, w), dtype=np.uint8)
    
    for i, entry in enumerate(sorted_data):
        bands = entry["bands"]
        blue_stack[i] = bands["blue"].values
        green_stack[i] = bands["green"].values
        red_stack[i] = bands["red"].values
        nir_stack[i] = bands["nir"].values
        ndvi_stack[i] = bands["ndvi"].values
        scl_stack[i] = bands["scl"].values
        
        # Ek spektral indeksleri hesapla
        ndwi_stack[i] = calculate_ndwi(bands["green"], bands["nir"]).values
        savi_stack[i] = calculate_savi(bands["red"], bands["nir"]).values
        evi_stack[i] = calculate_evi(bands["blue"], bands["red"], bands["nir"]).values
        
    buffer = io.BytesIO()
    np.savez_compressed(
        buffer,
        dates=np.array(dates, dtype="S10"),
        cloud_percents=np.array(cloud_percents, dtype=np.float32),
        blue_stack=blue_stack,
        green_stack=green_stack,
        red_stack=red_stack,
        nir_stack=nir_stack,
        ndvi_stack=ndvi_stack,
        ndwi_stack=ndwi_stack,
        savi_stack=savi_stack,
        evi_stack=evi_stack,
        scl_stack=scl_stack,
        shape=np.array([t, h, w], dtype=np.int32)
    )
    
    buffer.seek(0)
    return buffer.getvalue(), "tarla_uydu_veri_seti.npz"
