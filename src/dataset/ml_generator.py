"""CV / CNN / Deep Learning modelleri için üretim kalitesinde veri seti üreteci.

Özellikler:
    - Configurable patch extraction (32×32, 64×64, 128×128)
    - 8 kanallı multi-band stack (B02, B03, B04, B08 + NDVI, NDWI, SAVI, EVI)
    - Min-Max / Z-Score / Percentile normalizasyon
    - Augmentation pipeline (flip, rotation, noise, brightness)
    - Stratified train/val/test split
    - Otomatik NDVI-tabanlı label üretimi
    - Metadata JSON (band stats, normalizasyon params, coğrafi bilgi)
"""

import io
import json
import zipfile
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from src.config import logger
from src.dataset.ndvi import (
    calculate_ndvi, calculate_ndwi, calculate_savi, calculate_evi,
    savitzky_golay_smooth
)


# ═══════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════

@dataclass
class DatasetConfig:
    """ML veri seti üretim parametreleri."""
    # Patch
    patch_size: int = 64
    stride: int = 32  # Overlap = patch_size - stride
    min_valid_ratio: float = 0.7  # NaN oranı bu altındaysa patch geçerli

    # Channels
    include_bands: bool = True      # B02, B03, B04, B08
    include_ndvi: bool = True
    include_ndwi: bool = True
    include_savi: bool = True
    include_evi: bool = True

    # Normalization
    normalization: str = "minmax"  # "minmax", "zscore", "percentile", "none"
    percentile_low: float = 2.0
    percentile_high: float = 98.0

    # Augmentation
    aug_flip: bool = True
    aug_rotate: bool = True
    aug_noise: bool = False
    noise_std: float = 0.01
    aug_brightness: bool = False
    brightness_range: float = 0.1

    # Split
    train_ratio: float = 0.70
    val_ratio: float = 0.15
    test_ratio: float = 0.15

    # Labels
    generate_labels: bool = True
    label_thresholds: List[float] = field(default_factory=lambda: [0.15, 0.35, 0.55])
    # Sınıflar: 0=Çıplak (<0.15), 1=Seyrek (0.15-0.35), 2=Orta (0.35-0.55), 3=Yoğun (>0.55)
    label_names: List[str] = field(default_factory=lambda: ["Çıplak Toprak", "Seyrek Vejetasyon", "Orta Vejetasyon", "Yoğun Vejetasyon"])

    # Temporal
    apply_sg_smoothing: bool = True
    sg_window: int = 7
    sg_polyorder: int = 2


# ═══════════════════════════════════════════════════════════
#  Core ML Dataset Generator
# ═══════════════════════════════════════════════════════════

class MLDatasetGenerator:
    """Uydu görüntü verilerinden ML-ready veri seti üretir."""

    def __init__(self, config: Optional[DatasetConfig] = None):
        self.config = config or DatasetConfig()
        self._norm_params: Dict[str, Any] = {}

    # ─── Public API ───────────────────────────────────────

    def generate_from_processed(
        self,
        processed_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Streamlit processed_data listesinden tam ML veri seti üretir.

        Args:
            processed_data: [{date, cloud_percent, bands: {blue, green, red, nir, ndvi, scl}}]

        Returns:
            dict:
                patches: np.ndarray (N, C, H, W) — tüm patchler
                labels: np.ndarray (N,) — sınıf etiketleri
                dates: list[str] — her patchin kaynak tarihi
                train_idx, val_idx, test_idx: np.ndarray — split indeksleri
                metadata: dict — tam metadata
                channel_names: list[str] — kanal isimleri
        """
        logger.info(f"ML dataset üretimi başlıyor — {len(processed_data)} gözlem, "
                     f"patch={self.config.patch_size}, norm={self.config.normalization}")

        # 1. Multi-band küp oluştur
        all_patches = []
        all_labels = []
        all_dates = []
        channel_names = self._get_channel_names()

        for entry in processed_data:
            date = entry["date"]
            bands = entry["bands"]

            # Multi-channel stack (C, H, W)
            stack = self._build_channel_stack(bands)
            if stack is None:
                continue

            # Patch extraction
            patches = self._extract_patches(stack)
            if len(patches) == 0:
                continue

            # Labels
            if self.config.generate_labels:
                ndvi_channel_idx = self._get_ndvi_channel_idx()
                if ndvi_channel_idx is not None:
                    labels = self._generate_labels(patches, ndvi_channel_idx)
                else:
                    # Fallback: NDVI'ı ayrıca hesapla
                    labels = np.zeros(len(patches), dtype=np.int64)
            else:
                labels = np.zeros(len(patches), dtype=np.int64)

            all_patches.append(patches)
            all_labels.append(labels)
            all_dates.extend([date] * len(patches))

        if not all_patches:
            raise ValueError("Hiç geçerli patch üretilemedi. Veri kalitesini kontrol edin.")

        patches_array = np.concatenate(all_patches, axis=0)  # (N, C, H, W)
        labels_array = np.concatenate(all_labels, axis=0)    # (N,)

        logger.info(f"Ham patchler: {patches_array.shape}, kanal: {len(channel_names)}")

        # 2. Normalizasyon
        patches_array = self._normalize(patches_array)

        # 3. Augmentation
        if self._has_augmentation():
            patches_aug, labels_aug, dates_aug = self._augment(
                patches_array, labels_array, all_dates
            )
            patches_array = np.concatenate([patches_array, patches_aug], axis=0)
            labels_array = np.concatenate([labels_array, labels_aug], axis=0)
            all_dates = all_dates + dates_aug

        # 4. Split
        train_idx, val_idx, test_idx = self._split(labels_array)

        # 5. Metadata
        metadata = self._build_metadata(
            patches_array, labels_array, channel_names,
            train_idx, val_idx, test_idx, all_dates
        )

        logger.info(f"ML dataset tamamlandı — toplam: {len(patches_array)}, "
                     f"train: {len(train_idx)}, val: {len(val_idx)}, test: {len(test_idx)}")

        return {
            "patches": patches_array,
            "labels": labels_array,
            "dates": all_dates,
            "train_idx": train_idx,
            "val_idx": val_idx,
            "test_idx": test_idx,
            "metadata": metadata,
            "channel_names": channel_names,
        }

    def generate_from_cube(
        self,
        cube: np.ndarray,
        weight_mask: Optional[np.ndarray] = None,
        dates_dict: Optional[Dict] = None,
        sorted_years: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """5D veri küpünden (N_years, Steps, 4, H, W) ML veri seti üretir.

        Args:
            cube: 5D numpy array
            weight_mask: (H, W) tarla maskesi
            dates_dict: {year_str: [date_str, ...]}
            sorted_years: sıralı yıl listesi
        """
        logger.info(f"5D küpten ML dataset üretimi: shape={cube.shape}")

        N_years, Steps, Bands, H, W = cube.shape
        channel_names = self._get_channel_names()

        all_patches = []
        all_labels = []
        all_dates = []

        for y in range(N_years):
            year = sorted_years[y] if sorted_years else 2016 + y
            year_dates = dates_dict.get(str(year), []) if dates_dict else []

            for t in range(Steps):
                slice_4band = cube[y, t]  # (4, H, W)

                # Maske uygula
                if weight_mask is not None:
                    mask_3d = np.broadcast_to(weight_mask[np.newaxis, :, :], slice_4band.shape)
                    slice_4band = np.where(mask_3d > 0, slice_4band, np.nan)

                # bands dict oluştur (numpy versiyonu)
                bands = {
                    "blue": slice_4band[0],
                    "green": slice_4band[1],
                    "red": slice_4band[2],
                    "nir": slice_4band[3],
                }

                stack = self._build_channel_stack_numpy(bands)
                if stack is None:
                    continue

                patches = self._extract_patches(stack)
                if len(patches) == 0:
                    continue

                if self.config.generate_labels:
                    ndvi_idx = self._get_ndvi_channel_idx()
                    labels = self._generate_labels(patches, ndvi_idx) if ndvi_idx is not None else np.zeros(len(patches), dtype=np.int64)
                else:
                    labels = np.zeros(len(patches), dtype=np.int64)

                date_str = year_dates[t] if t < len(year_dates) else f"{year}-{t:02d}"
                all_patches.append(patches)
                all_labels.append(labels)
                all_dates.extend([date_str] * len(patches))

        if not all_patches:
            raise ValueError("5D küpten geçerli patch üretilemedi.")

        patches_array = np.concatenate(all_patches, axis=0)
        labels_array = np.concatenate(all_labels, axis=0)

        patches_array = self._normalize(patches_array)

        if self._has_augmentation():
            patches_aug, labels_aug, dates_aug = self._augment(patches_array, labels_array, all_dates)
            patches_array = np.concatenate([patches_array, patches_aug], axis=0)
            labels_array = np.concatenate([labels_array, labels_aug], axis=0)
            all_dates = all_dates + dates_aug

        train_idx, val_idx, test_idx = self._split(labels_array)

        metadata = self._build_metadata(
            patches_array, labels_array, channel_names,
            train_idx, val_idx, test_idx, all_dates
        )

        return {
            "patches": patches_array,
            "labels": labels_array,
            "dates": all_dates,
            "train_idx": train_idx,
            "val_idx": val_idx,
            "test_idx": test_idx,
            "metadata": metadata,
            "channel_names": channel_names,
        }

    def export_to_zip(self, dataset: Dict[str, Any]) -> bytes:
        """Üretilen dataseti indirilebilir ZIP olarak paketler.

        İçerik:
            X_train.npy, X_val.npy, X_test.npy  — patch dizileri
            y_train.npy, y_val.npy, y_test.npy  — label dizileri
            metadata.json  — tam metadata
        """
        buf = io.BytesIO()

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            patches = dataset["patches"]
            labels = dataset["labels"]
            train_idx = dataset["train_idx"]
            val_idx = dataset["val_idx"]
            test_idx = dataset["test_idx"]

            # Split arrays
            for name, idx in [("train", train_idx), ("val", val_idx), ("test", test_idx)]:
                x_buf = io.BytesIO()
                np.save(x_buf, patches[idx])
                zf.writestr(f"X_{name}.npy", x_buf.getvalue())

                y_buf = io.BytesIO()
                np.save(y_buf, labels[idx])
                zf.writestr(f"y_{name}.npy", y_buf.getvalue())

            # Metadata
            zf.writestr("metadata.json", json.dumps(dataset["metadata"], indent=2, ensure_ascii=False))

            # README
            readme = self._generate_readme(dataset)
            zf.writestr("README.md", readme)

        buf.seek(0)
        return buf.getvalue()

    # ─── Private: Channel Stack ───────────────────────────

    def _get_channel_names(self) -> List[str]:
        names = []
        if self.config.include_bands:
            names.extend(["B02_Blue", "B03_Green", "B04_Red", "B08_NIR"])
        if self.config.include_ndvi:
            names.append("NDVI")
        if self.config.include_ndwi:
            names.append("NDWI")
        if self.config.include_savi:
            names.append("SAVI")
        if self.config.include_evi:
            names.append("EVI")
        return names

    def _get_ndvi_channel_idx(self) -> Optional[int]:
        names = self._get_channel_names()
        return names.index("NDVI") if "NDVI" in names else None

    def _build_channel_stack(self, bands: Dict) -> Optional[np.ndarray]:
        """xarray DataArray bands dict → (C, H, W) numpy stack."""
        channels = []
        try:
            if self.config.include_bands:
                channels.extend([
                    bands["blue"].values,
                    bands["green"].values,
                    bands["red"].values,
                    bands["nir"].values,
                ])
            if self.config.include_ndvi:
                ndvi = bands.get("ndvi")
                if ndvi is None:
                    ndvi = calculate_ndvi(bands["red"], bands["nir"])
                channels.append(ndvi.values if hasattr(ndvi, "values") else ndvi)
            if self.config.include_ndwi:
                channels.append(calculate_ndwi(bands["green"], bands["nir"]).values
                                if hasattr(bands["green"], "values")
                                else calculate_ndwi(bands["green"], bands["nir"]))
            if self.config.include_savi:
                channels.append(calculate_savi(bands["red"], bands["nir"]).values
                                if hasattr(bands["red"], "values")
                                else calculate_savi(bands["red"], bands["nir"]))
            if self.config.include_evi:
                channels.append(calculate_evi(bands["blue"], bands["red"], bands["nir"]).values
                                if hasattr(bands["blue"], "values")
                                else calculate_evi(bands["blue"], bands["red"], bands["nir"]))
        except Exception as e:
            logger.warning(f"Kanal stack oluşturulamadı: {e}")
            return None

        stack = np.array(channels, dtype=np.float32)  # (C, H, W)
        return stack

    def _build_channel_stack_numpy(self, bands: Dict[str, np.ndarray]) -> Optional[np.ndarray]:
        """Pure numpy bands dict → (C, H, W) stack."""
        channels = []
        try:
            if self.config.include_bands:
                channels.extend([bands["blue"], bands["green"], bands["red"], bands["nir"]])
            if self.config.include_ndvi:
                channels.append(calculate_ndvi(bands["red"], bands["nir"]))
            if self.config.include_ndwi:
                channels.append(calculate_ndwi(bands["green"], bands["nir"]))
            if self.config.include_savi:
                channels.append(calculate_savi(bands["red"], bands["nir"]))
            if self.config.include_evi:
                channels.append(calculate_evi(bands["blue"], bands["red"], bands["nir"]))
        except Exception as e:
            logger.warning(f"Numpy kanal stack hatası: {e}")
            return None
        return np.array(channels, dtype=np.float32)

    # ─── Private: Patch Extraction ────────────────────────

    def _extract_patches(self, stack: np.ndarray) -> np.ndarray:
        """(C, H, W) stackten (N, C, pH, pW) patchler çıkarır."""
        C, H, W = stack.shape
        ps = self.config.patch_size
        stride = self.config.stride
        min_valid = self.config.min_valid_ratio

        patches = []
        for y in range(0, H - ps + 1, stride):
            for x in range(0, W - ps + 1, stride):
                patch = stack[:, y:y + ps, x:x + ps]  # (C, ps, ps)

                # Geçerlilik kontrolü: NaN oranı
                valid_ratio = np.count_nonzero(~np.isnan(patch)) / patch.size
                if valid_ratio < min_valid:
                    continue

                # NaN'ları 0 ile doldur
                patch = np.nan_to_num(patch, nan=0.0)
                patches.append(patch)

        if not patches:
            return np.zeros((0, C, ps, ps), dtype=np.float32)

        return np.array(patches, dtype=np.float32)

    # ─── Private: Labels ──────────────────────────────────

    def _generate_labels(self, patches: np.ndarray, ndvi_channel_idx: int) -> np.ndarray:
        """Her patchin ortalama NDVI'ına göre sınıf etiketi üretir."""
        N = patches.shape[0]
        labels = np.zeros(N, dtype=np.int64)
        thresholds = sorted(self.config.label_thresholds)

        for i in range(N):
            mean_ndvi = float(np.nanmean(patches[i, ndvi_channel_idx]))
            label = 0
            for t_idx, t_val in enumerate(thresholds):
                if mean_ndvi >= t_val:
                    label = t_idx + 1
            labels[i] = label

        return labels

    # ─── Private: Normalization ───────────────────────────

    def _normalize(self, patches: np.ndarray) -> np.ndarray:
        """(N, C, H, W) patch dizisini normalize eder."""
        if self.config.normalization == "none":
            self._norm_params = {"method": "none"}
            return patches

        N, C, H, W = patches.shape

        if self.config.normalization == "minmax":
            mins = np.zeros(C, dtype=np.float32)
            maxs = np.zeros(C, dtype=np.float32)
            for c in range(C):
                c_data = patches[:, c, :, :]
                c_min = float(np.nanpercentile(c_data, 1))
                c_max = float(np.nanpercentile(c_data, 99))
                mins[c] = c_min
                maxs[c] = c_max
                denom = c_max - c_min if c_max - c_min > 1e-8 else 1.0
                patches[:, c, :, :] = (c_data - c_min) / denom

            patches = np.clip(patches, 0.0, 1.0)
            self._norm_params = {
                "method": "minmax",
                "channel_mins": mins.tolist(),
                "channel_maxs": maxs.tolist(),
            }

        elif self.config.normalization == "zscore":
            means = np.zeros(C, dtype=np.float32)
            stds = np.zeros(C, dtype=np.float32)
            for c in range(C):
                c_data = patches[:, c, :, :]
                c_mean = float(np.nanmean(c_data))
                c_std = float(np.nanstd(c_data))
                means[c] = c_mean
                stds[c] = c_std
                patches[:, c, :, :] = (c_data - c_mean) / (c_std if c_std > 1e-8 else 1.0)

            self._norm_params = {
                "method": "zscore",
                "channel_means": means.tolist(),
                "channel_stds": stds.tolist(),
            }

        elif self.config.normalization == "percentile":
            p_low = self.config.percentile_low
            p_high = self.config.percentile_high
            lows = np.zeros(C, dtype=np.float32)
            highs = np.zeros(C, dtype=np.float32)
            for c in range(C):
                c_data = patches[:, c, :, :]
                lo = float(np.nanpercentile(c_data, p_low))
                hi = float(np.nanpercentile(c_data, p_high))
                lows[c] = lo
                highs[c] = hi
                denom = hi - lo if hi - lo > 1e-8 else 1.0
                patches[:, c, :, :] = (c_data - lo) / denom

            patches = np.clip(patches, 0.0, 1.0)
            self._norm_params = {
                "method": "percentile",
                "percentile_low": p_low,
                "percentile_high": p_high,
                "channel_lows": lows.tolist(),
                "channel_highs": highs.tolist(),
            }

        return patches

    # ─── Private: Augmentation ────────────────────────────

    def _has_augmentation(self) -> bool:
        return any([
            self.config.aug_flip,
            self.config.aug_rotate,
            self.config.aug_noise,
            self.config.aug_brightness,
        ])

    def _augment(
        self,
        patches: np.ndarray,
        labels: np.ndarray,
        dates: List[str],
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """Augmented kopyalar üretir."""
        aug_patches = []
        aug_labels = []
        aug_dates = []
        rng = np.random.default_rng(42)

        for i in range(len(patches)):
            patch = patches[i]  # (C, H, W)
            label = labels[i]
            date = dates[i]

            augmented = []

            if self.config.aug_flip:
                # Horizontal flip
                augmented.append(patch[:, :, ::-1].copy())
                # Vertical flip
                augmented.append(patch[:, ::-1, :].copy())

            if self.config.aug_rotate:
                # 90° rotation
                augmented.append(np.rot90(patch, k=1, axes=(1, 2)).copy())
                # 270° rotation
                augmented.append(np.rot90(patch, k=3, axes=(1, 2)).copy())

            if self.config.aug_noise:
                noisy = patch + rng.normal(0, self.config.noise_std, patch.shape).astype(np.float32)
                augmented.append(noisy)

            if self.config.aug_brightness:
                br = self.config.brightness_range
                factor = 1.0 + rng.uniform(-br, br)
                augmented.append((patch * factor).astype(np.float32))

            for aug_p in augmented:
                aug_patches.append(aug_p)
                aug_labels.append(label)
                aug_dates.append(date)

        if not aug_patches:
            return np.zeros((0, *patches.shape[1:]), dtype=np.float32), np.array([], dtype=np.int64), []

        return (
            np.array(aug_patches, dtype=np.float32),
            np.array(aug_labels, dtype=np.int64),
            aug_dates,
        )

    # ─── Private: Split ───────────────────────────────────

    def _split(self, labels: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Stratified train/val/test split."""
        N = len(labels)
        rng = np.random.default_rng(42)
        indices = rng.permutation(N)

        # Stratified: sınıf başına ayrı split
        unique_labels = np.unique(labels)
        train_idx, val_idx, test_idx = [], [], []

        for lbl in unique_labels:
            lbl_indices = indices[labels[indices] == lbl]
            n_lbl = len(lbl_indices)

            n_train = max(1, int(n_lbl * self.config.train_ratio))
            n_val = max(0, int(n_lbl * self.config.val_ratio))
            # Kalan test'e gider

            train_idx.extend(lbl_indices[:n_train])
            val_idx.extend(lbl_indices[n_train:n_train + n_val])
            test_idx.extend(lbl_indices[n_train + n_val:])

        return (
            np.array(train_idx, dtype=np.int64),
            np.array(val_idx, dtype=np.int64),
            np.array(test_idx, dtype=np.int64),
        )

    # ─── Private: Metadata ────────────────────────────────

    def _build_metadata(
        self,
        patches: np.ndarray,
        labels: np.ndarray,
        channel_names: List[str],
        train_idx: np.ndarray,
        val_idx: np.ndarray,
        test_idx: np.ndarray,
        dates: List[str],
    ) -> Dict[str, Any]:
        N, C, H, W = patches.shape
        unique, counts = np.unique(labels, return_counts=True)

        class_distribution = {}
        for u, c in zip(unique, counts):
            class_name = self.config.label_names[int(u)] if int(u) < len(self.config.label_names) else f"Class_{u}"
            class_distribution[class_name] = int(c)

        # Band istatistikleri
        band_stats = {}
        for c_idx, c_name in enumerate(channel_names):
            c_data = patches[:, c_idx]
            band_stats[c_name] = {
                "mean": float(np.nanmean(c_data)),
                "std": float(np.nanstd(c_data)),
                "min": float(np.nanmin(c_data)),
                "max": float(np.nanmax(c_data)),
                "median": float(np.nanmedian(c_data)),
            }

        return {
            "dataset_info": {
                "total_patches": N,
                "patch_shape": [C, H, W],
                "channels": channel_names,
                "n_channels": C,
                "dtype": str(patches.dtype),
            },
            "split": {
                "train": len(train_idx),
                "val": len(val_idx),
                "test": len(test_idx),
                "train_ratio": self.config.train_ratio,
                "val_ratio": self.config.val_ratio,
                "test_ratio": self.config.test_ratio,
            },
            "class_distribution": class_distribution,
            "label_thresholds": self.config.label_thresholds,
            "label_names": self.config.label_names,
            "normalization": self._norm_params,
            "band_statistics": band_stats,
            "augmentation": {
                "flip": self.config.aug_flip,
                "rotate": self.config.aug_rotate,
                "noise": self.config.aug_noise,
                "brightness": self.config.aug_brightness,
            },
            "config": asdict(self.config),
            "unique_dates": sorted(set(dates)),
            "n_temporal_steps": len(set(dates)),
        }

    # ─── Private: README ──────────────────────────────────

    def _generate_readme(self, dataset: Dict[str, Any]) -> str:
        meta = dataset["metadata"]
        info = meta["dataset_info"]
        split = meta["split"]
        dist = meta["class_distribution"]

        lines = [
            "# GEO-AGRI ML Dataset",
            "",
            "Bu veri seti GEO-AGRI Satellite Intelligence platformu tarafından üretilmiştir.",
            "",
            "## Veri Seti Bilgileri",
            f"- **Toplam Patch**: {info['total_patches']}",
            f"- **Patch Boyutu**: {info['patch_shape']}",
            f"- **Kanal Sayısı**: {info['n_channels']}",
            f"- **Kanallar**: {', '.join(info['channels'])}",
            f"- **Veri Tipi**: {info['dtype']}",
            "",
            "## Split",
            f"- Train: {split['train']} ({split['train_ratio']*100:.0f}%)",
            f"- Val: {split['val']} ({split['val_ratio']*100:.0f}%)",
            f"- Test: {split['test']} ({split['test_ratio']*100:.0f}%)",
            "",
            "## Sınıf Dağılımı",
        ]
        for cls, cnt in dist.items():
            lines.append(f"- {cls}: {cnt}")

        lines.extend([
            "",
            "## Kullanım (PyTorch)",
            "```python",
            "import numpy as np",
            "from torch.utils.data import Dataset, DataLoader",
            "",
            "class SatelliteDataset(Dataset):",
            "    def __init__(self, split='train'):",
            "        self.X = np.load(f'X_{split}.npy')",
            "        self.y = np.load(f'y_{split}.npy')",
            "",
            "    def __len__(self):",
            "        return len(self.X)",
            "",
            "    def __getitem__(self, idx):",
            "        return self.X[idx], self.y[idx]",
            "",
            "train_ds = SatelliteDataset('train')",
            "loader = DataLoader(train_ds, batch_size=32, shuffle=True)",
            "```",
            "",
            "## Kullanım (TensorFlow)",
            "```python",
            "import numpy as np",
            "import tensorflow as tf",
            "",
            "X_train = np.load('X_train.npy')",
            "y_train = np.load('y_train.npy')",
            "",
            "# Channel-first → Channel-last",
            "X_train = np.transpose(X_train, (0, 2, 3, 1))",
            "",
            "dataset = tf.data.Dataset.from_tensor_slices((X_train, y_train))",
            "dataset = dataset.shuffle(1000).batch(32).prefetch(tf.data.AUTOTUNE)",
            "```",
        ])

        return "\n".join(lines)
