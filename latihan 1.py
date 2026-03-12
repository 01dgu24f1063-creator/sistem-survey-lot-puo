import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, Point
import folium
from streamlit_folium import folium_static
from folium.plugins import Fullscreen, MiniMap
import math
from pyproj import Transformer
import io
import zipfile
import time

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Sistem Survey Lot PUO", layout="wide", initial_sidebar_state="collapsed")

# --- 2. PENGURUSAN STATE (LOGIN & SECURITY) ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "login_attempts" not in st.session_state:
    st.session_state["login_attempts"] = 0
if "last_attempt_time" not in st.session_state:
    st.session_state["last_attempt_time"] = 0

NAMA_USER_MAP = {1: "NUR FADILAH ADHA", 2: "SITI ZULAIKA", 3: "HASLIZA"}

# --- 3. FUNGSI UTILITI ---
def decimal_to_dms(deg):
    d = int(deg)
    m = int((deg - d) * 60)
    s = (deg - d - m/60) * 3600
    return f"{d:03d}°{m:02d}'{s:02.0f}\""

def calculate_bearing_dist(p1, p2):
    de = p2['E'] - p1['E']
    dn = p2['N'] - p1['N']
    dist = math.sqrt(de**2 + dn**2)
    bearing_deg = math.degrees(math.atan2(de, dn)) % 360
    rotation = math.degrees(math.atan2(dn, de)) 
    if rotation > 90: rotation -= 180
    if rotation < -90: rotation += 180
    return bearing_deg, dist, -rotation

def create_zip_geojson(df, data_ukur, luas, perimeter):
    df_ukur = pd.DataFrame(data_ukur)
    point_data = []
    for i, row in df.iterrows():
        info_ukur = df_ukur[df_ukur['KE'] == row['STN']]
        point_data.append({
            'id': i + 1, 'stn': row['STN'],
            'bering': info_ukur['BEARING'].values[0] if not info_ukur.empty else "-",
            'jarak': info_ukur['JARAK'].values[0] if not info_ukur.empty else "-",
            'E': row['E'], 'N': row['N'], 'type': 'Station',
            'geometry': Point(row['E'], row['N'])
        })
    gdf_points = gpd.GeoDataFrame(point_data, crs="EPSG:4390").to_crs("EPSG:4326")
    poly_geom = Polygon(list(zip(df.E, df.N)))
    gdf_poly = gpd.GeoDataFrame({
        'type': ['Lot Kawasan'], 'luas': [f"{luas:.3f}"], 'perimeter': [f"{perimeter:.3f}"],
        'geometry': [poly_geom]
    }, crs="EPSG:4390").to_crs("EPSG:4326")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("1_Stesen_Points.geojson", gdf_points.to_json())
        zf.writestr("2_Lot_Polygon.geojson", gdf_poly.to_json())
    return zip_buffer.getvalue()

# --- 4. SISTEM LOG MASUK ---
if not st.session_state["logged_in"]:
    st.markdown("""<style>.login-header { text-align: center; font-size: 40px; font-weight: bold; color: #333; margin-bottom: 20px; }.stButton button { background-color: #00BFFF; color: white; width: 100%; height: 50px; }</style>""", unsafe_allow_html=True)
    _, col2, _ = st.columns([1, 2, 1])
    with col2:
        st.markdown('<p class="login-header">🔐 Sistem Survey Lot PUO</p>', unsafe_allow_html=True)
        input_id = st.number_input("👤 Masukkan ID:", min_value=1, step=1)
        input_pwd = st.text_input("🔑 Masukkan Kata Laluan:", type="password")
        placeholder = st.empty()
        time_since_last = time.time() - st.session_state["last_attempt_time"]
        if st.session_state["login_attempts"] >= 3 and time_since_last < 10:
            while time_since_last < 10:
                remaining = int(10 - time_since_last)
                placeholder.error(f"🚫 Terlalu banyak cubaan! Sila tunggu {remaining} saat lagi...")
                time.sleep(1)
                time_since_last = time.time() - st.session_state["last_attempt_time"]
            st.rerun()
        else:
            if st.button("Log Masuk"):
                if input_pwd == "admin123":
                    st.session_state["login_attempts"] = 0
                    st.session_state["logged_in"] = True
                    st.session_state["user_id"] = input_id
                    st.session_state["user_name"] = NAMA_USER_MAP.get(input_id, f"USER {input_id}")
                    st.rerun()
                else:
                    st.session_state["login_attempts"] += 1
                    st.session_state["last_attempt_time"] = time.time()
                    st.rerun()
    st.stop()

# --- 5. APLIKASI UTAMA ---
with st.sidebar:
    st.markdown(f"""<div style="background-color: #00BFFF; padding: 20px; border-radius: 10px; text-align: center; color: white; margin-bottom: 20px;"><img src="https://www.w3schools.com/howto/img_avatar.png" style="width: 80px; border-radius: 50%; margin-bottom: 10px;"><h3 style="margin: 0;">Hai, {st.session_state['user_name'].split()[0].lower()}!</h3><p style="margin: 0; font-size: 0.9em; font-weight: bold;">{st.session_state['user_name']}</p></div>""", unsafe_allow_html=True)
    if st.button("Log Keluar"):
        st.session_state["logged_in"] = False
        st.rerun()
    st.header("⚙️ Kawalan Fail")
    uploaded_file = st.file_uploader("Upload fail CSV (STN, E, N)", type=['csv'])

data_ukur = []
df = None
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    if all(col in df.columns for col in ['STN', 'E', 'N']):
        for i in range(len(df)):
            p1 = df.iloc[i]
            p2 = df.iloc[(i + 1) % len(df)]
            brg, dst, rot = calculate_bearing_dist(p1, p2)
            data_ukur.append({
                'DARI': p1['STN'], 'KE': p2['STN'],
                'BEARING': decimal_to_dms(brg), 'JARAK': f"{dst:.3f}m",
                'mid_e': (p1['E']+p2['E'])/2, 'mid_n': (p1['N']+p2['N'])/2,
                'ROTATION': rot
            })
        poly_obj = Polygon(list(zip(df['E'], df['N'])))
        st.session_state["luas"] = poly_obj.area
        st.session_state["perimeter"] = poly_obj.length

    with st.sidebar:
        st.divider()
        st.header("📤 Eksport Data")
        zip_data = create_zip_geojson(df, data_ukur, st.session_state["luas"], st.session_state["perimeter"])
        st.download_button("📥 Download ZIP untuk QGIS", zip_data, f"Survey_PUO_{st.session_state['user_name'].replace(' ', '_')}.zip", "application/zip")
        st.divider()
        st.header("⚙️ Kawalan Paparan")
        saiz_marker = st.slider("Saiz Marker", 10, 40, 22)
        saiz_teks = st.slider("Saiz Teks", 6, 25, 12)
        warna_poli = st.color_picker("Warna Poligon", "#FFFF00")

# --- TAMBAH LOGO DAN TAJUK ---
col1, col2 = st.columns([1, 10])
with col1:
    st.image("logo-puo.png.png", width=100)
with col2:
    st.title("🗺️ Web GIS Visualisasi Poligon (EPSG:4390)")

if uploaded_file and df is not None:
    c1, c2, c3 = st.columns(3)
    c1.metric("Luas (m²)", f"{st.session_state['luas']:.3f}")
    c2.metric("Perimeter (m)", f"{st.session_state['perimeter']:.3f}")
    c3.metric("Jumlah Stesen", len(df))

    transformer = Transformer.from_crs("EPSG:4390", "EPSG:4326", always_xy=True)
    center_lon, center_lat = transformer.transform(df['E'].mean(), df['N'].mean())
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=19, max_zoom=28, control_scale=True)
    folium.TileLayer('openstreetmap', name='Peta Jalan (OSM)', max_zoom=28).add_to(m)
    folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Google Hybrid (Satelit)', max_zoom=28, max_native_zoom=20, overlay=False, control=True, show=True).add_to(m)

    # Cipta FeatureGroup untuk organisasi lapisan
    fg_survey = folium.FeatureGroup(name="Data Survey (Lot & Stesen)", show=True)
    fg_labels = folium.FeatureGroup(name="Label Bering & Jarak", show=True)

    # Poligon dengan Popup
    poly_latlon = [transformer.transform(e, n)[::-1] for e, n in list(zip(df['E'], df['N']))]
    popup_lot = f"<b>Info Lot</b><br>Luas: {st.session_state['luas']:.3f} m²<br>Perimeter: {st.session_state['perimeter']:.3f} m"
    folium.Polygon(poly_latlon, color=warna_poli, fill=True, fill_opacity=0.3, weight=3).add_child(folium.Popup(popup_lot)).add_to(fg_survey)

    # Marker Stesen dengan Popup
    for _, row in df.iterrows():
        lon, lat = transformer.transform(row['E'], row['N'])
        popup_stn = f"<b>Stesen {int(row['STN'])}</b><br>E: {row['E']:.3f}<br>N: {row['N']:.3f}"
        folium.Marker([lat, lon], icon=folium.DivIcon(html=f'''<div style="background:red; color:white; border:2px solid white; border-radius:50%; width:{saiz_marker}px; height:{saiz_marker}px; display:flex; justify-content:center; align-items:center; font-weight:bold; font-size:{saiz_teks-2}pt;">{int(row["STN"])}</div>''')).add_child(folium.Popup(popup_stn)).add_to(fg_survey)

    # Label Bearing & Jarak (Dimasukkan ke dalam fg_labels agar boleh di-toggle)
    for item in data_ukur:
        lon, lat = transformer.transform(item['mid_e'], item['mid_n'])
        folium.Marker([lat, lon], icon=folium.DivIcon(html=f'''<div style="transform:rotate({item["ROTATION"]}deg); font-size:{saiz_teks}pt; color:{warna_poli}; font-weight:bold; text-shadow:2px 2px 4px black; white-space:nowrap; text-align:center;">{item["BEARING"]}<br>{item["JARAK"]}</div>''')).add_to(fg_labels)

    fg_survey.add_to(m)
    fg_labels.add_to(m)
    
    Fullscreen().add_to(m)
    MiniMap(tile_layer='openstreetmap', position='bottomright', width=120, height=120).add_to(m)
    folium.LayerControl(position='topright', collapsed=False).add_to(m)
    folium_static(m, width=1100)
    st.dataframe(pd.DataFrame(data_ukur)[['DARI', 'KE', 'BEARING', 'JARAK']], use_container_width=True)
else:  
    st.info("👋 Sila muat naik fail CSV di sidebar untuk memulakan.")