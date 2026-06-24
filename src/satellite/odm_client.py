"""WebODM / NodeODM API istemci modülü.

Uçuş fotoğraflarını NodeODM API'sine gönderir, işlem durumunu takip eder
ve sonuç ortofoto/DSM dosyalarını indirir. Sunucu bulunamadığında çalışan
bir Simülasyon (Mock) modu içerir.
"""

import os
import zipfile
import tempfile
import time
import requests
from typing import List, Dict, Any, Tuple, Optional
from pyodm import Node, exceptions as pyodm_exceptions
from src.config import logger

class ODMClient:
    """WebODM/NodeODM REST ve SDK API istemcisi."""

    def __init__(self, host: str = "localhost", port: int = 3000, token: Optional[str] = None):
        self.host = host
        self.port = port
        self.token = token
        self.url = f"http://{host}:{port}"
        
        # PyODM Node objesi (Token desteği için headers eklenebilir)
        # Not: NodeODM genellikle kimlik doğrulamasız çalışır.
        self.node = None
        self._is_simulated = False
        
        try:
            self.node = Node(self.host, self.port)
        except Exception as e:
            logger.warning(f"NodeODM bağlantısı kurulamadı, simülasyon modu aktif edilebilir: {e}")

    @property
    def is_simulated(self) -> bool:
        return self._is_simulated

    @is_simulated.setter
    def is_simulated(self, val: bool):
        self._is_simulated = val

    def check_connection(self) -> bool:
        """NodeODM sunucusuna bağlantı olup olmadığını kontrol eder."""
        if self._is_simulated:
            return True
        try:
            # Doğrudan /info endpoint'ine istek atalım veya pyodm kullanalım
            response = requests.get(f"{self.url}/info", timeout=3)
            return response.status_code == 200
        except Exception:
            return False

    def get_node_info(self) -> Dict[str, Any]:
        """Düğüm hakkındaki kapasite, sürüm vb. bilgileri döner."""
        if self._is_simulated:
            return {
                "version": "1.5.13 (Simülasyon)",
                "taskQueueCount": 0,
                "maxImages": 500,
                "supportedOptions": ["dsm", "orthophoto-resolution", "dem-resolution", "quality"]
            }
        try:
            response = requests.get(f"{self.url}/info", timeout=3)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Node info alınamadı: {e}")
        return {}

    def create_task_from_zip(
        self,
        zip_file_bytes: bytes,
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        """ZIP dosyası içerisindeki görüntüleri çıkartıp NodeODM'e göndererek görev başlatır."""
        options = options or {}
        
        if self._is_simulated:
            logger.info("Simülasyon modunda görev başlatılıyor...")
            return "sim_task_" + str(int(time.time()))

        # Geçici bir klasör oluşturup zip'i açalım
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "images.zip")
            with open(zip_path, "wb") as f:
                f.write(zip_file_bytes)
            
            # Zip'ten görselleri ayıklayalım
            extracted_images = []
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
                
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.lower().endswith(('.jpg', '.jpeg', '.png', '.tif', '.tiff')):
                        # Geçici zip dosyasının kendisini eklemeyelim
                        extracted_images.append(os.path.join(root, file))

            if not extracted_images:
                raise ValueError("ZIP dosyası içinde geçerli görsel (.jpg, .png) bulunamadı.")

            logger.info(f"NodeODM'e {len(extracted_images)} adet görsel gönderiliyor...")
            
            # PyODM ile görevi oluşturup başlatalım
            try:
                task = self.node.create_task(extracted_images, options)
                logger.info(f"Görev başarıyla oluşturuldu. ID: {task.uuid}")
                return task.uuid
            except Exception as e:
                logger.error(f"NodeODM üzerinde görev oluşturulamadı: {e}")
                raise e

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Görev durumunu (status, progress, error) sorgular."""
        if self._is_simulated or task_id.startswith("sim_task_"):
            # Simüle edilmiş durum güncellemesi
            # Gerçekçi bir ilerleme için zaman farkını baz alabiliriz
            start_time = int(task_id.split("_")[-1])
            elapsed = time.time() - start_time
            
            if elapsed < 10:
                return {"status": "RUNNING", "progress": int(elapsed * 10), "error": None}
            elif elapsed < 15:
                return {"status": "RUNNING", "progress": 95, "error": None}
            else:
                return {"status": "COMPLETED", "progress": 100, "error": None}

        try:
            # PyODM üzerinden görevi alalım
            task = self.node.get_task(task_id)
            info = task.info()
            
            # pyodm durum kodları genellikle:
            # 1: QUEUED, 2: RUNNING, 3: COMPLETED, 4: FAILED, 5: CANCELLED
            status_map = {1: "QUEUED", 2: "RUNNING", 3: "COMPLETED", 4: "FAILED", 5: "CANCELLED"}
            status_code = info.status.value
            status_str = status_map.get(status_code, "UNKNOWN")
            
            return {
                "status": status_str,
                "progress": info.progress,
                "error": info.error_message if hasattr(info, "error_message") else None
            }
        except Exception as e:
            logger.error(f"Görev durumu alınamadı ({task_id}): {e}")
            return {"status": "FAILED", "progress": 0, "error": str(e)}

    def download_assets(self, task_id: str, output_dir: str) -> Dict[str, str]:
        """Görev çıktılarını (Ortofoto ve DSM) belirtilen klasöre indirir."""
        os.makedirs(output_dir, exist_ok=True)
        
        result_paths = {
            "orthophoto": "",
            "dsm": ""
        }

        if self._is_simulated or task_id.startswith("sim_task_"):
            logger.info("Simülasyon modunda yapay çıktılar hazırlanıyor...")
            # Bu dosyaları bir sonraki adımda `drone_analyzer.py` içindeki mock üretecimiz
            # aracılığıyla dinamik olarak yaratacağız veya kopyalayacağız.
            result_paths["orthophoto"] = os.path.join(output_dir, "sim_orthophoto.tif")
            result_paths["dsm"] = os.path.join(output_dir, "sim_dsm.tif")
            return result_paths

        try:
            task = self.node.get_task(task_id)
            
            # Asset listesini alıp ortofoto ve dsm'i indirelim
            # PyODM download_assets() tüm zip'i indirir ve açar
            logger.info(f"Görev çıktıları indiriliyor: {output_dir}")
            task.download_assets(output_dir)
            
            # İndirilen dosyaları bulalım
            # Genellikle output_dir içinde 'odm_orthophoto/odm_orthophoto.tif' ve 'odm_dem/dsm.tif' oluşur
            for root, _, files in os.walk(output_dir):
                for file in files:
                    if file == "odm_orthophoto.tif" or file == "orthophoto.tif":
                        result_paths["orthophoto"] = os.path.join(root, file)
                    elif file == "dsm.tif" or file == "odm_dsm.tif":
                        result_paths["dsm"] = os.path.join(root, file)
            
            # Eğer beklenen isimlerde bulunamadıysa ilk .tif dosyalarını eşleştirelim
            if not result_paths["orthophoto"]:
                tifs = []
                for root, _, files in os.walk(output_dir):
                    for file in files:
                        if file.lower().endswith(".tif") and "dsm" not in file.lower() and "dem" not in file.lower():
                            tifs.append(os.path.join(root, file))
                if tifs:
                    result_paths["orthophoto"] = tifs[0]

            logger.info(f"İndirilen çıktılar: {result_paths}")
            return result_paths

        except Exception as e:
            logger.error(f"Çıktılar indirilirken hata oluştu: {e}")
            raise e
