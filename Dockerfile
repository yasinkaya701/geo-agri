FROM python:3.11-slim

# System-level dependencies for spatial/GIS libraries and building compiled extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    libexpat1 \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    libgeos-dev \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Environment variables for compiling dependencies like rasterio/gdal
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Set up working directory
WORKDIR /app

# Install dependencies first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure startup script is executable
RUN chmod +x start_railway.sh

# Expose Streamlit port
EXPOSE 8080

# Run the startup script
CMD ["./start_railway.sh"]
