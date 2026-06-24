import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
from src.config import DATABASE_URL, logger

class DatabaseManager:
    _pool = None

    @classmethod
    def initialize_pool(cls):
        """Bağlantı havuzunu (Connection Pool) başlatır."""
        if cls._pool is None:
            try:
                logger.info("Veritabanı bağlantı havuzu başlatılıyor...")
                cls._pool = SimpleConnectionPool(
                    minconn=1,
                    maxconn=20,
                    dsn=DATABASE_URL
                )
                logger.info("Bağlantı havuzu başarıyla oluşturuldu.")
            except Exception as e:
                logger.error(f"Bağlantı havuzu başlatılamadı: {e}")
                raise RuntimeError(f"Database connection pool initialization failed: {e}")

    @classmethod
    def get_connection(cls):
        """Bağlantı havuzundan bir bağlantı alır."""
        if cls._pool is None:
            cls.initialize_pool()
        try:
            return cls._pool.getconn()
        except Exception as e:
            logger.error(f"Bağlantı havuzundan bağlantı alınamadı: {e}")
            raise RuntimeError(f"Failed to get database connection: {e}")

    @classmethod
    def release_connection(cls, conn):
        """Bağlantıyı havuza geri iade eder."""
        if cls._pool is not None and conn is not None:
            cls._pool.putconn(conn)

    @staticmethod
    def initialize_schema():
        """Sistem için gerekli PostGIS uzantısını, tabloları ve GiST indekslerini oluşturur."""
        conn = None
        cur = None
        try:
            conn = DatabaseManager.get_connection()
            cur = conn.cursor()
            
            logger.info("PostGIS uzantısı kontrol ediliyor...")
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            
            logger.info("Veritabanı tabloları oluşturuluyor...")
            
            # Fields Tablosu
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fields (
                    id UUID PRIMARY KEY,
                    user_id VARCHAR(100) NOT NULL,
                    name VARCHAR(150),
                    geom GEOMETRY(Polygon, 4326) NOT NULL,
                    bbox DOUBLE PRECISION[] NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Mekânsal GiST indeksi
            cur.execute("CREATE INDEX IF NOT EXISTS fields_geom_idx ON fields USING GIST (geom);")
            
            # Tarihsel Metrikler Tablosu
            cur.execute("""
                CREATE TABLE IF NOT EXISTS field_historical_metrics (
                    field_id UUID REFERENCES fields(id) ON DELETE CASCADE,
                    year INT NOT NULL,
                    ndvi_trends JSONB NOT NULL,
                    matrix_path VARCHAR(512),
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (field_id, year)
                );
            """)
            
            conn.commit()
            logger.info("Veritabanı şeması ve GiST indeksleri başarıyla kuruldu.")
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Veritabanı şeması oluşturulurken hata: {e}")
            raise RuntimeError(f"Database schema initialization failed: {e}")
        finally:
            if cur:
                cur.close()
            if conn:
                DatabaseManager.release_connection(conn)
