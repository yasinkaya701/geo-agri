import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import shape, mapping
from typing import Optional, Dict, Any, Tuple
from src.config import logger
from src.tkgm.megsis_client import MegsisClient
from src.exceptions import TKGMError

def render_tkgm_selectors() -> Optional[Dict[str, Any]]:
    """İl, İlçe, Mahalle, Ada, Parsel seçim kutularını render eder.
    
    Sorgulanan parselin GeoJSON verisini döner.
    """
    if "megsis_client" not in st.session_state:
        st.session_state.megsis_client = MegsisClient()
    client: MegsisClient = st.session_state.megsis_client
    
    st.caption("Resmi ada/parsel numarası ile tarla poligonunu otomatik sorgulayın.")
    
    # İlleri çek (Cache'li)
    @st.cache_data(show_spinner="İller yükleniyor...")
    def load_provinces():
        try:
            return client.get_provinces()
        except Exception as e:
            st.error(f"İller yüklenemedi: {e}")
            return []
            
    provinces = load_provinces()
    if not provinces:
        st.warning("TKGM servisi şu an yanıt vermiyor. Lütfen harita üzerinden çizim yapın.")
        return None
        
    province_names = [p["name"] for p in provinces]
    
    # Hızlı demo için varsayılan olarak Burdur
    default_prov_idx = 0
    for idx, p in enumerate(provinces):
        if p["name"].upper() == "BURDUR":
            default_prov_idx = idx
            break

    # İl ve İlçe yan yana
    col_il, col_ilce = st.columns(2)
    with col_il:
        selected_province_name = st.selectbox(
            "İl", 
            province_names, 
            index=default_prov_idx,
            key="tkgm_prov"
        )
    
    selected_province_id = next(p["id"] for p in provinces if p["name"] == selected_province_name)
    
    # İlçeleri çek (Cache'li)
    @st.cache_data(show_spinner="İlçeler yükleniyor...")
    def load_districts(prov_id: int):
        try:
            return client.get_districts(prov_id)
        except Exception as e:
            return []
            
    districts = load_districts(selected_province_id)
    district_names = [d["name"] for d in districts]
    
    default_dist_idx = 0
    for idx, d in enumerate(districts):
        if d["name"].upper() == "MERKEZ":
            default_dist_idx = idx
            break
    
    with col_ilce:
        selected_district_name = st.selectbox(
            "İlçe", 
            district_names, 
            index=default_dist_idx if default_dist_idx < len(district_names) else 0,
            key=f"tkgm_dist_{selected_province_id}"
        )
    
    if not districts:
        st.warning("Bu ile ait ilçe verisi alınamadı.")
        return None
        
    selected_district_id = next(d["id"] for d in districts if d["name"] == selected_district_name)
    
    # Mahalleleri çek (Cache'li)
    @st.cache_data(show_spinner="Mahalleler yükleniyor...")
    def load_neighborhoods(dist_id: int):
        try:
            return client.get_neighborhoods(dist_id)
        except Exception as e:
            return []
            
    neighborhoods = load_neighborhoods(selected_district_id)
    neighborhood_names = [m["name"] for m in neighborhoods]
    
    default_neigh_idx = 0
    for idx, m in enumerate(neighborhoods):
        if m["name"].upper() == "İLYAS":
            default_neigh_idx = idx
            break
            
    selected_neighborhood_name = st.selectbox(
        "Mahalle / Köy", 
        neighborhood_names, 
        index=default_neigh_idx if default_neigh_idx < len(neighborhood_names) else 0,
        key=f"tkgm_neigh_{selected_district_id}"
    )
    
    if not neighborhoods:
        st.warning("Bu ilçeye ait mahalle/köy verisi alınamadı.")
        return None
        
    selected_neighborhood_id = next(m["id"] for m in neighborhoods if m["name"] == selected_neighborhood_name)
    
    # Ada ve Parsel Girişleri
    is_demo = (selected_province_name.upper() == "BURDUR" and 
               selected_district_name.upper() == "MERKEZ" and 
               selected_neighborhood_name.upper() == "İLYAS")
    
    default_ada = "389" if is_demo else ""
    default_parsel = "26" if is_demo else ""

    col_ada, col_parsel = st.columns(2)
    with col_ada:
        ada = st.text_input("Ada No", value=default_ada, key="tkgm_ada")
    with col_parsel:
        parsel = st.text_input("Parsel No", value=default_parsel, key="tkgm_parsel")
        
    btn_sorgula = st.button("🔍 Parsel Sorgula", type="primary", use_container_width=True)
    
    # Hızlı demo parsel yükleme
    if st.button("💡 Demo Tarlası Yükle (Burdur/İlyas)", use_container_width=True):
        demo_geojson = {
            "type": "Feature",
            "properties": {
                "ilAd": "BURDUR",
                "ilceAd": "MERKEZ",
                "mahalleAd": "İLYAS",
                "adaNo": "389",
                "parselNo": "26",
                "alan": "7.722,87",
                "nitelik": "Tarla"
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [30.12993, 37.75737],
                    [30.13, 37.75765],
                    [30.12968, 37.7578],
                    [30.12966, 37.75792],
                    [30.12952, 37.75803],
                    [30.12931, 37.75778],
                    [30.12905, 37.75753],
                    [30.12893, 37.75744],
                    [30.12909, 37.75732],
                    [30.12923, 37.75721],
                    [30.12912, 37.75709],
                    [30.12891, 37.75685],
                    [30.12907, 37.75678],
                    [30.12919, 37.75676],
                    [30.12941, 37.75665],
                    [30.12955, 37.75689],
                    [30.12974, 37.75712],
                    [30.12993, 37.75737]
                ]]
            }
        }
        st.session_state.active_geojson = demo_geojson
        st.session_state.active_geometry = shape(demo_geojson["geometry"])
        st.session_state.tkgm_properties = demo_geojson["properties"]
        st.session_state.field_source = "TKGM"
        st.rerun()

    if btn_sorgula:
        if not ada or not parsel:
            st.error("Lütfen sorgulamak istediğiniz Ada ve Parsel numaralarını girin.")
        else:
            with st.spinner("Parsel sınırları sorgulanıyor..."):
                try:
                    parcel_geojson = client.get_parcel(selected_neighborhood_id, ada, parsel)
                    # Session State'e kaydet
                    st.session_state.active_geojson = parcel_geojson
                    st.session_state.active_geometry = shape(parcel_geojson["geometry"])
                    st.session_state.tkgm_properties = parcel_geojson["properties"]
                    st.session_state.field_source = "TKGM"
                    st.rerun()
                except Exception as e:
                    msg = getattr(e, "message", str(e))
                    st.markdown(f"""
                    <div class="saas-error">
                        <span style="font-size: 18px;">⚠️</span>
                        <div>
                            <strong style="display:block; font-weight:700; color:#B91C1C;">Kadastro Sorgu Hatası</strong>
                            <span style="font-size: 13px; color: #DC2626;">{msg}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    st.info("💡 Ada/Parsel numaralarını kontrol edin veya harita üzerinden manuel çizim yapın.")
                
    # Sorgulanan parselin bilgileri
    if "tkgm_properties" in st.session_state and st.session_state.get("field_source") == "TKGM":
        props = st.session_state.tkgm_properties
        st.markdown(f"""
        <div class="info-card">
            <div class="info-card-header">📋 Kadastro Detay Kartı</div>
            <div class="info-card-row">
                <span class="info-card-label">📍 Lokasyon</span>
                <span class="info-card-value">{props.get('ilAd') or '-'} / {props.get('ilceAd') or '-'} / {props.get('mahalleAd') or '-'}</span>
            </div>
            <div class="info-card-row">
                <span class="info-card-label">📦 Ada / Parsel</span>
                <span class="info-card-value">{props.get('adaNo') or '-'} / {props.get('parselNo') or '-'}</span>
            </div>
            <div class="info-card-row">
                <span class="info-card-label">📐 Tapu Alanı</span>
                <span class="info-card-value">{props.get('alan') or '-'} m²</span>
            </div>
            <div class="info-card-row">
                <span class="info-card-label">🌾 Nitelik</span>
                <span class="info-card-value">{props.get('nitelik') or '-'}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)


def render_folium_map() -> None:
    """İnteraktif haritayı çizer.
    
    Hem çizilen geometrileri yakalar hem de TKGM'den sorgulanan poligonu gösterir.
    """
    st.caption("Çizim araçları ile tarla sınırı belirleyin veya TKGM parseli sorgulayın.")
    
    # Harita merkezleme ve zoom ayarı
    center = [39.0, 35.0]  # Türkiye merkezi
    zoom = 6
    
    # Eğer aktif bir geometri varsa haritayı onun merkezine odakla
    if "active_geometry" in st.session_state:
        geom = st.session_state.active_geometry
        centroid = geom.centroid
        center = [centroid.y, centroid.x]
        zoom = 15  # Tarlaya yakınlaş
        
    # Folium haritası oluştur
    m = folium.Map(
        location=center, 
        zoom_start=zoom, 
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google Satellite"
    )
    
    # Eğer aktif bir geometri varsa haritayı tam sınırlarına sığdır (fit_bounds)
    if "active_geometry" in st.session_state:
        bounds = st.session_state.active_geometry.bounds  # (minx, miny, maxx, maxy)
        # fit_bounds formatı: [[min_lat, min_lon], [max_lat, max_lon]]
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    
    # TKGM poligonunu haritaya ekle
    if "active_geojson" in st.session_state and st.session_state.get("field_source") == "TKGM":
        folium.GeoJson(
            st.session_state.active_geojson,
            name="TKGM Resmi Sınır",
            style_function=lambda x: {
                "fillColor": "#10B981",
                "color": "#10B981",
                "weight": 3,
                "fillOpacity": 0.2
            }
        ).add_to(m)
        
    # Çizim aracını (Draw) ekle
    draw_control = Draw(
        export=False,
        filename="drawn_field.geojson",
        position="topleft",
        draw_options={
            "polyline": False,
            "polygon": {
                "allowIntersection": False,
                "shapeOptions": {
                    "color": "#3B82F6",
                    "fillColor": "#3B82F6",
                    "fillOpacity": 0.2,
                    "weight": 2.5
                }
            },
            "rectangle": {
                "shapeOptions": {
                    "color": "#3B82F6",
                    "fillColor": "#3B82F6",
                    "fillOpacity": 0.2,
                    "weight": 2.5
                }
            },
            "circle": False,
            "marker": False,
            "circlemarker": False
        },
        edit_options={
            "poly": {"allowIntersection": False}
        }
    )
    draw_control.add_to(m)
    
    # Haritayı Streamlit'te göster
    map_output = st_folium(m, width="100%", height=480, key="map_field")
    
    # Çizilen geometriyi kontrol et
    if map_output and map_output.get("last_active_drawing"):
        drawing = map_output["last_active_drawing"]
        geom_type = drawing.get("geometry", {}).get("type")
        
        # Sadece Poligon ve Dikdörtgen kabul ediyoruz
        if geom_type in ["Polygon", "MultiPolygon"]:
            try:
                shapely_shape = shape(drawing["geometry"])
                
                if ("active_geometry" not in st.session_state or 
                    st.session_state.get("field_source") != "Drawn" or
                    not st.session_state.active_geometry.equals(shapely_shape)):
                    
                    st.session_state.active_geometry = shapely_shape
                    st.session_state.active_geojson = drawing
                    st.session_state.field_source = "Drawn"
                    
                    # Custom properties oluştur
                    st.session_state.tkgm_properties = {
                        "ilAd": "Manuel Çizim",
                        "ilceAd": "-",
                        "mahalleAd": "-",
                        "adaNo": "-",
                        "parselNo": "-",
                        "alan": f"{shapely_shape.area * 1e8:.2f}", # Yaklaşık metrekare hesabı
                        "nitelik": "Kullanıcı Çizimi"
                    }
                    st.rerun()
            except Exception as e:
                logger.error(f"Çizilen geometri ayrıştırılamadı: {e}")
