"""Interfaz local mínima sobre el mismo pipeline que usa el CLI."""

import json
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

import imageio_ffmpeg
import streamlit as st

from app import load_config, process_video

ROOT = Path(__file__).resolve().parent


def browser_video(source: Path) -> Path:
    """Solo convierte el resultado MP4V; conserva la salida original de OpenCV."""
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
            # Las transiciones entre muestras llevan análisis anterior: no duplicarlo en la gráfica.
            if record.get("analysis_timestamp", record["timestamp"]) != record["timestamp"]:
                continue
            for zone, analysis in record.get("analysis", {}).items():
                rows.append({
                    "timestamp": record["timestamp"], "zona": zone,
                    "vehículos actuales": analysis["current_count"],
                    "promedio": analysis["average_count"], "tendencia": analysis["trend"],
                    "prioridad": record.get("priority", {}).get("scores", {}).get(zone, {}).get("score"),
                    "fase": record.get("current_phase"),
                    "estado semafórico": record.get("current_light_state"),
                })
    return rows


def show_results(result):
    summary = result["summary"]
    st.subheader("Resumen")
    st.success("Video procesado correctamente")
    st.write(f"Frames procesados: {summary['frames_processed']} · "
             f"Duración: {summary['video']['duration_seconds']} s · Dispositivo: {summary['device']}")
    experience = summary.get("experience", {})
    if experience:
        st.write(f"Experiencias generadas: {experience['generated']} · "
                 f"Reward promedio: {experience['average_reward']} · "
                 f"Dataset acumulado: {experience['dataset_count']} experiencias")
        st.caption(f"Dataset: {experience['dataset_path']}")
        if experience["incomplete"]:
            st.caption("El último verde quedó incompleto y no se agregó al dataset.")
        if experience["rows"]:
            st.dataframe(experience["rows"], hide_index=True)
    st.info("Las experiencias se registran para entrenamiento futuro. Actualmente NO modifican "
            "automáticamente las decisiones del controlador.")
    decision = summary.get("final_decision", {})
    if decision:
        st.subheader("Estado final del cerebro")
        st.write({"Fase actual": decision["current_phase"],
                  "Estado": decision["current_light_state"],
                  "Verde planificado (s)": decision["planned_green"],
                  "Zona con mayor score": summary.get("final_zone_priority", {}).get("winner"),
                  "Siguiente fase provisional": decision["next_phase"],
                  "Modo": decision["mode"]})
        st.write("Motivos: " + "; ".join(decision["reasons"]))
    if result.get("web_video"):
        st.video(str(result["web_video"]))
    else:
        st.warning("No se pudo preparar la reproducción web. El video anotado está guardado en la ruta indicada.")
    st.subheader("Archivos generados")
    for key, label in (("video", "Video anotado"), ("csv", "CSV"), ("json", "Resumen JSON"), ("jsonl", "JSONL")):
        path = result[key]
        st.text(f"{label}: {path}")
        if key != "video" and path.stat().st_size <= 20 * 1024 * 1024:
            st.download_button(f"Descargar {label}", path.read_bytes(), file_name=path.name, key=f"download_{key}")
    rows = analysis_rows(result["jsonl"])
    if rows:
        st.subheader("Análisis por zona")
        st.dataframe(rows, hide_index=True)
        st.line_chart(rows, x="timestamp", y="vehículos actuales", color="zona")
    else:
        st.info("No hay análisis por zona; revisa waiting_zones en la configuración.")


def main():
    st.set_page_config(page_title="Visión City")
    st.title("Visión City")
    mode = st.radio("Video", ["Seleccionar de data/videos", "Subir archivo"])
    uploaded_video = None
    source = None
    if mode == "Subir archivo":
        uploaded_video = st.file_uploader("Subir video", type=["mp4", "avi", "mov"])
    else:
        videos = sorted(path for path in (ROOT / "data/videos").glob("*")
                        if path.suffix.lower() in {".mp4", ".avi", ".mov"})
        source = st.selectbox("Video disponible", videos, format_func=lambda path: path.name)

    configs = sorted((ROOT / "config").glob("*.json"), key=lambda path: (path.name != "intersection.json", path.name))
    config_path = st.selectbox("Configuración JSON", configs, format_func=lambda path: path.name)
    uploaded_config = st.file_uploader("O subir otra configuración JSON", type=["json"])
    config_data = None
    try:
        config_data = uploaded_config.getvalue() if uploaded_config is not None else config_path.read_bytes() if config_path else None
        config = json.loads(config_data) if config_data is not None else {}
        if not isinstance(config, dict):
            raise ValueError("La configuración debe ser un objeto JSON.")
        if not config.get("waiting_zones"):
            st.warning("Esta configuración no tiene zonas de espera calibradas. "
                       "El análisis puede ejecutarse, pero los resultados de tráfico no serán representativos.")
    except (ValueError, OSError) as error:
        st.error(f"Configuración inválida. Detalle: {error}")
        config_data = None

    if st.button("Analizar", disabled=config_data is None or (source is None and uploaded_video is None)):
        st.session_state.pop("result", None)
        status = st.empty()
        progress = st.progress(0)

        def on_progress(done, total):
            if total:
                progress.progress(min(done / total, 1.0), text=f"Analizando video... {done}/{total} frames")
            else:
                status.info(f"Preparando modelo y video..." if done == 0 else f"Procesando frame {done}...")

        try:
            work = ROOT / "output" / "ui"
            work.mkdir(parents=True, exist_ok=True)
            output = work / uuid4().hex
            # Solo las entradas copiadas son temporales; los resultados sobreviven a los reruns.
            with tempfile.TemporaryDirectory(prefix="upload_", dir=work) as temp:
                temporary = Path(temp)
                selected_config = temporary / "intersection.json"
                selected_config.write_bytes(config_data)
                load_config(selected_config)
                if uploaded_video is not None:
                    source = temporary / ("video" + Path(uploaded_video.name).suffix.lower())
                    source.write_bytes(uploaded_video.getbuffer())
                status.info("Analizando video...")
                with st.spinner("Procesando video..."):
                    result = process_video(source, selected_config, output, on_progress,
                                           source_video_name=uploaded_video.name if uploaded_video is not None else str(source))
                # Conservar la configuración efectiva para poder interpretar el resultado.
                (output / "configuration.json").write_bytes(config_data)
            status.info("Preparando video para el navegador...")
            try:
                result["web_video"] = browser_video(result["video"])
            except (OSError, RuntimeError, subprocess.CalledProcessError):
                result["web_video"] = None
            st.session_state["result"] = result
            progress.progress(1.0, text="Finalizado")
            status.empty()
        except Exception as error:
            status.empty()
            st.error(f"No se pudo procesar el video. Detalle: {str(error)[:500]}")

    if "result" in st.session_state:
        try:
            show_results(st.session_state["result"])
        except (OSError, ValueError, KeyError) as error:
            st.error(f"No se pudieron mostrar los resultados. Detalle: {str(error)[:500]}")


if __name__ == "__main__":
    main()
