import numpy as np
from scipy.ndimage import convolve

def apply_sobel_edge(image: np.ndarray) -> np.ndarray:
    """Sobel kenar algılama filtresini NumPy ve SciPy ile uygular.
    Giriş görüntüsü 2D (tek kanal) veya 3D (çok kanallı) olabilir.
    """
    # Sobel çekirdekleri (Kernels)
    Kx = np.array([[-1, 0, 1],
                   [-2, 0, 2],
                   [-1, 0, 1]], dtype=np.float32)
    Ky = np.array([[-1, -2, -1],
                   [ 0,  0,  0],
                   [ 1,  2,  1]], dtype=np.float32)
    
    if len(image.shape) == 2:
        # Tek kanal (grayscale veya spektral indeks)
        img_clean = np.nan_to_num(image, nan=0.0)
        gx = convolve(img_clean, Kx)
        gy = convolve(img_clean, Ky)
        magnitude = np.sqrt(gx**2 + gy**2)
        # Normalizasyon
        mag_max = magnitude.max()
        if mag_max > 0:
            magnitude = magnitude / mag_max
        return magnitude
    else:
        # Çok kanallı (RGB)
        channels = []
        for c in range(image.shape[2]):
            img_clean = np.nan_to_num(image[:, :, c], nan=0.0)
            gx = convolve(img_clean, Kx)
            gy = convolve(img_clean, Ky)
            magnitude = np.sqrt(gx**2 + gy**2)
            mag_max = magnitude.max()
            if mag_max > 0:
                magnitude = magnitude / mag_max
            channels.append(magnitude)
        return np.dstack(channels)

def apply_gaussian_blur(image: np.ndarray, sigma: float = 1.0) -> np.ndarray:
    """Gaussian blur filtresini 2D konvolüsyon ile uygular."""
    # 5x5 Gaussian Kernel oluştur
    size = 5
    x, y = np.mgrid[-size//2 + 1:size//2 + 1, -size//2 + 1:size//2 + 1]
    g = np.exp(-((x**2 + y**2) / (2.0 * sigma**2)))
    kernel = g / g.sum()
    
    if len(image.shape) == 2:
        img_clean = np.nan_to_num(image, nan=0.0)
        return convolve(img_clean, kernel)
    else:
        channels = []
        for c in range(image.shape[2]):
            img_clean = np.nan_to_num(image[:, :, c], nan=0.0)
            channels.append(convolve(img_clean, kernel))
        return np.dstack(channels)

def apply_contrast_stretching(image: np.ndarray) -> np.ndarray:
    """Kontrast germe (Min-Max normalizasyonu) uygular."""
    if len(image.shape) == 2:
        img_clean = np.nan_to_num(image, nan=0.0)
        min_val = np.percentile(img_clean, 2)
        max_val = np.percentile(img_clean, 98)
        if max_val - min_val > 1e-5:
            stretched = (img_clean - min_val) / (max_val - min_val)
        else:
            stretched = img_clean
        return np.clip(stretched, 0.0, 1.0)
    else:
        channels = []
        for c in range(image.shape[2]):
            img_clean = np.nan_to_num(image[:, :, c], nan=0.0)
            min_val = np.percentile(img_clean, 2)
            max_val = np.percentile(img_clean, 98)
            if max_val - min_val > 1e-5:
                stretched = (img_clean - min_val) / (max_val - min_val)
            else:
                stretched = img_clean
            channels.append(np.clip(stretched, 0.0, 1.0))
        return np.dstack(channels)

def apply_grayscale(image: np.ndarray) -> np.ndarray:
    """RGB görüntüsünü tek kanallı gri tonlamaya çevirir.
    Luminosity formülü: 0.299*R + 0.587*G + 0.114*B
    """
    if len(image.shape) == 2:
        return image
    else:
        r, g, b = image[:, :, 0], image[:, :, 1], image[:, :, 2]
        gray = 0.299 * r + 0.587 * g + 0.114 * b
        return gray
