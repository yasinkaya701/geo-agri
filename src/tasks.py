import os
import json
import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
from celery import Celery
from src.config import REDIS_URL, logger
from src.database import DatabaseManager
from src.pipeline import SatelliteDataFactoryPipeline

# Celery Uygulaması Yapılandırması
celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Istanbul",
    enable_utc=True
)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def process_historical_pipeline_task(self, field_id: str, start_year: int = 2016, end_year: int = 2026, temporal_resolution: str = "15 Günlük Periyotlar"):
    """
    Asenkron 10 yıllık Sentinel-2 zaman serisi veri küpü üretim görevi.
    İşlemleri yıllık döngüler halinde parçalayarak RAM tüketimini optimize eder.
    """
    logger.info(f"Asenkron veri küpü oluşturma görevi başladı. Arazi ID: {field_id}, Yıllar: {start_year}-{end_year}, Çözünürlük: {temporal_resolution}")

    # 1. Veritabanından geometri bilgisini çek
    conn = None
    cur = None
    field_row = None
    try:
        conn = DatabaseManager.get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor if hasattr(psycopg2.extras, "RealDictCursor") else None)
        # RealDictCursor olmaması durumuna karşı normal cursor ile dict olarak parse edelim
        cur.execute("SELECT name, ST_AsGeoJSON(geom) as geom_json FROM fields WHERE id = %s;", (field_id,))
        field_row = cur.fetchone()
    except Exception as e:
        logger.error(f"Veritabanı okuma hatası: {e}")
        return {"status": "FAILED", "error": f"Database read failed: {str(e)}"}
    finally:
        if cur:
            cur.close()
        if conn:
            DatabaseManager.release_connection(conn)


    if not field_row:
        logger.error(f"Arazi veritabanında bulunamadı: {field_id}")
        return {"status": "FAILED", "error": f"Field {field_id} not found in database"}

    # Geometri verisini oku
    geom_json = field_row["geom_json"] if isinstance(field_row, dict) else field_row[1]
    name = field_row["name"] if isinstance(field_row, dict) else field_row[0]
    
    if isinstance(geom_json, str):
        geometry_geojson = json.loads(geom_json)
    else:
        geometry_geojson = geom_json

    # 2. Pipeline'ı başlat
    pipeline = SatelliteDataFactoryPipeline(geometry_geojson=geometry_geojson)
    
    years = list(range(start_year, end_year + 1))
    total_years = len(years)
    
    master_cube_list = []
    historical_scalar_trends = {}
    historical_dates = {}
    weight_mask = None

    # Çıktı klasörünü ayarla
    storage_directory = f"/tmp/data_factory_outputs/{field_id}"
    os.makedirs(storage_directory, exist_ok=True)
    
    # 3. Yıllık döngü
    for idx, year in enumerate(years):
        progress_percentage = int((idx / total_years) * 100)
        self.update_state(
            state="PROGRESS",
            meta={
                "current_year": year,
                "progress": progress_percentage,
                "status_message": f"{year} yılı büyüme sezonu NDVI matrisi hesaplanıyor."
            }
        )
        
        try:
            year_cube, year_trends, year_weight, year_dates = pipeline.process_seasonal_cube(year, temporal_resolution=temporal_resolution)
            master_cube_list.append(year_cube)
            historical_scalar_trends[str(year)] = year_trends
            historical_dates[str(year)] = year_dates
            if weight_mask is None:
                weight_mask = year_weight

            # Yıllık trend ve matris bilgilerini veritabanına kaydet
            conn = DatabaseManager.get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO field_historical_metrics (field_id, year, ndvi_trends, matrix_path)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (field_id, year)
                DO UPDATE SET ndvi_trends = EXCLUDED.ndvi_trends, matrix_path = EXCLUDED.matrix_path, processed_at = NOW();
                """,
                (field_id, year, json.dumps({"trends": year_trends, "dates": year_dates}), f"{storage_directory}/cube_latest.npy")
            )
            conn.commit()
            cur.close()
            DatabaseManager.release_connection(conn)
            
        except Exception as e:
            logger.error(f"{year} yılı işlenirken kritik hata: {str(e)}")
            # Hata durumunda boş matris ile zaman serisi bütünlüğünü koru
            steps = 6 if "AYLIK" in temporal_resolution.upper() else (1 if "HAM" in temporal_resolution.upper() else 12)
            master_cube_list.append(np.zeros((steps, 4, 64, 64), dtype=np.float32))
            historical_scalar_trends[str(year)] = [0.0] * steps
            if "HAM" in temporal_resolution.upper():
                historical_dates[str(year)] = [f"{year}-06-01"]
            else:
                historical_dates[str(year)] = [pd.to_datetime(t).strftime("%Y-%m-%d") for t in pd.date_range(start=f"{year}-03-01", end=f"{year}-08-31", periods=steps)]

    # 4. Çok boyutlu veri küpünü (5D) istifle
    # Farklı yılların boyutları (özellikle HAM modunda) farklı olabileceği için maksimum adıma göre pedleyelim
    max_steps = max(cube.shape[0] for cube in master_cube_list)
    padded_cubes = []
    for cube in master_cube_list:
        curr_steps = cube.shape[0]
        if curr_steps < max_steps:
            pad_width = ((0, max_steps - curr_steps), (0, 0), (0, 0), (0, 0))
            padded = np.pad(cube, pad_width, mode='constant', constant_values=np.nan)
            padded_cubes.append(padded)
        else:
            padded_cubes.append(cube)
            
    final_4d_cube = np.stack(padded_cubes, axis=0)
    
    # 5. Disk / S3 Sürümleme Alanına Kaydet
    matrix_filepath = os.path.join(storage_directory, "cube_latest.npy")
    np.save(matrix_filepath, final_4d_cube)
    
    # Spektral Ağırlık Maskesini de kaydet (AI eğitimi için)
    if weight_mask is not None:
        weight_filepath = os.path.join(storage_directory, "weight_mask.npy")
        np.save(weight_filepath, weight_mask)

    logger.info(f"Tarihsel Veri Fabrikası başarıyla tamamlandı. Kayıt yeri: {matrix_filepath}")
    
    return {
        "status": "COMPLETED",
        "field_id": field_id,
        "name": name,
        "cube_shape": list(final_4d_cube.shape),
        "matrix_path": matrix_filepath,
        "trends": historical_scalar_trends,
        "dates": historical_dates
    }
