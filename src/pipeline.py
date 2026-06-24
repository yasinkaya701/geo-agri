import os
import numpy as np
import xarray as xr
import pandas as pd
import shapely.geometry as sg
from shapely.geometry import shape
import pystac_client
import planetary_computer as pc
from odc.stac import stac_load, configure_rio
from rasterio.enums import Resampling
from rasterio.features import rasterize
import rioxarray
from src.config import PLANETARY_COMPUTER_STAC_URL, logger

class SatelliteDataFactoryPipeline:
    def __init__(self, geometry_geojson: dict, spatial_shape: tuple = (64, 64)):
        self.geometry_geojson = geometry_geojson
        self.shapely_geom = shape(geometry_geojson)
        self.bbox = list(self.shapely_geom.bounds)  # [minx, miny, maxx, maxy]
        self.spatial_shape = spatial_shape

        # Negatif Tamponlama (Erosion): 5m (yaklaşık 0.00005 derece)
        self.eroded_geom = self.shapely_geom.buffer(-0.00005)
        if self.eroded_geom.is_empty or not self.eroded_geom.is_valid:
            logger.warning("Negatif tamponlama poligonu sıfırladı veya geçersiz kıldı. Orijinal poligon kullanılacak.")
            self.eroded_geom = self.shapely_geom

    def _apply_advanced_cloud_mask(self, dataset: xr.Dataset) -> xr.Dataset:
        """
        SCL (Scene Classification Layer) bandını kullanarak bulut ve gölge içeren pikselleri NaN yapar.
        Maskelenen sınıflar: 0 (No Data), 1 (Saturated/Defective), 3 (Cloud Shadows), 
        8 (Cloud Medium Prob), 9 (Cloud High Prob), 10 (Thin Cirrus).
        """
        if "SCL" not in dataset.data_vars:
            logger.warning("SCL bandı bulunamadı. Bulut maskeleme atlanıyor.")
            return dataset

        # Maskelenecek pikseller için boolean maskesi (True = bulutlu/bozuk)
        cloud_mask = dataset.SCL.isin([0, 1, 3, 8, 9, 10])

        # Tüm spektral bantları maskele (B02, B03, B04, B08)
        bands_to_mask = [b for b in ["B02", "B03", "B04", "B08"] if b in dataset.data_vars]
        cleaned = dataset[bands_to_mask].where(~cloud_mask)
        return cleaned

    def _resample_spatial(self, dataset: xr.Dataset) -> xr.Dataset:
        """
        Raster veri kümesini rioxarray.reproject kullanarak hedef matris boyutuna (64x64) getirir.
        """
        # EPSG:4326 CRS tanımla
        if not dataset.rio.crs:
            dataset = dataset.rio.write_crs("EPSG:4326")

        resampled = dataset.rio.reproject(
            dst_crs="EPSG:4326",
            shape=self.spatial_shape,
            resampling=Resampling.bilinear
        )
        return resampled

    def _generate_weight_mask(self, resampled_ds: xr.Dataset) -> np.ndarray:
        """
        Piksel düzeyinde tarla kapsama oranını (Weight Mask) üretir.
        Erozyon poligonu içi = 1.0, sınır bölgeleri = 0.5, dışarısı = 0.0.
        """
        transform = resampled_ds.rio.transform()
        out_shape = resampled_ds.rio.shape

        # Orijinal geometri maskesi
        original_mask = rasterize(
            [(self.shapely_geom, 1.0)],
            out_shape=out_shape,
            transform=transform,
            fill=0.0,
            dtype=np.float32
        )

        # Erozyon geometri maskesi
        eroded_mask = rasterize(
            [(self.eroded_geom, 1.0)],
            out_shape=out_shape,
            transform=transform,
            fill=0.0,
            dtype=np.float32
        )

        weight_mask = 0.5 * original_mask + 0.5 * eroded_mask
        return weight_mask

    def process_seasonal_cube(self, year: int, temporal_resolution: str = "15 Günlük Periyotlar") -> tuple[np.ndarray, list[float], np.ndarray]:
        """
        İlgili yılın büyüme sezonunu (Mart - Ağustos) işleyerek 4-bantlı (B02, B03, B04, B08) matrisi,
        skaler NDVI trend özetini ve spatial weight maskesini üretir.
        """
        start_date = f"{year}-03-01"
        end_date = f"{year}-08-31"

        logger.info(f"{year} yılı büyüme sezonu sorgulanıyor ({start_date} / {end_date}) [{temporal_resolution}]...")

        # STAC API bağlantısı
        catalog = pystac_client.Client.open(PLANETARY_COMPUTER_STAC_URL, modifier=pc.sign_inplace)

        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=self.bbox,
            datetime=f"{start_date}/{end_date}",
            query={"eo:cloud_cover": {"lt": 60}}
        )

        items = list(search.item_collection())
        if not items:
            logger.warning(f"{year} yılı için sahne bulunamadı. Boş veri küpü dönülüyor.")
            steps = 6 if "AYLIK" in temporal_resolution.upper() else (1 if "HAM" in temporal_resolution.upper() else 12)
            empty_cube = np.zeros((steps, 4, *self.spatial_shape), dtype=np.float32)
            empty_trends = [0.0] * steps
            empty_weight = np.zeros(self.spatial_shape, dtype=np.float32)
            return empty_cube, empty_trends, empty_weight

        # Dinamik Zaman Filtrelemesi
        if "HAM" in temporal_resolution.upper():
            # Tüm sahneleri doğrudan al (en temiz 25 sahneyi seçerek performansı koru)
            selected_items = sorted(items, key=lambda x: x.properties.get("eo:cloud_cover", 100.0))[:25]
            selected_items.sort(key=lambda x: x.properties.get("datetime", ""))
        else:
            steps_count = 6 if "AYLIK" in temporal_resolution.upper() else 12
            days_step = 30 if "AYLIK" in temporal_resolution.upper() else 15
            periods = []
            start_dt = pd.to_datetime(start_date)
            for i in range(steps_count):
                p_start = start_dt + pd.Timedelta(days=i*days_step)
                p_end = p_start + pd.Timedelta(days=days_step)
                periods.append((p_start, p_end))

            selected_items = []
            for p_start, p_end in periods:
                period_items = []
                for item in items:
                    item_date = pd.to_datetime(item.properties.get("datetime", "")[:10])
                    if p_start <= item_date < p_end:
                        period_items.append(item)
                if period_items:
                    best_item = min(period_items, key=lambda x: x.properties.get("eo:cloud_cover", 100.0))
                    selected_items.append(best_item)

        if not selected_items:
            logger.warning(f"{year} yılı periyotları boş kaldı. Boş veri küpü dönülüyor.")
            steps = 6 if "AYLIK" in temporal_resolution.upper() else (1 if "HAM" in temporal_resolution.upper() else 12)
            empty_cube = np.zeros((steps, 4, *self.spatial_shape), dtype=np.float32)
            empty_trends = [0.0] * steps
            empty_weight = np.zeros(self.spatial_shape, dtype=np.float32)
            return empty_cube, empty_trends, empty_weight

        # Rasterio bulut ayarları
        configure_rio(cloud_defaults=True)

        # odc-stac ile B02, B03, B04, B08 ve SCL bantlarını lazy loading yükleme
        ds = stac_load(
            selected_items,
            bands=["B02", "B03", "B04", "B08", "SCL"],
            bbox=self.bbox,
            crs="EPSG:4326",
            resolution=0.00009,
            chunks={"time": 1, "x": 256, "y": 256},
            groupby="solar_day"
        )

        # 1. Uzamsal Kırpma & Yeniden Örnekleme (64x64)
        resampled_ds = self._resample_spatial(ds)

        # 2. Spektral Sızıntı & Weight Mask Üretimi
        weight_mask = self._generate_weight_mask(resampled_ds)

        # 3. Gelişmiş Bulut Maskeleme
        masked_ds = self._apply_advanced_cloud_mask(resampled_ds)

        # Dask array hesaplamasını başlatmadan önce zamansal boşluk analizi yapalım
        time_coords = masked_ds.time.values
        valid_counts = masked_ds["B04"].notnull().sum(dim=["x", "y"]).compute().values
        valid_dates = time_coords[valid_counts > 0]

        # 5. Zamansal İnterpolasyon ve Hata Tolerans Analizi (Sınır boşlukları dahil)
        max_gap = 184  # Varsayılan olarak tüm sezon boş kabul edilir
        if len(valid_dates) >= 1:
            import datetime
            current_date = datetime.date.today()
            season_start = pd.to_datetime(start_date)
            
            if year == current_date.year:
                season_end_for_gap = pd.to_datetime(valid_dates[-1])
            else:
                season_end_for_gap = pd.to_datetime(end_date)
                
            gap_start = (pd.to_datetime(valid_dates[0]) - season_start).days
            gap_end = (season_end_for_gap - pd.to_datetime(valid_dates[-1])).days
            
            gaps = [gap_start, gap_end]
            if len(valid_dates) > 1:
                diffs = np.diff(valid_dates) / np.timedelta64(1, 'D')
                gaps.extend(diffs)
            max_gap = float(np.max(gaps))

        logger.info(f"{year} yılı için maksimum zamansal boşluk: {max_gap:.1f} gün.")

        # Boşluk durumuna göre interpolasyon stratejisi
        if max_gap > 60:
            logger.warning(f"{year} yılı büyüme sezonu veri kalitesi yetersiz (Boşluk: {max_gap:.1f} gün > 60 gün). Analiz dışı bırakılıyor.")
            steps = len(valid_dates) if "HAM" in temporal_resolution.upper() else (6 if "AYLIK" in temporal_resolution.upper() else 12)
            empty_cube = np.zeros((steps, 4, *self.spatial_shape), dtype=np.float32)
            empty_trends = [0.0] * steps
            return empty_cube, empty_trends, weight_mask

        # Zaman interpolasyon yöntemi seçimi
        if max_gap > 30:
            logger.info("30 günden fazla veri kaybı var. Doğrusal (linear) enterpolasyon kullanılacak.")
            interp_method = "linear"
        else:
            logger.info("Veri kalitesi yüksek (Boşluk <= 30 gün). Kübik spline enterpolasyonu uygulanacak.")
            interp_method = "cubic"

        # Sezon sınırlarını içeren boş dilimler (NaN) ekleyerek sınır dışı interpolasyonu sabit tutalım
        t_start = pd.to_datetime(start_date)
        t_end = pd.to_datetime(end_date)
        
        additional_times = []
        if t_start not in masked_ds.time.values:
            additional_times.append(t_start)
        if t_end not in masked_ds.time.values:
            additional_times.append(t_end)
            
        if additional_times:
            nan_ds = xr.Dataset(
                {
                    "B02": (["time", "y", "x"], np.full((len(additional_times), *self.spatial_shape), np.nan, dtype=np.float32)),
                    "B03": (["time", "y", "x"], np.full((len(additional_times), *self.spatial_shape), np.nan, dtype=np.float32)),
                    "B04": (["time", "y", "x"], np.full((len(additional_times), *self.spatial_shape), np.nan, dtype=np.float32)),
                    "B08": (["time", "y", "x"], np.full((len(additional_times), *self.spatial_shape), np.nan, dtype=np.float32)),
                },
                coords={"time": additional_times, "y": masked_ds.y, "x": masked_ds.x}
            )
            ds_extended = xr.concat([masked_ds[["B02", "B03", "B04", "B08"]], nan_ds], dim="time").sortby("time")
        else:
            ds_extended = masked_ds[["B02", "B03", "B04", "B08"]]

        # Tüm bantlardaki zamansal NaN'ları doldur
        try:
            if len(valid_dates) >= 4 and interp_method == "cubic":
                ds_filled = ds_extended.interpolate_na(dim="time", method="cubic", use_coordinate=True)
            else:
                ds_filled = ds_extended.interpolate_na(dim="time", method="linear", use_coordinate=True)
        except Exception as e:
            logger.warning(f"İnterpolasyon hatası ({interp_method}), lineer fall-back yapılıyor. Hata: {e}")
            ds_filled = ds_extended.interpolate_na(dim="time", method="linear", use_coordinate=True)

        # Sınır dışı boşlukları ffill/bfill ile sabit tut
        ds_filled = ds_filled.ffill(dim="time").bfill(dim="time").fillna(0.0)

        # 6. Zaman Adımlarına Örnekleme
        if "HAM" in temporal_resolution.upper():
            ds_steps = ds_filled.sel(time=valid_dates)
        else:
            steps_count = 6 if "AYLIK" in temporal_resolution.upper() else 12
            target_dates = pd.date_range(start=start_date, end=end_date, periods=steps_count)
            ds_steps = ds_filled.interp(time=target_dates, method="linear").fillna(0.0)

        # NDVI hesaplama (sadece trendler için)
        red_steps = ds_steps["B04"].astype(np.float32)
        nir_steps = ds_steps["B08"].astype(np.float32)
        denom = nir_steps + red_steps
        denom = xr.where(denom == 0.0, 1e-7, denom)
        ndvi_steps = ((nir_steps - red_steps) / denom).clip(-1.0, 1.0)

        # Dask array hesaplamasını başlat
        logger.info(f"Dask hesaplaması tetikleniyor ({year})...")
        cube_ndvi = ndvi_steps.compute().values # (TimeSteps, 64, 64)
        
        b02_val = ds_steps["B02"].compute().values
        b03_val = ds_steps["B03"].compute().values
        b04_val = ds_steps["B04"].compute().values
        b08_val = ds_steps["B08"].compute().values
        
        # 4 bantlı çoklu spektral küpü oluştur: (TimeSteps, 4, 64, 64)
        cube_multiband = np.stack([b02_val, b03_val, b04_val, b08_val], axis=1)

        # Skaler trendlerin hesaplanması (Arayüz grafikleri için)
        scalar_trends = []
        for t in range(len(cube_ndvi)):
            slice_data = cube_ndvi[t]
            field_pixels = slice_data[weight_mask > 0]
            if len(field_pixels) > 0:
                mean_val = float(np.mean(field_pixels))
                scalar_trends.append(0.0 if np.isnan(mean_val) else mean_val)
            else:
                scalar_trends.append(0.0)

        # Zaman adımlarının tarihlerini string listesi olarak al
        step_dates = [pd.to_datetime(t).strftime("%Y-%m-%d") for t in ds_steps.time.values]

        return cube_multiband, scalar_trends, weight_mask, step_dates
