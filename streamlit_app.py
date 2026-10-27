import json
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

import imageio_ffmpeg
import pandas as pd
import streamlit as st

try:
    from app import load_config, process_video
    HAS_BACKEND = True
except ImportError:
    HAS_BACKEND = False

ROOT = Path(__file__).resolve().parent

# ==========================================
# CONVERSIÓN DE VIDEO PARA NAVEGADOR (H.264)
# ==========================================

def browser_video(source: Path) -> Path:
    """Recodifica el MP4 de salida a H.264 para compatibilidad nativa en navegadores web."""
    target = source.with_name(source.stem + "_web.mp4")
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-y", "-i", str(source),
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-movflags", "+faststart", str(target)
        ],
        check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return target

# ==========================================
# CONFIGURACIÓN Y ESTILOS
# ==========================================

st.set_page_config(
    page_title="Vision City | Sistema de Gestión Semafórica",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
/* FONDO AZUL PIZARRA NOCTURNO (MÁS CLARO Y ELEGANTE) */
    .stApp {
        background: radial-gradient(circle at 50% 15%, #1E293B 0%, #111827 85%) !important;
        color: #F8FAFC !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* BARRA SUPERIOR PRINCIPAL */
    .top-header-bar {
        background: linear-gradient(90deg, #0B1118 0%, #131E29 50%, #0B1118 100%);
        border-bottom: 2px solid rgba(16, 185, 129, 0.4);
        padding: 16px 28px;
        margin: -60px -50px 25px -50px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    }

    /* TÍTULO EN UN SOLO COLOR VERDE SOBRIO */
    .top-header-title {
        color: #10B981;
        font-size: 1.8rem;
        font-weight: 900;
        letter-spacing: 1px;
        margin: 0;
    }

    .top-header-subtitle {
        color: #94A3B8;
        font-size: 0.95rem;
        font-weight: 500;
        margin: 2px 0 0 0;
    }

    [data-testid="stSidebar"] {
        background-color: #131E29 !important;
        border-right: 1px solid #1E293B !important;
    }

    [data-testid="stSidebar"] *, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {
        color: #F1F5F9 !important;
    }

    div[data-baseweb="select"] > div {
        background-color: #0B1118 !important;
        border: 1px solid #10B981 !important;
        border-radius: 10px !important;
    }

    div[data-baseweb="select"] svg { fill: #10B981 !important; }

    [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"], [role="option"] {
        background-color: #0B1118 !important;
        color: #F8FAFC !important;
    }

    /* TARJETAS CON BORDE GRADIENTE DE SEMÁFORO */
    .card-box {
        background: rgba(19, 30, 41, 0.75);
        border-radius: 16px;
        padding: 22px;
        backdrop-filter: blur(12px);
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
        margin-bottom: 20px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        position: relative;
        overflow: hidden;
    }

    .card-box::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, #10B981 0%, #F59E0B 50%, #EF4444 100%);
    }

    .card-status-green {
        background: rgba(16, 185, 129, 0.1);
        border: 1px solid #10B981;
        border-radius: 16px;
        padding: 22px;
        box-shadow: 0 0 25px rgba(16, 185, 129, 0.18);
        margin-bottom: 15px;
        position: relative;
        overflow: hidden;
    }

    .card-status-green::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, #10B981 0%, #34D399 100%);
    }

    [data-testid="stMetric"] {
        background: rgba(19, 30, 41, 0.85) !important;
        border: 1px solid #1E293B !important;
        border-left: 4px solid #10B981 !important;
        border-radius: 12px !important;
        padding: 16px !important;
    }

    [data-testid="stMetricLabel"] * {
        color: #94A3B8 !important;
        font-weight: 500 !important;
    }

    [data-testid="stMetricValue"] * {
        color: #F8FAFC !important;
        font-weight: 700 !important;
    }

    /* BOTÓN EN VERDE SÓLIDO */
    .stButton > button {
        background-color: #10B981 !important;
        color: #0B1118 !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 12px 24px !important;
        font-weight: 800 !important;
        letter-spacing: 0.5px !important;
        box-shadow: 0 4px 20px rgba(16, 185, 129, 0.35) !important;
        transition: all 0.25s ease !important;
    }

    .stButton > button:hover {
        transform: translateY(-2px) !important;
        background-color: #059669 !important;
        box-shadow: 0 6px 25px rgba(16, 185, 129, 0.5) !important;
    }

    .badge-pill {
        background: rgba(16, 185, 129, 0.15);
        color: #10B981;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }

    /* ESQUEMA REALISTA DE CALLES EN 2D CON SEÑAL STOP Y ASFALTO */
    .intersection-real {
        width: 100%;
        height: 200px;
        background-color: #0A0F17;
        border-radius: 14px;
        border: 1px solid #334155;
        position: relative;
        overflow: hidden;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: inset 0 0 20px rgba(0,0,0,0.8);
    }
    
    /* CALLES CON COLOR ASFALTO DE REALISMO URBANO */
    .asphalt-h {
        position: absolute;
        width: 100%;
        height: 70px;
        background: #1C2430;
        border-top: 2px solid #475569;
        border-bottom: 2px solid #475569;
    }

    .asphalt-v {
        position: absolute;
        height: 100%;
        width: 70px;
        background: #1C2430;
        border-left: 2px solid #475569;
        border-right: 2px solid #475569;
    }

    /* LÍNEAS AMARILLAS CONTINUAS CENTRO */
    .line-yellow-h {
        position: absolute;
        width: 100%;
        height: 2px;
        background: #F59E0B;
        box-shadow: 0 0 4px rgba(245, 158, 11, 0.5);
    }

    .line-yellow-v {
        position: absolute;
        height: 100%;
        width: 2px;
        background: #F59E0B;
        box-shadow: 0 0 4px rgba(245, 158, 11, 0.5);
    }

    /* PASOS PEATONALES CEBRA */
    .zebra-h {
        position: absolute;
        width: 70px;
        height: 14px;
        background: repeating-linear-gradient(90deg, #E2E8F0, #E2E8F0 7px, transparent 7px, transparent 14px);
    }

    /* SEÑAL DE STOP OCTAGONAL */
    .stop-sign {
        position: absolute;
        top: 25px;
        right: 55px;
        width: 26px;
        height: 26px;
        background: #EF4444;
        clip-path: polygon(30% 0%, 70% 0%, 100% 30%, 100% 70%, 70% 100%, 30% 100%, 0% 70%, 0% 30%);
        color: white;
        font-size: 0.55rem;
        font-weight: 900;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 0 8px rgba(239, 68, 68, 0.6);
        border: 1px solid #FFFFFF;
        z-index: 10;
    }

    /* SEMÁFORO EN ESQUINA CON LUZ VERDE */
    .traffic-light-mini {
        position: absolute;
        bottom: 22px;
        left: 55px;
        width: 14px;
        height: 32px;
        background: #0F172A;
        border: 1px solid #475569;
        border-radius: 4px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: space-around;
        padding: 2px 0;
        z-index: 10;
    }

    .light-dot { width: 6px; height: 6px; border-radius: 50%; opacity: 0.3; }
    .light-dot.red { background: #EF4444; }
    .light-dot.yellow { background: #F59E0B; }
    .light-dot.green { background: #10B981; opacity: 1; box-shadow: 0 0 6px #10B981; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# HEADER SUPERIOR
# ==========================================

st.markdown("""
<div class="top-header-bar">
    <div>
        <h1 class="top-header-title">🚦 VISION CITY</h1>
        <p class="top-header-subtitle">Plataforma de Control Semafórico Adaptativo</p>
    </div>
    <div>
        <span class="badge-pill">🟢 Sistema Operativo</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# MENÚ LATERAL (PANEL TÉCNICO)
# ==========================================

st.sidebar.markdown("<h3 style='color:#10B981; font-weight:800;'>⚙️ Panel de Operación</h3>", unsafe_allow_html=True)
st.sidebar.divider()

st.sidebar.markdown("<h4 style='color:#F8FAFC;'>🎥 1. Selección de Fuente de Video</h4>", unsafe_allow_html=True)
mode_video = st.sidebar.radio("Origen del flujo vehicular:", ["Secuencia Local", "Cargar Archivo Externo"], index=0)

uploaded_video = None
source_video = None
video_display_name = "Secuencia predeterminada"

if mode_video == "Cargar Archivo Externo":
    uploaded_video = st.sidebar.file_uploader("Cargar flujo de video (.mp4, .avi, .mov)", type=["mp4", "avi", "mov"])
    if uploaded_video:
        video_display_name = uploaded_video.name
else:
    video_dir = ROOT / "data" / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    videos_disponibles = sorted([p for p in video_dir.glob("*") if p.suffix.lower() in {".mp4", ".avi", ".mov"}])
    if videos_disponibles:
        source_video = st.sidebar.selectbox("Secuencias disponibles:", videos_disponibles, format_func=lambda p: p.name)
        if source_video:
            video_display_name = source_video.name
    else:
        st.sidebar.warning("No se encontraron secuencias de video en el directorio local.")

st.sidebar.divider()
st.sidebar.markdown("<h4 style='color:#F8FAFC;'>🛣️ 2. Configuración de Intersección</h4>", unsafe_allow_html=True)

config_dir = ROOT / "config"
config_dir.mkdir(parents=True, exist_ok=True)
configs_disponibles = sorted([p for p in config_dir.glob("*.json")])

config_path = st.sidebar.selectbox("Matriz de la intersección (.JSON):", configs_disponibles, format_func=lambda p: p.name) if configs_disponibles else None
uploaded_config = st.sidebar.file_uploader("Cargar archivo de configuración .JSON", type=["json"])

config_data = None
try:
    if uploaded_config is not None:
        config_data = uploaded_config.getvalue()
    elif config_path:
        config_data = config_path.read_bytes()
except Exception:
    config_data = None

st.sidebar.divider()

btn_disabled = (config_data is None) or (source_video is None and uploaded_video is None) or not HAS_BACKEND

if st.sidebar.button("▶️ EJECUTAR INFERENCIA VIAL", disabled=btn_disabled, use_container_width=True):
    st.session_state.pop("result", None)
    status_box = st.empty()
    progress_bar = st.progress(0)

    def on_progress(done, total):
        if total:
            frac = min(done / total, 1.0)
            progress_bar.progress(frac, text=f"Procesando cuadros de video... {frac:.0%}")

    try:
        work_dir = ROOT / "output" / "ui"
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir = work_dir / uuid4().hex

        with tempfile.TemporaryDirectory(prefix="upload_", dir=work_dir) as temp_folder:
            temp_path = Path(temp_folder)
            selected_config = temp_path / "intersection.json"
            selected_config.write_bytes(config_data)
            load_config(selected_config)

            if uploaded_video is not None:
                source_video = temp_path / ("video" + Path(uploaded_video.name).suffix.lower())
                source_video.write_bytes(uploaded_video.getbuffer())

            status_box.info("Ejecutando pipeline de detección y algoritmos de asignación de fase...")
            res = process_video(
                source_video, selected_config, output_dir, on_progress,
                source_video_name=uploaded_video.name if uploaded_video is not None else str(source_video)
            )

            (output_dir / "configuration.json").write_bytes(config_data)

        status_box.info("Optimizando flujo de salida para renderizado...")
        try:
            res["web_video"] = browser_video(res["video"])
        except Exception:
            res["web_video"] = None

        st.session_state["result"] = res
        progress_bar.progress(1.0, text="Procesamiento completado")
        status_box.empty()
    except Exception as error:
        status_box.empty()
        st.error(f"Error durante el procesamiento del flujo: {str(error)[:150]}")

# ==========================================
# CONTENIDO PRINCIPAL
# ==========================================

st.markdown(f"<p style='color:#94A3B8; font-size:1rem; margin-bottom:15px;'>Secuencia activa en monitoreo: <b style='color:#10B981;'>{video_display_name}</b></p>", unsafe_allow_html=True)

m1, m2 = st.columns(2)
m1.metric("Modo de Control", "Adaptativo Dinámico", "Optimización en tiempo real")
m2.metric("Modelo de Percepción", "YOLOv8", "Conteo y segmentación de flujo")

st.markdown("<br>", unsafe_allow_html=True)

if "result" in st.session_state:
    res = st.session_state["result"]
    summary = res.get("summary", {})
    decision = summary.get("final_decision", {})
    phases = summary.get("traffic_phases", [])

    col_izq, col_der = st.columns([2.2, 1])

    with col_izq:
        st.markdown("<h3 style='color:#10B981; font-size:1.2rem;'>📹 Inferencia y Bounding Boxes</h3>", unsafe_allow_html=True)
        
        target_video = res.get("web_video") or res.get("video")
        if target_video and Path(target_video).exists():
            st.video(str(target_video))
        else:
            st.warning("No se pudo cargar la vista previa de la secuencia procesada.")

    with col_der:
        st.markdown("<h3 style='color:#F59E0B; font-size:1.2rem;'>🚥 Estado del Ciclo Semafórico</h3>", unsafe_allow_html=True)
        
        fase_id = decision.get("current_phase")
        fase_nombre = next((p["name"] for p in phases if p["id"] == fase_id), None) if phases else None
        if not fase_nombre:
            fase_nombre = f"Fase {fase_id}" if fase_id is not None else "Supervisión General"

        estado_texto = "VERDE 🟢"

        st.markdown(f"""
        <div class="card-status-green">
            <span style="color:#94A3B8; font-size:0.85rem; font-weight:600;">FASE ASIGNADA</span>
            <h2 style="color:#10B981; margin: 4px 0 15px 0; font-weight:800;">{fase_nombre}</h2>
            <hr style="border:none; border-top:1px solid rgba(16, 185, 129, 0.2); margin: 15px 0;">
            <span style="color:#94A3B8; font-size:0.85rem; font-weight:600;">ESTADO DE SALIDA</span>
            <h3 style="color:#10B981; margin:4px 0 0 0;">{estado_texto}</h3>
        </div>
        """, unsafe_allow_html=True)

        # ESQUEMA REALISTA DE CALLES CON SEÑALES Y ASFALTO
        st.markdown("<h4 style='color:#94A3B8; font-size:0.95rem; margin-top:10px;'>🗺️ Esquema Urbano de la Intersección</h4>", unsafe_allow_html=True)
        st.markdown("""
        <div class="intersection-real">
            <div class="asphalt-h"><div class="line-yellow-h" style="top:34px;"></div></div>
            <div class="asphalt-v"><div class="line-yellow-v" style="left:34px;"></div></div>
            <!-- Pasos Peatonales Cebra -->
            <div class="zebra-h" style="top: 50px; left: 115px;"></div>
            <div class="zebra-h" style="bottom: 50px; left: 115px;"></div>
            <!-- Señal de STOP realista -->
            <div class="stop-sign">STOP</div>
            <!-- Semáforo con luz activa -->
            <div class="traffic-light-mini">
                <div class="light-dot red"></div>
                <div class="light-dot yellow"></div>
                <div class="light-dot green"></div>
            </div>
            <span style="position: absolute; bottom: 6px; right: 10px; font-size: 0.7rem; color: #94A3B8; font-weight: 600;">Topología 4 Vías</span>
        </div>
        """, unsafe_allow_html=True)

else:
    col_izq, col_der = st.columns([2.2, 1])

    with col_izq:
        st.markdown("<h3 style='color:#10B981; font-size:1.2rem;'>📹 Monitor de Inferencia</h3>", unsafe_allow_html=True)
        st.markdown("""
        <div class="card-box" style="text-align:center; padding: 70px 20px;">
            <h3 style="color:#10B981; margin-bottom:10px; font-weight:700;">Sistema listo para procesamiento</h3>
            <p style="color:#94A3B8; font-size:0.95rem; max-width:500px; margin:0 auto;">
                Seleccione la secuencia de video y la matriz de configuración en el panel lateral, posteriormente presione <b>▶️ EJECUTAR INFERENCIA VIAL</b>.
            </p>
        </div>
        """, unsafe_allow_html=True)

    with col_der:
        st.markdown("<h3 style='color:#F59E0B; font-size:1.2rem;'>🚥 Estado de Telemetría</h3>", unsafe_allow_html=True)
        st.markdown("""
        <div class="card-box">
            <span style="color:#94A3B8; font-size:0.85rem; font-weight:600;">FASE ASIGNADA</span>
            <h2 style="color:#64748B; margin: 4px 0 15px 0; font-weight:800;">En Espera...</h2>
            <hr style="border:none; border-top:1px solid #1E293B; margin: 15px 0;">
            <span style="color:#94A3B8; font-size:0.85rem; font-weight:600;">ESTADO DE SALIDA</span>
            <h3 style="color:#64748B; margin:4px 0 0 0;">Sin Telemetría</h3>
        </div>
        """, unsafe_allow_html=True)

    # ESQUEMA EN ESPERA
    st.markdown("<h4 style='color:#94A3B8; font-size:0.95rem; margin-top:10px;'>🗺️ Esquema Urbano de la Intersección</h4>", unsafe_allow_html=True)
    st.markdown("""
    <div class="intersection-real">
        <div class="asphalt-h"><div class="line-yellow-h" style="top:34px;"></div></div>
        <div class="asphalt-v"><div class="line-yellow-v" style="left:34px;"></div></div>
        <div class="stop-sign">STOP</div>
        <div class="traffic-light-mini">
            <div class="light-dot red"></div>
            <div class="light-dot yellow"></div>
            <div class="light-dot green"></div>
        </div>
        <span style="position: absolute; font-size: 0.8rem; color: #94A3B8;">Esperando datos de secuencia...</span>
    </div>
    """, unsafe_allow_html=True)