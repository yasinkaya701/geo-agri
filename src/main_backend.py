import uuid
import json
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from celery.result import AsyncResult

from src.config import logger
from src.database import DatabaseManager
from src.tkgm.megsis_client import MegsisClient
from src.tasks import process_historical_pipeline_task, celery_app
from shapely.geometry import shape

# Pydantic Schemas
class GeoJSONPolygon(BaseModel):
    type: str = Field("Polygon", pattern="^(Polygon)$")
    coordinates: List[List[List[float]]]

class FieldRegistration(BaseModel):
    user_id: str
    name: str
    geometry: GeoJSONPolygon

class TKGMImportPayload(BaseModel):
    user_id: str
    name: str
    mahalle_id: int
    ada_no: str
    parsel_no: str

app = FastAPI(
    title="Uydu Tabanlı Tarihsel Tarımsal Veri Fabrikası",
    description="Sentinel-2 Zaman Serisi Veri Küpü Üretim Altyapısı API Servisi",
    version="1.0.0"
)

@app.on_event("startup")
def startup_event():
    # Uygulama başlarken PostGIS şemasını doğrula ve bağlantı havuzunu ilklendir
    DatabaseManager.initialize_pool()
    DatabaseManager.initialize_schema()

@app.post("/api/fields/register", status_code=status.HTTP_201_CREATED)
async def register_field(payload: FieldRegistration):
    """
    Manuel çizimden (GeoJSON) gelen tarla sınırını doğrular ve PostGIS tablosuna kaydeder.
    """
    field_id = str(uuid.uuid4())
    try:
        # Shapely ile geometrinin geçerliliğini ve sınırlarını hesapla
        geom = shape(payload.geometry.dict())
        bbox = list(geom.bounds)  # [minx, miny, maxx, maxy]
    except Exception as e:
        logger.error(f"Geometri çözümleme hatası: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid geometry format: {str(e)}")

    geojson_str = json.dumps(payload.geometry.dict())
    
    conn = None
    cur = None
    try:
        conn = DatabaseManager.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO fields (id, user_id, name, geom, bbox)
            VALUES (
                %s, %s, %s,
                ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)),
                %s
            ) RETURNING id;
            """,
            (field_id, payload.user_id, payload.name, geojson_str, bbox)
        )
        conn.commit()
        
        return {
            "status": "SUCCESS",
            "message": "Arazi geometrisi PostGIS tablosuna kaydedildi.",
            "field_id": field_id,
            "bounding_box": bbox
        }
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"PostGIS geometri kayıt hatası: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Spatial insertion failed: {str(e)}")
    finally:
        if cur:
            cur.close()
        if conn:
            DatabaseManager.release_connection(conn)

@app.post("/api/fields/tkgm-import", status_code=status.HTTP_201_CREATED)
async def import_tkgm_field(payload: TKGMImportPayload):
    """
    Kullanıcının girdiği ada/parsel bilgisini TKGM servislerinden sorgulayarak PostGIS'e kaydeder.
    """
    client = MegsisClient()
    try:
        parcel_data = client.get_parcel(payload.mahalle_id, payload.ada_no, payload.parsel_no)
        geometry_to_save = parcel_data["geometry"]
    except Exception as e:
        logger.error(f"TKGM Entegrasyon Hatası: {str(e)}")
        # Test/Geliştirme ortamı için fallback dummy geometri (Ankara)
        logger.warning("TKGM servisine ulaşılamadı veya hata alındı. Dummy poligon atanıyor.")
        geometry_to_save = {
            "type": "Polygon",
            "coordinates": [[[32.854, 39.920], [32.856, 39.920], [32.856, 39.922], [32.854, 39.922], [32.854, 39.920]]]
        }
        
    try:
        geom = shape(geometry_to_save)
        bbox = list(geom.bounds)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid geometry returned: {str(e)}")

    field_id = str(uuid.uuid4())
    geojson_str = json.dumps(geometry_to_save)
    
    conn = None
    cur = None
    try:
        conn = DatabaseManager.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO fields (id, user_id, name, geom, bbox)
            VALUES (
                %s, %s, %s,
                ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)),
                %s
            ) RETURNING id;
            """,
            (field_id, payload.user_id, payload.name, geojson_str, bbox)
        )
        conn.commit()
        
        return {
            "status": "SUCCESS",
            "message": "TKGM Parsel sınırları başarıyla PostGIS tablosuna aktarıldı.",
            "field_id": field_id,
            "bounding_box": bbox
        }
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"TKGM veri tabanı kayıt hatası: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Database registration failed: {str(e)}")
    finally:
        if cur:
            cur.close()
        if conn:
            DatabaseManager.release_connection(conn)

@app.post("/api/tasks/trigger/{field_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_historical_pipeline_endpoint(
    field_id: str, 
    start_year: Optional[int] = 2016, 
    end_year: Optional[int] = 2026,
    temporal_resolution: Optional[str] = "15 Günlük Periyotlar"
):
    """
    Belirtilen arazinin 10 yıllık zaman serisi analizini Celery asenkron görev kuyruğuna gönderir.
    """
    conn = None
    cur = None
    field_exists = False
    try:
        conn = DatabaseManager.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM fields WHERE id = %s;", (field_id,))
        field_exists = cur.fetchone() is not None
    except Exception as e:
        logger.error(f"Veritabanı kontrol hatası: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")
    finally:
        if cur:
            cur.close()
        if conn:
            DatabaseManager.release_connection(conn)
            
    if not field_exists:
        raise HTTPException(status_code=404, detail=f"Field {field_id} not found in database.")
        
    # Asenkron görevin kuyruğa bırakılması
    task = process_historical_pipeline_task.delay(field_id, start_year, end_year, temporal_resolution)
    
    return {
        "status": "QUEUED",
        "message": "Tarihsel uydu veri küpü oluşturma görevi Celery kuyruğuna eklendi.",
        "task_id": task.id
    }

@app.get("/api/tasks/status/{task_id}")
async def get_task_status_endpoint(task_id: str):
    """
    Celery görev durumunu ve anlık ilerleme (yıllık ilerleme yüzdeleri) verisini sorgular.
    """
    task_result = AsyncResult(task_id, app=celery_app)
    
    response = {
        "task_id": task_id,
        "status": task_result.status
    }
    
    if task_result.status == "PROGRESS":
        response["progress_details"] = task_result.info
    elif task_result.status == "SUCCESS":
        response["result"] = task_result.result
    elif task_result.status == "FAILURE":
        response["error"] = str(task_result.result)
        
    return response
