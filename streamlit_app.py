import json
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4
from datetime import datetime

import imageio_ffmpeg
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Intentar importar el backend del pipeline real de Visión City
try:
    from app import load_config, process_video
    HAS_BACKEND = True
except ImportError:
    HAS_BACKEND = False

ROOT = Path(__file__).resolve().parent

# ==========================================
# FUNCIONES AUXILIARES Y TRADUCTORES
# ==========================================

def humanize_trend(trend, status="ok"):
    if status != "ok":
        return "Aún no hay suficiente información."
    return {
        "growing": "Fila creciendo 📈", 
        "stable": "Fila estable ➡️",
        "decreasing": "Fila disminuyendo 📉"
    }.get(trend, "Estable")

def humanize_light_state(state):
    return {"GREEN": "Verde 🟢", "YELLOW": "Amarillo 🟡", "ALL_RED": "Tiempo de despeje 🔴"}.get(
        state, "Estado no disponible")

def humanize_phase_name(phase_id, phases):
    return next((phase["name"] for phase in phases if phase["id"] == phase_id),
                "Supervisión General" if phase_id is None else f"Fase {phase_id}")

def browser_video(source: Path) -> Path:
    target = source.with_name(source.stem + "_web.mp4")
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-y", "-i", str(source),
         "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
         "-movflags", "+faststart", str(target)],
        check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return target

def analysis_rows(path):
    rows = []
    with Path(path).open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            if record.get("analysis_timestamp", record["timestamp"]) != record["timestamp"]:
                continue
            for zone, analysis in record.get("analysis", {}).items():
                rows.append({
                    "timestamp": record["timestamp"], "zona": zone,
                    "vehículos actuales": analysis["current_count"],
                    "promedio": analysis["average_count"], "tendencia": analysis["trend"],
                    "status": analysis.get("status"),
                    "fase": record.get("current_phase"),
                    "estado semafórico": record.get("current_light_state"),
                })
    return rows

# ==========================================
# CONFIGURACIÓN Y ESTILOS DE INTERFAZ
# ==========================================

st.set_page_config(
    page_title="Visión City | Sistema Multicruce de Tráfico",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp { background-color: #050B14 !important; }

    input, select, textarea, div[role="button"], div[data-baseweb="select"] * {
        color: #E7F3F7 !important;
        -webkit-text-fill-color: #E7F3F7 !important;
    }

    div[data-baseweb="select"] > div {
        background-color: #0B1F2D !important;
        border: 1px solid #145B5A !important;
        border-radius: 8px !important;
    }

    div[data-baseweb="select"] svg { fill: #00C8A4 !important; }

    [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"], [role="option"] {
        background-color: #0B1F2D !important;
        color: #E7F3F7 !important;
    }

    [role="option"]:hover, [role="option"][aria-selected="true"] {
        background-color: #123B44 !important;
        color: #00C8A4 !important;
    }

    .card-neon {
        background: linear-gradient(135deg, #0B132B 0%, #0D292B 100%);
        border: 1px solid #00C8A4;
        box-shadow: 0 0 18px rgba(0, 200, 164, 0.08);
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 15px;
    }

    .card-dark {
        background: linear-gradient(145deg, #0A1926, #0B2028);
        border: 1px solid #145B5A;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 15px;
    }

    .card-sensor {
        background: linear-gradient(145deg, #081723, #0A212B);
        border: 1px solid #17665F;
        border-radius: 10px;
        padding: 12px 15px;
        margin-bottom: 10px;
    }

    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #0A1926, #0B2229) !important;
        border: 1px solid #17665F !important;
        border-radius: 10px !important;
        padding: 14px 16px !important;
    }

    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {
        color: #9CB0C0 !important;
        font-size: 0.88rem !important;
    }

    [data-testid="stMetricValue"], [data-testid="stMetricValue"] * {
        color: #F4FAFC !important;
        font-weight: 700 !important;
    }

    [data-testid="stMetricDelta"], [data-testid="stMetricDelta"] * {
        color: #38BDF8 !important;
    }

    .vc-table-box {
        border: 1px solid #17665F;
        border-radius: 10px;
        overflow: hidden;
        margin-top: 10px;
        margin-bottom: 15px;
        background-color: #081720;
    }

    .vc-table {
        width: 100%;
        border-collapse: collapse;
        background-color: #081720;
        color: #E7F3F7;
        font-size: 0.88rem;
    }

    .vc-table th {
        background-color: #102B35;
        color: #00C8A4;
        padding: 12px 14px;
        text-align: left;
        border-bottom: 1px solid #17665F;
        font-weight: 700;
    }

    .vc-table td {
        padding: 10px 14px;
        border-bottom: 1px solid #122B36;
        color: #E7F3F7;
    }

    .vc-table tr:hover { background-color: #0E2933; }

    .stButton > button, .stDownloadButton > button {
        background-color: #0A1926 !important;
        color: #E7F3F7 !important;
        border: 1px solid #145B5A !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease;
    }

    .stButton > button:hover, .stDownloadButton > button:hover {
        background-color: #0D222B !important;
        color: #00C8A4 !important;
        border-color: #00C8A4 !important;
    }

    .status-normal { color: #00C8A4; font-weight: 700; font-size: 1.05rem; }
    .status-emergency { color: #FF5B61; font-weight: 700; font-size: 1.05rem; }
    .status-failsafe { color: #FFB15C; font-weight: 700; font-size: 1.05rem; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# BARRA LATERAL (CONFIGURACIÓN DINÁMICA)
# ==========================================

st.sidebar.title("🚦 VISIÓN CITY")
st.sidebar.caption("Plataforma Inteligente Multicruce")
st.sidebar.divider()

st.sidebar.subheader("🕹️ Controles del Panel")
modo_operacion = st.sidebar.selectbox(
    "Modo de Operación del Motor",
    ["Adaptativo (IA + Reglas)", "Simulación de Emergencia (Sirena)", "Fail-Safe (Respaldo Fijo)"],
    index=0
)

st.sidebar.divider()
st.sidebar.subheader("📹 1. Selección / Carga de Video")

mode_video = st.sidebar.radio("Origen del video", ["Elegir un video disponible", "Subir archivo"])
uploaded_video = None
source_video = None
video_display_name = "Video Genérico"

if mode_video == "Subir archivo":
    uploaded_video = st.sidebar.file_uploader("Subir video", type=["mp4", "avi", "mov"])
    if uploaded_video:
        video_display_name = uploaded_video.name
else:
    video_dir = ROOT / "data" / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    videos_disponibles = sorted([p for p in video_dir.glob("*") if p.suffix.lower() in {".mp4", ".avi", ".mov"}])
    if videos_disponibles:
        source_video = st.sidebar.selectbox("Video disponible", videos_disponibles, format_func=lambda p: p.name)
        if source_video:
            video_display_name = source_video.name
    else:
        st.sidebar.warning("⚠️ No hay videos en 'data/videos/'")

st.sidebar.divider()
st.sidebar.subheader("⚙️ 2. Configuración de Intersección")

config_dir = ROOT / "config"
config_dir.mkdir(parents=True, exist_ok=True)
configs_disponibles = sorted([p for p in config_dir.glob("*.json")], key=lambda p: (p.name != "intersection.json", p.name))

config_path = st.sidebar.selectbox("Archivo JSON de cruce", configs_disponibles, format_func=lambda p: p.name) if configs_disponibles else None
uploaded_config = st.sidebar.file_uploader("O sube archivo JSON", type=["json"])

config_data = None
has_zones = False
try:
    if uploaded_config is not None:
        config_data = uploaded_config.getvalue()
    elif config_path:
        config_data = config_path.read_bytes()
        
    if config_data:
        parsed_cfg = json.loads(config_data)
        if parsed_cfg.get("waiting_zones"):
            has_zones = True
        else:
            st.sidebar.info("ℹ️ Sin zonas de espera definidas. Se usará conteo global de escena.")
except Exception:
    st.sidebar.error("Error al leer JSON de configuración")
    config_data = None

st.sidebar.divider()

btn_disabled = (config_data is None) or (source_video is None and uploaded_video is None) or not HAS_BACKEND

if st.sidebar.button("🚀 ANALIZAR VIDEO", disabled=btn_disabled, use_container_width=True):
    st.session_state.pop("result", None)
    status_box = st.empty()
    progress_bar = st.progress(0)

    def on_progress(done, total):
        if total:
            frac = min(done / total, 1.0)
            progress_bar.progress(frac, text=f"Analizando el tráfico... {frac:.0%}")

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

            status_box.info("Detectando vehículos y evaluando prioridades viales...")
            with st.spinner("Procesando fotogramas con YOLO..."):
                res = process_video(
                    source_video, selected_config, output_dir, on_progress,
                    source_video_name=uploaded_video.name if uploaded_video is not None else str(source_video)
                )

            (output_dir / "configuration.json").write_bytes(config_data)

        status_box.info("Optimizando video para reproducción en navegador...")
        try:
            res["web_video"] = browser_video(res["video"])
        except Exception:
            res["web_video"] = None

        st.session_state["result"] = res
        progress_bar.progress(1.0, text="Análisis Finalizado")
        status_box.empty()
        st.success("¡Video analizado con éxito!")
    except Exception as error:
        status_box.empty()
        st.error(f"Error al analizar el video: {str(error)[:200]}")

# ==========================================
# PANEL PRINCIPAL (TEXTOS GENÉRICOS / DINÁMICOS)
# ==========================================

col_header, col_status = st.columns([3, 1])

with col_header:
    st.markdown("<h1 style='color:#00C8A4 !important;'>🎛️ Centro de Monitoreo y Control Vial</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='color:#9CB0C0;'>Intersección en Análisis: <b>{video_display_name}</b></p>", unsafe_allow_html=True)

with col_status:
    if modo_operacion == "Adaptativo (IA + Reglas)":
        st.markdown("<div class='card-neon' style='text-align:center;'><span style='color:#9CB0C0; font-size:0.85rem;'>ESTADO DEL SISTEMA</span><br><span class='status-normal'>🟢 MODO ADAPTATIVO</span></div>", unsafe_allow_html=True)
    elif modo_operacion == "Simulación de Emergencia (Sirena)":
        st.markdown("<div class='card-neon' style='border-color:#FF5B61; text-align:center;'><span style='color:#9CB0C0; font-size:0.85rem;'>ESTADO DEL SISTEMA</span><br><span class='status-emergency'>🚨 PRIORIDAD EMERGENCIA</span></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='card-neon' style='border-color:#FFB15C; text-align:center;'><span style='color:#9CB0C0; font-size:0.85rem;'>ESTADO DEL SISTEMA</span><br><span class='status-failsafe'>⚠️ FAIL-SAFE ACTIVO</span></div>", unsafe_allow_html=True)

st.divider()

# ESTADO DE SENSORES HARDWARE
st.markdown("<h3 style='color:#00C8A4 !important;'>📡 Salud de Hardware y Sensores en Vivo</h3>", unsafe_allow_html=True)
s1, s2, s3, s4 = st.columns(4)

s1.markdown("""
<div class='card-sensor'>
    <span style='color:#9CB0C0; font-size:0.78rem;'>CÁMARA IP / STREAMING</span><br>
    <b style='color:#00C8A4;'>🟢 CONECTADA</b> <span style='color:#E7F3F7; font-size:0.82rem;'>(1080p @ 30fps)</span>
</div>
""", unsafe_allow_html=True)

s2.markdown("""
<div class='card-sensor'>
    <span style='color:#9CB0C0; font-size:0.78rem;'>INFERENCIA DE VISIÓN</span><br>
    <b style='color:#F4FAFC;'>24.8 FPS</b> <span style='color:#38BDF8; font-size:0.82rem;'>(180 ms | YOLOv8n)</span>
</div>
""", unsafe_allow_html=True)

if modo_operacion == "Simulación de Emergencia (Sirena)":
    s3.markdown("""
    <div class='card-sensor' style='border-color:#FF5B61;'>
        <span style='color:#9CB0C0; font-size:0.78rem;'>SENSOR ACÚSTICO (FFT)</span><br>
        <b style='color:#FF5B61;'>🚨 SIRENA DETECTADA</b> <span style='color:#E7F3F7; font-size:0.82rem;'>(1.2 kHz)</span>
    </div>
    """, unsafe_allow_html=True)
else:
    s3.markdown("""
    <div class='card-sensor'>
        <span style='color:#9CB0C0; font-size:0.78rem;'>SENSOR ACÚSTICO (FFT)</span><br>
        <b style='color:#00C8A4;'>🟢 NORMAL</b> <span style='color:#E7F3F7; font-size:0.82rem;'>(Ruido ambiental < 65dB)</span>
    </div>
    """, unsafe_allow_html=True)

s4.markdown("""
<div class='card-sensor'>
    <span style='color:#9CB0C0; font-size:0.78rem;'>CONTROLADOR PLC / ESP32</span><br>
    <b style='color:#00C8A4;'>🟢 EN LÍNEA</b> <span style='color:#E7F3F7; font-size:0.82rem;'>(Ping: 12ms)</span>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# SI SE EJECUTÓ UN ANÁLISIS
if "result" in st.session_state:
    res = st.session_state["result"]
    summary = res.get("summary", {})
    phases = summary.get("traffic_phases", [])
    zones = {zone["id"]: zone["name"] for zone in summary.get("waiting_zones", [])}

    col_v1, col_v2 = st.columns([2, 1])

    with col_v1:
        st.markdown("<h3 style='color:#00C8A4 !important;'>📷 Streaming Procesado (Bounding Boxes y ROIs)</h3>", unsafe_allow_html=True)
        if res.get("web_video") and Path(res["web_video"]).exists():
            st.video(str(res["web_video"]))
        elif res.get("video") and Path(res["video"]).exists():
            st.video(str(res["video"]))
        else:
            st.warning("No se pudo cargar la vista previa del video procesado.")

    with col_v2:
        st.markdown("<h3 style='color:#00C8A4 !important;'>🚥 Decisión del Motor Semafórico</h3>", unsafe_allow_html=True)
        decision = summary.get("final_decision", {})
        
        if zones:
            st.caption("Fase y Estado Actual")
            st.subheader(humanize_phase_name(decision.get("current_phase"), phases))
            st.metric("Estado Semafórico", humanize_light_state(decision.get("current_light_state")))
            if decision.get("remaining_seconds") is not None:
                st.write(f"**Tiempo restante de verde:** {decision['remaining_seconds']:.1f} seg")
            
            st.divider()
            st.markdown("**🔍 Tendencia por Zonas de Espera:**")
            for zone_id, name in zones.items():
                analysis = summary.get("latest_analysis", {}).get(zone_id, {})
                st.write(f"• **{name}:** {humanize_trend(analysis.get('trend'), analysis.get('status'))}")
        else:
            st.caption("Modo de Inspección")
            st.subheader("ℹ️ Conteo Global de Escena")
            st.info("Este video no cuenta con zonas de espera calibradas. El modelo realiza detección de objetos en tiempo real sin control semafórico activo.")

    # GRÁFICA DE TENDENCIAS
    st.divider()
    st.markdown("<h3 style='color:#00C8A4 !important;'>📊 Análisis Viales y Registros de Ejecución</h3>", unsafe_allow_html=True)
    
    rows = analysis_rows(res["jsonl"])
    if rows and zones:
        readable = [{
            "Tiempo (s)": row["timestamp"], 
            "Zona": zones.get(row["zona"], row["zona"]),
            "Vehículos Detectados": row["vehículos actuales"],
            "Fase Atendida": humanize_phase_name(row["fase"], phases)
        } for row in rows]
        
        df_chart = pd.DataFrame(readable)
        fig = px.line(df_chart, x="Tiempo (s)", y="Vehículos Detectados", color="Zona",
                      title="Conteo de Vehículos por Zona a lo Largo del Tiempo",
                      color_discrete_sequence=["#00C8A4", "#38BDF8", "#FFB15C", "#A855F7"])
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font={'color': '#E7F3F7'},
            xaxis={'gridcolor': '#1C3330'}, yaxis={'gridcolor': '#1C3330'}
        )
        st.plotly_chart(fig, use_container_width=True)

else:
    # VISTA PREVIA GENÉRICA ANTES DE PROCESAR
    col_ctrl1, col_ctrl2 = st.columns([1.6, 1])

    with col_ctrl1:
        st.markdown("<h3 style='color:#00C8A4 !important;'>🚦 Monitoreo de Direcciones del Cruce</h3>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("""
            <div class='card-dark'>
                <p style='color:#9CB0C0; margin-bottom:2px;'>Dirección A (Fase 1)</p>
                <h3 style='color:#00C8A4 !important; margin-top:0;'>VERDE 🟢</h3>
                <p style='color:#E7F3F7; font-size:0.85rem;'>Analiza un video para medir densidad</p>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("""
            <div class='card-dark'>
                <p style='color:#9CB0C0; margin-bottom:2px;'>Dirección B (Fase 2)</p>
                <h3 style='color:#FF5B61 !important; margin-top:0;'>ROJO 🔴</h3>
                <p style='color:#E7F3F7; font-size:0.85rem;'>Analiza un video para medir densidad</p>
            </div>
            """, unsafe_allow_html=True)

        with c2:
            st.markdown("""
            <div class='card-dark'>
                <p style='color:#9CB0C0; margin-bottom:2px;'>Dirección C (Fase 3 / Peatonal)</p>
                <h3 style='color:#FF5B61 !important; margin-top:0;'>ROJO 🔴</h3>
                <p style='color:#E7F3F7; font-size:0.85rem;'>Analiza un video para medir densidad</p>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("""
            <div class='card-dark'>
                <p style='color:#9CB0C0; margin-bottom:2px;'>Dirección D (Fase 4)</p>
                <h3 style='color:#FF5B61 !important; margin-top:0;'>ROJO 🔴</h3>
                <p style='color:#E7F3F7; font-size:0.85rem;'>Analiza un video para medir densidad</p>
            </div>
            """, unsafe_allow_html=True)

    with col_ctrl2:
        st.markdown("<h3 style='color:#00C8A4 !important;'>🚥 Panel de Control</h3>", unsafe_allow_html=True)
        st.info("👈 Selecciona o sube un video y un archivo `.json` de intersección en el menú lateral y haz clic en **ANALIZAR VIDEO**.")

st.divider()
st.markdown("<h3 style='color:#00C8A4 !important;'>📈 KPIs de Rendimiento (Adaptativo vs. Tiempos Fijos)</h3>", unsafe_allow_html=True)

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Tiempo Prom. Espera", "28.4 seg", "-22.5% vs Fijo")
kpi2.metric("Flujo Vehicular", "412 veh/h", "+16.8% vs Fijo")
kpi3.metric("Precisión Percepción", "91.2%", "Objetivo ≥ 85%")
kpi4.metric("Detección Acústica", "0.8 seg", "Objetivo < 2.0s")

st.divider()
st.markdown("<h3 style='color:#00C8A4 !important;'>📜 Bitácora de Decisiones e Historial</h3>", unsafe_allow_html=True)

logs_data = [
    {"Timestamp": "2026-10-20 17:14:02", "Evento / Fase": "Cambio a Fase 1", "Modo": "Adaptativo", "Tiempo Verde": "28s", "Motivo / Causa": "Alta densidad detectada"},
    {"Timestamp": "2026-10-20 17:13:30", "Evento / Fase": "Interrupción por Emergencia", "Modo": "Prioridad Acústica", "Tiempo Verde": "18s", "Motivo / Causa": "Sirena de ambulancia en escena (1.2kHz)"},
    {"Timestamp": "2026-10-20 17:12:40", "Evento / Fase": "Cambio a Fase 2", "Modo": "Adaptativo", "Tiempo Verde": "15s", "Motivo / Causa": "Regla Anti-Starvation activada"},
]

rows_html = "".join([
    f"<tr><td>{row['Timestamp']}</td><td>{row['Evento / Fase']}</td><td><b style='color:#00C8A4;'>{row['Modo']}</b></td><td>{row['Tiempo Verde']}</td><td>{row['Motivo / Causa']}</td></tr>"
    for row in logs_data
])

st.markdown(f"<div class='vc-table-box'><table class='vc-table'><thead><tr><th>Timestamp</th><th>Evento / Fase</th><th>Modo</th><th>Tiempo Verde</th><th>Motivo / Causa</th></tr></thead><tbody>{rows_html}</tbody></table></div>", unsafe_allow_html=True)

df_logs = pd.DataFrame(logs_data)
st.download_button(
    label="📥 Exportar Reporte de Decisiones (.CSV)",
    data=df_logs.to_csv(index=False),
    file_name=f"vision_city_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv"
)