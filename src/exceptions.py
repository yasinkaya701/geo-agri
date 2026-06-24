class TarimUyduError(Exception):
    """Tarım Uydu uygulamasındaki tüm hataların temel sınıfı."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class TKGMError(TarimUyduError):
    """TKGM MEGSIS API işlemlerindeki hatalar."""
    pass


class STACQueryError(TarimUyduError):
    """Microsoft Planetary Computer STAC API arama hataları."""
    pass


class RasterProcessingError(TarimUyduError):
    """Görüntü işleme, kırpma veya maskeleme esnasındaki hatalar."""
    pass


class GeometryError(TarimUyduError):
    """Coğrafi koordinat dönüşümleri veya poligon sınırlandırma hataları."""
    pass
