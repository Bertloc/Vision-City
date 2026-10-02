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


def humanize_trend(trend, status="ok"):
    if status != "ok":
        return "Aún no hay suficiente información para conocer la tendencia."
    return {"growing": "La fila está creciendo", "stable": "La fila se mantiene estable",
            "decreasing": "La fila está disminuyendo"}.get(
                trend, "Aún no hay suficiente información para conocer la tendencia.")


def humanize_light_state(state):
    return {"GREEN": "Verde", "YELLOW": "Amarillo", "ALL_RED": "Tiempo de despeje"}.get(
        state, "Estado no disponible")


def humanize_reward(reward):
    # Solo presentación: esta banda no cambia el reward guardado ni su elegibilidad.
    if reward is None:
        return "No se pudo evaluar el resultado."
    if reward > 0.5:
        return "La decisión tuvo un resultado positivo."
    if reward < -0.5:
        return "La situación empeoró según las métricas actuales."
    return "La decisión no produjo un cambio claro."


def humanize_phase_name(phase_id, phases):
    return next((phase["name"] for phase in phases if phase["id"] == phase_id),
                "Sin dirección seleccionada" if phase_id is None else "Dirección sin nombre configurado")


def humanize_eligibility(evaluation):
    if evaluation.get("training_eligible") is True:
        return "Esta experiencia puede servir para entrenamiento futuro."
    causes = []
    for reason in evaluation.get("reasons", []):
        if "Confianza" in reason:
            causes.append("Los datos no fueron suficientemente confiables.")
        elif "SAFE_MODE" in reason:
            causes.append("El sistema usó el modo seguro.")
        elif "Modo FIXED_LOW" in reason or "no adaptativa" in reason:
            causes.append("La decisión siguió una secuencia fija de semáforos.")
        elif "Conteos" in reason:
            causes.append("Faltaron conteos válidos de vehículos.")
    return "Esta experiencia no se usará para entrenamiento. " + " ".join(dict.fromkeys(causes))


def session_experiences(experience):
    path = Path(experience.get("dataset_path", ""))
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as source:
        return [record for line in source if (record := json.loads(line)).get("session_id") == experience.get("session_id")]


def decision_explanation(record):
    """Traduce motivos existentes; no decide ni recalcula prioridades."""
    reasons = record.get("reasons", [])
    if record.get("mode") != "ADAPTIVE":
        return ["Se eligió la siguiente dirección de una secuencia fija de semáforos."]
    if any(reason.startswith("Anti-starvation:") for reason in reasons):
        return ["Era la dirección con más tiempo de espera entre las que ya necesitaban atención."]
    if any(reason.startswith("Sin demanda:") for reason in reasons):
        return ["No había vehículos registrados en el análisis usado para decidir; se siguió una secuencia fija con un verde corto."]
    if any(reason.startswith("Margen de histéresis:") for reason in reasons):
        return ["Las prioridades eran parecidas; se eligió volver a atender la misma dirección después del despeje."]
    return ["Se compararon los vehículos presentes, el promedio reciente y el crecimiento de las filas.",
            "Si las prioridades eran parecidas, se consideró cuánto llevaba esperando cada dirección."]


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
                    "status": analysis.get("status"), "growth_rate": analysis.get("growth_rate"),
                    "prioridad": record.get("priority", {}).get("scores", {}).get(zone, {}).get("score"),
                    "fase": record.get("current_phase"),
                    "estado semafórico": record.get("current_light_state"),
                })
    return rows


def show_results(result):
    summary = result["summary"]
    st.success("Video procesado correctamente")
    phases = summary.get("traffic_phases", [])
    zones = {zone["id"]: zone["name"] for zone in summary.get("waiting_zones", [])}
    with Path(result["jsonl"]).open(encoding="utf-8") as source:
        records = [json.loads(line) for line in source]
    latest = records[-1] if records else {}
    starts = [record for record in records if record.get("decision") == "INICIAR"]
    chosen = starts[-1] if starts else None
    experience = summary.get("experience", {})
    saved = session_experiences(experience) if experience else []
    st.subheader("¿Qué está viendo el sistema?")
    st.caption("Última observación disponible del video. Los conteos son vehículos detectados dentro de cada zona.")
    if zones:
        for zone, name in zones.items():
            count = latest.get("vehicles_by_zone", {}).get(zone)
            st.write(f"**{name}**")
            st.write(f"{count} vehículos esperando" if count is not None else "No hay un conteo disponible.")
    else:
        st.info("No hay zonas de espera configuradas para observar las filas.")

    st.subheader("¿Qué está pasando con el tráfico?")
    for zone, name in zones.items():
        analysis = latest.get("analysis", {}).get(zone, {})
        st.write(f"**{name}:** {humanize_trend(analysis.get('trend'), analysis.get('status'))}")
    decision = summary.get("final_decision", {})
    ranked = decision.get("phase_priorities", {})
    candidates = {key: value for key, value in ranked.items()
                  if value.get("effective_score") is not None and (value.get("demand") or 0) > 0}
    if decision.get("mode") == "ADAPTIVE" and candidates:
        best = max(value["effective_score"] for value in candidates.values())
        leaders = [key for key, value in candidates.items() if value["effective_score"] == best]
        st.write("**Dirección que necesita más atención según el último análisis:** "
                 + ", ".join(humanize_phase_name(key, phases) for key in leaders))
        st.write("¿Por qué?")
        for key in leaders:
            phase = candidates[key]
            st.write(f"- {humanize_phase_name(key, phases)}: {phase['demand']} vehículos registrados en sus zonas.")
            phase_zones = next((item["zones"] for item in phases if item["id"] == key), [])
            growing = [zones.get(zone, "Zona sin nombre configurado") for zone in phase_zones
                       if latest.get("priority", {}).get("scores", {}).get(zone, {}).get("components", {}).get("growth", 0) > 0]
            if growing:
                st.write("- El crecimiento de la fila aumentó su prioridad en: " + ", ".join(growing) + ".")
            if phase.get("starvation_bonus", 0) > 0:
                st.write("- El tiempo que lleva esperando también aumentó su prioridad.")
        st.caption("Se comparan los vehículos presentes, el promedio reciente, el crecimiento y la espera por dirección.")
    else:
        st.write("No hay una prioridad adaptativa disponible con demanda registrada.")

    st.subheader("¿Qué decidió?")
    if chosen:
        st.write("**Última dirección elegida:** " + humanize_phase_name(chosen["current_phase"], phases))
        st.write(f"Tiempo verde planeado: {chosen['planned_green']:.1f} segundos.")
        st.write("¿Por qué?")
        for explanation in decision_explanation(chosen):
            st.write("- " + explanation)
    else:
        st.write("Durante este video no se inició un nuevo período de verde.")

    st.subheader("¿Qué está haciendo el semáforo?")
    if decision:
        st.write("**Semáforo al terminar el video:** " + humanize_light_state(decision["current_light_state"]))
        st.write(humanize_phase_name(decision["current_phase"], phases))
        if decision["current_light_state"] == "ALL_RED":
            st.caption("Todas las direcciones están en rojo para dejar libre el cruce antes del siguiente verde.")
        if decision.get("remaining_seconds") is not None:
            st.write(f"Tiempo restante de este estado: {decision['remaining_seconds']:.1f} segundos.")
        if decision.get("mode") == "SAFE_MODE":
            st.warning("Modo seguro activado. El sistema no confía lo suficiente en los datos, "
                       "así que está usando una secuencia fija de semáforos. Este modo permanece activo hasta reiniciar.")
        elif decision.get("mode") == "FIXED_LOW":
            st.warning("Los datos actuales no son suficientemente confiables. Se conserva el verde vigente "
                       "y después se usa una secuencia fija de semáforos.")

    st.subheader("¿Qué pasó después?")
    if saved:
        table = []
        for record in saved:
            evaluation = record["evaluation"]
            selected = record["decision"]["selected_phase"]
            served_zones = next((item["zones"] for item in phases if item["id"] == selected), [])
            counts = [record[side]["traffic_state"]["vehicles_by_zone"] for side in ("before", "after")]
            demands = [sum(values[zone] for zone in served_zones)
                       if served_zones and all(type(values.get(zone)) is int for zone in served_zones) else None
                       for values in counts]
            table.append({"Tiempo": f"{record['timestamp_decision']:.1f} s",
                          "Fase atendida": humanize_phase_name(selected, phases),
                          "Duración del verde": f"{record['after']['elapsed_seconds']:.1f} s",
                          "Vehículos antes": demands[0], "Vehículos después": demands[1],
                          "Resultado": humanize_reward(evaluation.get("reward")),
                          "Uso futuro": humanize_eligibility(evaluation)})
        st.dataframe(table, hide_index=True)
        st.caption("Se compara la cantidad de vehículos en las zonas atendidas al empezar y terminar cada verde. "
                   "Una reducción no permite saber cuántos vehículos atravesaron el cruce.")
    else:
        st.write("No hay períodos de verde completos guardados para comparar en esta ejecución.")

    st.subheader("¿Qué quedó registrado de esta ejecución?")
    if experience:
        if not experience.get("enabled", True):
            st.info("El registro de experiencias está desactivado en esta configuración.")
        elif experience["generated"]:
            st.success("Experiencias guardadas")
            st.write("El sistema guardó:\n- qué tráfico había\n- qué decisión tomó\n- qué ocurrió después")
        else:
            st.write("Esta ejecución no generó experiencias completas.")
        st.write(f"Experiencias generadas en este video: {experience['generated']}")
        if experience.get("enabled", True):
            st.write(f"Experiencias acumuladas al terminar el video: {experience['dataset_count']}")
        if experience["incomplete"]:
            st.caption("El último verde no terminó antes de finalizar el video; no se guardó como experiencia completa.")
    st.warning("El sistema todavía no cambia sus decisiones usando estas experiencias. "
               "Se están recopilando para entrenamiento futuro.")

    rows = analysis_rows(result["jsonl"])
    if rows:
        with st.expander("Ver cómo cambiaron las filas"):
            readable = [{"Tiempo": row["timestamp"], "Zona": zones.get(row["zona"], "Zona sin nombre configurado"),
                         "Vehículos": row["vehículos actuales"],
                         "Tendencia": humanize_trend(row["tendencia"], row.get("status")),
                         "Fase atendida": humanize_phase_name(row["fase"], phases)} for row in rows]
            st.dataframe(readable, hide_index=True)
            st.line_chart(readable, x="Tiempo", y="Vehículos", color="Zona")

    with st.expander("Ver detalles técnicos"):
        st.caption("La banda de presentación del reward es de −0.5 a +0.5. No modifica el valor guardado ni su elegibilidad.")
        st.json(summary)
        if saved:
            st.dataframe(experience.get("rows", []), hide_index=True)
            st.json(saved)
        if rows:
            st.dataframe(rows, hide_index=True)
        st.json(latest)
        if result.get("web_video"):
            st.video(str(result["web_video"]))
        else:
            st.warning("No se pudo preparar la reproducción web. El video anotado está guardado en la ruta indicada.")
        for key, label in (("video", "Video anotado"), ("csv", "CSV"), ("json", "Resumen JSON"), ("jsonl", "JSONL")):
            path = result[key]
            st.text(f"{label}: {path}")
            if key != "video" and path.stat().st_size <= 20 * 1024 * 1024:
                st.download_button(f"Descargar {label}", path.read_bytes(), file_name=path.name, key=f"download_{key}")


def main():
    st.set_page_config(page_title="Visión City")
    st.title("VISIÓN CITY")
    st.write("Analiza un video de tráfico y observa qué decisión tomaría un semáforo inteligente.")
    st.subheader("1. Elige un video")
    mode = st.radio("Origen del video", ["Elegir un video disponible", "Subir archivo"])
    uploaded_video = None
    source = None
    if mode == "Subir archivo":
        uploaded_video = st.file_uploader("Subir video", type=["mp4", "avi", "mov"])
    else:
        videos = sorted(path for path in (ROOT / "data/videos").glob("*")
                        if path.suffix.lower() in {".mp4", ".avi", ".mov"})
        source = st.selectbox("Video disponible", videos, format_func=lambda path: path.name)

    configs = sorted((ROOT / "config").glob("*.json"), key=lambda path: (path.name != "intersection.json", path.name))
    st.subheader("2. Elige la configuración del cruce")
    st.caption("Define dónde están las zonas y cómo funciona el cruce.")
    config_path = st.selectbox("Configuración de intersección", configs, format_func=lambda path: path.name)
    uploaded_config = st.file_uploader("O sube otro archivo de configuración", type=["json"])
    config_data = None
    try:
        config_data = uploaded_config.getvalue() if uploaded_config is not None else config_path.read_bytes() if config_path else None
        config = json.loads(config_data) if config_data is not None else {}
        if not isinstance(config, dict):
            raise ValueError("La configuración debe ser un objeto JSON.")
        if not config.get("waiting_zones"):
            st.warning("Este archivo todavía no tiene zonas de espera configuradas. "
                       "Podemos analizar el video, pero las decisiones de tráfico no serán confiables.")
    except (ValueError, OSError) as error:
        st.error("No pudimos leer la configuración del cruce. Revisa el archivo elegido.")
        with st.expander("Ver detalles técnicos"):
            st.code(str(error))
        config_data = None

    if st.button("ANALIZAR VIDEO", disabled=config_data is None or (source is None and uploaded_video is None)):
        st.session_state.pop("result", None)
        status = st.empty()
        progress = st.progress(0)

        def on_progress(done, total):
            if total:
                fraction = min(done / total, 1.0)
                progress.progress(fraction, text=f"Analizando el tráfico... {fraction:.0%}")
            else:
                status.info("Analizando el tráfico... Estamos detectando vehículos y observando cómo cambia el tráfico.")

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
                status.info("Estamos detectando vehículos y observando cómo cambia el tráfico.")
                with st.spinner("Analizando el tráfico..."):
                    result = process_video(source, selected_config, output, on_progress,
                                           source_video_name=uploaded_video.name if uploaded_video is not None else str(source))
                # Conservar la configuración efectiva para poder interpretar el resultado.
                (output / "configuration.json").write_bytes(config_data)
            status.info("Preparando el video para que puedas verlo...")
            try:
                result["web_video"] = browser_video(result["video"])
            except (OSError, RuntimeError, subprocess.CalledProcessError):
                result["web_video"] = None
            st.session_state["result"] = result
            progress.progress(1.0, text="Finalizado")
            status.empty()
        except Exception as error:
            status.empty()
            st.error("No pudimos terminar el análisis. Revisa el video y la configuración del cruce.")
            with st.expander("Ver detalles técnicos"):
                st.code(str(error)[:500])

    if "result" in st.session_state:
        try:
            show_results(st.session_state["result"])
        except (OSError, ValueError, KeyError) as error:
            st.error("No pudimos mostrar los resultados guardados de este video.")
            with st.expander("Ver detalles técnicos"):
                st.code(str(error)[:500])


if __name__ == "__main__":
    main()
