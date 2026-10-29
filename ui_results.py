"""Presentación de resultados existentes; nunca procesa video ni escribe experiencias."""

from html import escape
import csv
import json
from pathlib import Path

import streamlit as st


def humanize_trend(trend, status="ok"):
    if status != "ok":
        return "Aún no hay suficiente información para conocer la tendencia."
    return {"growing": "La presencia de vehículos está creciendo", "stable": "La presencia de vehículos se mantiene estable",
            "decreasing": "La presencia de vehículos está disminuyendo"}.get(
                trend, "Aún no hay suficiente información para conocer la tendencia.")


def humanize_light_state(state):
    return {"GREEN": "Verde", "YELLOW": "Amarillo", "ALL_RED": "Todas las direcciones en rojo"}.get(
        state, "Estado no disponible")


def humanize_reward(reward):
    # Solo presentación: esta banda no cambia el reward guardado ni su elegibilidad.
    if reward is None:
        return "No se pudo evaluar el resultado."
    if reward > 0.5:
        return "Resultado positivo según la métrica de ocupación."
    if reward < -0.5:
        return "La situación empeoró según las métricas actuales."
    return "La métrica no produjo un cambio claro."


def humanize_phase_name(phase_id, phases):
    return next((phase["name"] for phase in phases if phase["id"] == phase_id),
                "Sin dirección seleccionada" if phase_id is None else "Dirección sin nombre configurado")


def humanize_eligibility(evaluation):
    if evaluation.get("training_eligible") is True:
        return "Esta experiencia puede servir para entrenamiento futuro."
    causes = []
    for reason in evaluation.get("reasons", []):
        if "Confianza" in reason:
            causes.append("La confianza simulada no permitió considerar los datos confiables para esta evaluación.")
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
        return ["Era la dirección con más tiempo de espera entre las que superaron el umbral, incluso si estaba vacía."]
    if any(reason.startswith("Sin demanda:") for reason in reasons):
        return ["No había vehículos registrados en el análisis usado para decidir; se siguió una secuencia fija con un verde corto."]
    if any(reason.startswith("Margen de histéresis:") for reason in reasons):
        return ["Las prioridades eran parecidas; se eligió volver a atender la misma dirección después del despeje."]
    return ["Se compararon los vehículos presentes, el promedio reciente y el crecimiento de la ocupación.",
            "Si las prioridades eran parecidas, se consideró cuánto llevaba esperando cada dirección."]


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


def apply_visual_style():
    # Clases propias y clave pública de st.container: sin selectores internos de Streamlit.
    st.html("""
    <style>
    .st-key-analyze_action button {color:#0F172A}
    .st-key-analyze_action button:focus-visible {outline:2px solid #F8FAFC;outline-offset:3px}
    .vc-brand {display:flex; align-items:center; gap:16px; margin:0 0 24px;
      font-family:'Fira Sans',system-ui,sans-serif; color:#F8FAFC}
    .vc-brand-mark {display:grid;place-items:center; width:48px;height:48px;
      border:1px solid #64748B;border-radius:12px;background:#1E293B;flex-shrink:0;
      font:700 18px 'Fira Code',ui-monospace,monospace;color:#38BDF8}
    .vc-eyebrow {color:#38BDF8;font-size:12px;letter-spacing:.14em;font-weight:700}
    .vc-subtitle {color:#CBD5E1;font-size:14px;margin-top:4px}
    .vc-signal {display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin:16px 0}
    .vc-lights {display:flex;gap:10px;background:#0F172A;border:1px solid #64748B;
      padding:12px;border-radius:32px}
    .vc-light {width:24px;height:24px;border-radius:50%;background:#334155;border:1px solid #64748B}
    .vc-signal-label {font:600 18px 'Fira Sans',system-ui,sans-serif;color:#F8FAFC}
    </style>
    """)
    st.html("""<div class="vc-brand">
      <div class="vc-brand-mark" aria-hidden="true">VC</div>
      <div><div class="vc-eyebrow">VISION CITY / ANÁLISIS DE INTERSECCIONES</div>
      <div class="vc-subtitle">Observa el tráfico. Comprende cada decisión virtual.</div></div></div>""")


def result_context(result):
    context = result.get("ui_context", {})
    summary = result["summary"]
    source = context.get("video_name") or summary.get("experience", {}).get("source_video") or summary.get("video", {}).get("source")
    st.text("Video: " + str(source or "Nombre no disponible"))
    st.caption("Configuración utilizada: " + str(context.get("config_name", "Nombre no disponible")))


def configuration_warnings(summary):
    messages = []
    if not summary.get("waiting_zones"):
        messages.append("Sin zonas configuradas: no hay medición de presencia por zona. Los ceros del archivo no significan que el cruce esté vacío.")
    if not summary.get("traffic_phases"):
        messages.append("Sin fases configuradas: todas las direcciones permanecen en rojo. No hay una fase activa ni experiencias de verdes completos.")
    if messages:
        st.warning("\n\n".join(messages))


def show_signal(decision, phases):
    state = decision.get("current_light_state")
    colors = {"ALL_RED": "#F87171", "YELLOW": "#FBBF24", "GREEN": "#4ADE80"}
    lamps = "".join(f'<span class="vc-light" style="background:{colors[key] if state == key else "#334155"}"></span>'
                    for key in ("ALL_RED", "YELLOW", "GREEN"))
    st.html(f'<div class="vc-signal"><div class="vc-lights" aria-hidden="true">{lamps}</div>'
            f'<div class="vc-signal-label">{escape(humanize_light_state(state))}</div></div>')
    if not phases:
        st.write("**Sin fases configuradas.** No hay una dirección favorecida.")
        return
    if state == "GREEN":
        st.write("**Fase con verde:** " + humanize_phase_name(decision.get("current_phase"), phases))
    elif state == "YELLOW":
        st.write("**Fase que termina:** " + humanize_phase_name(decision.get("current_phase"), phases))
    elif state == "ALL_RED":
        st.caption("Ninguna dirección tiene verde. Se respeta el despeje antes de elegir el siguiente verde.")
    mode = decision.get("mode")
    st.write("**Modo:** " + {"ADAPTIVE": "Adaptativo por reglas", "FIXED_LOW": "Secuencia fija",
                             "SAFE_MODE": "Modo seguro · Secuencia fija"}.get(mode, "No disponible"))
    if mode == "SAFE_MODE":
        st.warning("Modo seguro activado por la señal de simulación. Conserva el plan vigente y luego rota por orden; permanece activo hasta reiniciar el controlador.")
    elif mode == "FIXED_LOW":
        st.warning("Señal simulada baja o datos faltantes: conserva el verde vigente y después usa una secuencia fija.")
    if decision.get("remaining_seconds") is not None:
        st.write(f"**Tiempo restante registrado:** {decision['remaining_seconds']:.1f} s")
    st.caption("Estado al terminar el video. Este tiempo no es una cuenta regresiva en vivo.")


def show_downloads(result):
    st.subheader("Resultados y descargas")
    st.caption("Archivos de esta ejecución. Los cruces son eventos por línea; no equivalen a vehículos únicos reales.")
    files = [("video", "Video anotado", "video/mp4"), ("csv", "CSV por fotograma", "text/csv"),
             ("json", "Resumen JSON", "application/json"), ("jsonl", "Tráfico JSONL", "application/x-ndjson")]
    if result.get("web_video"):
        files.insert(1, ("web_video", "Video para navegador", "video/mp4"))
    configuration = result.get("ui_context", {}).get("configuration")
    if configuration:
        files.append(("configuration", "Configuración utilizada", "application/json"))
    columns = st.columns(2)
    for index, (key, label, mime) in enumerate(files):
        path = Path(configuration if key == "configuration" else result[key])
        if not path.is_file():
            st.warning(f"{label}: el archivo ya no está disponible en disco.")
            continue
        size = path.stat().st_size
        with columns[index % 2], st.container(border=True):
            st.write(f"**{label}** · {size / (1024 * 1024):.2f} MiB")
            if size <= 20 * 1024 * 1024:
                st.download_button(f"Descargar {label}", path.read_bytes(), file_name=path.name,
                                   mime=mime, key=f"download_{key}")
            else:
                st.info("Supera el límite de descarga de 20 MiB de esta interfaz. El archivo se conserva en la ruta indicada.")
            with st.expander(f"Ubicación de {label}"):
                st.code(str(path), language=None)


def show_summary(result):
    summary = result["summary"]
    result_context(result)
    st.success("Análisis finalizado · Resultados disponibles")
    configuration_warnings(summary)
    with Path(result["jsonl"]).open(encoding="utf-8") as source:
        latest = {}
        for line in source:
            latest = json.loads(line)
    decision = summary.get("final_decision", {})
    zones = summary.get("waiting_zones", [])
    metrics = (("Presencia en zonas", latest.get("total_vehicles") if zones else None),
               ("Estado final", {"GREEN": "Verde", "YELLOW": "Amarillo", "ALL_RED": "Todo rojo"}.get(decision.get("current_light_state"), "Sin dato")),
               ("Experiencias completas", summary.get("experience", {}).get("generated")),
               ("Fotogramas analizados", summary.get("frames_processed")))
    video_column, signal_column = st.columns([2, 1])
    with video_column, st.container(border=True):
        st.subheader("Video procesado")
        if result.get("web_video") and Path(result["web_video"]).is_file():
            st.video(str(result["web_video"]))
        else:
            st.warning("La reproducción web no está disponible. Conservas el video original anotado y los demás resultados en las descargas.")
        st.caption("Cajas: detecciones · Líneas: conteo de cruces · Polígonos: presencia, si están configurados.")
    with signal_column, st.container(border=True):
        st.subheader("Semáforo virtual")
        show_signal(decision, summary.get("traffic_phases", []))
    for column, (label, value) in zip(st.columns(4), metrics):
        with column, st.container(border=True):
            st.metric(label, "Sin dato" if value is None else value)
    if zones and latest:
        st.caption(f"Presencia: última observación guardada en t={latest['timestamp']:.2f} s. Solo vehículos rastreados dentro de la unión de zonas; no implica que estén detenidos.")
    st.info("Simulación académica por reglas. No controla semáforos reales ni aprende de las experiencias registradas.")
    show_downloads(result)


def read_records(path):
    with Path(path).open(encoding="utf-8") as source:
        return [json.loads(line) for line in source]


def show_traffic(result):
    summary = result["summary"]
    zones = {zone["id"]: zone["name"] for zone in summary.get("waiting_zones", [])}
    phases = summary.get("traffic_phases", [])
    records = read_records(result["jsonl"])
    latest = records[-1] if records else {}
    st.subheader("Presencia por zona")
    st.caption("Automóviles, motocicletas, autobuses y camiones rastreados en polígonos. La presencia no demuestra detención ni espera individual.")
    if zones:
        table = []
        for zone, name in zones.items():
            analysis = latest.get("analysis", {}).get(zone, {})
            table.append({"Zona": name, "Vehículos presentes": latest.get("vehicles_by_zone", {}).get(zone),
                          "Promedio reciente": analysis.get("average_count"),
                          "Tendencia": humanize_trend(analysis.get("trend"), analysis.get("status")),
                          "Muestras válidas": analysis.get("sample_count")})
        st.dataframe(table, hide_index=True, width=1600)
        st.caption("Los conteos de zonas solapadas pueden incluir el mismo vehículo. Sin dato no equivale a cero.")
        if latest:
            st.caption(f"Conteos: t={latest['timestamp']:.2f} s · Análisis utilizado: t={latest.get('analysis_timestamp', latest['timestamp']):.2f} s.")
        st.subheader("Evolución de la presencia")
        selected = st.multiselect("Zonas de la gráfica", list(zones), default=list(zones)[:4],
                                 format_func=lambda key: zones[key], key="traffic_zones")
        rows = analysis_rows(result["jsonl"])
        readable = [{"Tiempo (s)": row["timestamp"], "Zona": zones.get(row["zona"], row["zona"]),
                     "Vehículos": row["vehículos actuales"], "Promedio": row["promedio"],
                     "Tendencia": humanize_trend(row["tendencia"], row.get("status")),
                     "Fase registrada": humanize_phase_name(row["fase"], phases)}
                    for row in rows if row["zona"] in selected]
        if readable:
            # La tabla y el resumen textual permiten interpretar series sin depender del color.
            st.line_chart(readable, x="Tiempo (s)", y="Vehículos", color="Zona")
            with st.expander("Datos de la gráfica", expanded=True):
                st.dataframe(readable, hide_index=True, width=1600)
        else:
            st.info("Selecciona una zona con observaciones para consultar su evolución.")
        with st.expander("Análisis técnico por muestra"):
            st.dataframe(rows, hide_index=True, width=1600)
    else:
        st.info("Configura polígonos de presencia para consultar ocupación y tendencias. Los cruces de líneas siguen disponibles.")

    st.subheader("Objetos detectados por clase")
    last_row = {}
    with Path(result["csv"]).open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            last_row = row
    labels = {"persona": "Persona", "bicicleta": "Bicicleta", "automovil": "Automóvil",
              "motocicleta": "Motocicleta", "autobus": "Autobús", "camion": "Camión"}
    classes = [{"Clase": label,
                "Visibles al final": int(last_row[f"visibles_{key}"]) if f"visibles_{key}" in last_row else None,
                "Máximo simultáneo de la clase": summary.get("maximum_simultaneous_by_class", {}).get(key)}
               for key, label in labels.items()]
    st.dataframe(classes, hide_index=True, width=1600)
    st.caption("Los máximos de cada clase pueden ocurrir en momentos distintos; no se suman como un máximo global. Los IDs observados son solo diagnóstico técnico.")

    st.subheader("Cruces detectados por línea")
    crossings = summary.get("crossings", {})
    if not crossings:
        st.info("No hay resultados de cruces disponibles en esta ejecución.")
        return
    line = st.selectbox("Línea de conteo", list(crossings), format_func=lambda key: crossings[key]["name"], key="crossing_line")
    crossing = crossings[line]
    table = [{"Clase": labels.get(key, key), "Sentido": crossing["directions"][direction], "Cruces": count}
             for key, counts in crossing["by_class"].items() for direction, count in counts.items()]
    st.dataframe(table, hide_index=True, width=1600)
    if table:
        st.bar_chart(table, x="Clase", y="Cruces", color="Sentido")
    st.caption("Eventos detectados al atravesar esta línea. Un ID cuenta como máximo una vez por línea. No son vehículos únicos entre líneas ni conteos validados contra anotación manual.")


def show_controller(result):
    summary = result["summary"]
    phases = summary.get("traffic_phases", [])
    decision = summary.get("final_decision", {})
    with st.container(border=True):
        st.subheader("Estado final registrado")
        show_signal(decision, phases)
        if decision.get("timestamp") is not None:
            st.write(f"Instante del video: {decision['timestamp']:.2f} s")
        if phases and decision.get("elapsed_state_time") is not None:
            st.write(f"Tiempo transcurrido en este estado: {decision['elapsed_state_time']:.2f} s")
        if decision.get("next_phase") is not None:
            st.write("**Siguiente fase provisional:** " + humanize_phase_name(decision["next_phase"], phases))
            st.caption("Se volverá a elegir al terminar el intervalo con todas las direcciones en rojo.")

    st.subheader("Prioridad calculada y fase con verde")
    ranked = decision.get("phase_priorities", {})
    if phases and ranked:
        table = [{"Fase": humanize_phase_name(key, phases), "Ocupaciones en sus zonas": values.get("demand"),
                  "Prioridad base": values.get("score"), "Aporte por espera": values.get("starvation_bonus"),
                  "Prioridad efectiva": values.get("effective_score"), "Espera de fase (s)": values.get("waiting_seconds")}
                 for key, values in ranked.items()]
        st.dataframe(table, hide_index=True, width=1600)
        candidates = {key: value for key, value in ranked.items()
                      if value.get("effective_score") is not None and (value.get("demand") or 0) > 0}
        if decision.get("mode") == "ADAPTIVE" and candidates:
            best = max(value["effective_score"] for value in candidates.values())
            st.write("**Mayor prioridad efectiva entre fases con presencia:** " + ", ".join(
                humanize_phase_name(key, phases) for key, value in candidates.items() if value["effective_score"] == best))
        else:
            st.info("No hay una prioridad adaptativa disponible con demanda registrada.")
        st.caption("Último cálculo disponible. La prioridad puede diferir de la fase activa: se respeta el verde planificado, el despeje y la atención de fases con espera vencida. La espera es de fase, no de cada vehículo.")
    else:
        st.info("No hay prioridades por fase disponibles. Revisa la configuración de zonas y fases.")

    records = read_records(result["jsonl"])
    starts = [record for record in records if record.get("decision") == "INICIAR"]
    st.subheader("Última decisión de verde")
    if starts:
        chosen = starts[-1]
        st.write("**Dirección elegida:** " + humanize_phase_name(chosen.get("current_phase"), phases))
        st.write(f"Inicio: {chosen['timestamp']:.2f} s · Verde planeado: {chosen['planned_green']:.1f} s")
        for explanation in decision_explanation(chosen):
            st.write("- " + explanation)
    else:
        st.info("Durante este video no se inició un nuevo período de verde.")
    st.caption("La confianza se inyecta para la simulación y no mide precisión de detección. El controlador usa reglas y una máquina de estados, sin aprendizaje de decisiones.")
    with st.expander("Ver detalles técnicos"):
        st.json(decision)
        if starts:
            st.json(starts[-1])


def show_history(result):
    summary = result["summary"]
    phases = summary.get("traffic_phases", [])
    records = read_records(result["jsonl"])
    events = [record for record in records if record.get("decision") not in (None, "MANTENER")]
    st.subheader("Historial de decisiones y transiciones")
    actions = {"INICIAR": "Inicio de verde", "FINALIZAR": "Fin de verde · Inicio de amarillo", "DESPEJAR": "Inicio de todo rojo"}
    if events:
        table = [{"Tiempo (s)": record["timestamp"], "Evento": actions.get(record["decision"], record["decision"]),
                  "Fase registrada": humanize_phase_name(record.get("current_phase"), phases),
                  "Estado": humanize_light_state(record.get("current_light_state"))} for record in events]
        st.dataframe(table, hide_index=True, width=1600)
        selected = st.selectbox("Consultar una decisión", range(len(events)),
                                format_func=lambda index: f"{events[index]['timestamp']:.2f} s · {actions.get(events[index]['decision'], events[index]['decision'])}", key="history_event")
        event = events[selected]
        if event["decision"] == "INICIAR":
            for explanation in decision_explanation(event):
                st.write("- " + explanation)
        elif event["decision"] == "FINALIZAR":
            st.write("Terminó el verde planificado. Se inicia el amarillo antes de dejar todas las direcciones en rojo.")
        else:
            st.write("Todas las direcciones pasan a rojo para respetar el despeje antes del próximo verde.")
        with st.expander("Motivos y datos originales del evento"):
            st.json(event)
    else:
        st.info("No hubo transiciones semafóricas registradas en este video.")

    st.subheader("Experiencias y evaluación")
    experience = summary.get("experience", {})
    if experience and not experience.get("enabled", True):
        st.info("El registro de experiencias está desactivado en esta configuración.")
    saved = session_experiences(experience) if experience.get("enabled", True) else []
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
            table.append({"Tiempo (s)": record["timestamp_decision"], "Fase atendida": humanize_phase_name(selected, phases),
                          "Duración del verde (s)": record["after"]["elapsed_seconds"],
                          "Vehículos antes": demands[0], "Vehículos después": demands[1],
                          "Puntuación de ocupación": evaluation.get("reward"),
                          "Resultado": humanize_reward(evaluation.get("reward")), "Uso futuro": humanize_eligibility(evaluation)})
        st.dataframe(table, hide_index=True, width=1600)
        numeric = [row for row in table if row["Puntuación de ocupación"] is not None]
        if len(numeric) > 1:
            st.line_chart(numeric, x="Tiempo (s)", y="Puntuación de ocupación")
        st.caption("Se compara ocupación al comenzar y terminar un verde completo; no mide vehículos que atravesaron el cruce ni demuestra una mejora causada por el semáforo virtual en un video grabado.")
    else:
        st.info("No hay períodos de verde completos guardados para comparar en esta ejecución.")
    if experience:
        st.write(f"**Experiencias generadas:** {experience.get('generated', 0)}")
        if experience.get("enabled", True):
            st.write(f"**Acumuladas al terminar esta ejecución:** {experience.get('dataset_count', 0)}")
        if experience.get("incomplete"):
            st.caption("El último verde no terminó antes del final del video; no se guardó como experiencia completa.")
        if experience.get("generated", 0) and not saved:
            st.warning("El resumen informa experiencias, pero su dataset no está disponible. Los demás archivos de resultados siguen siendo consultables.")
    st.info("Registrar experiencias, evaluar ocupación y aprender son procesos distintos. Actualmente no hay entrenamiento automático; la elegibilidad no garantiza calibración ni precisión.")
    show_downloads(result)
    with st.expander("Ver detalles técnicos"):
        st.caption("La banda de presentación del reward es de −0.5 a +0.5. No cambia su fórmula ni su elegibilidad.")
        st.write("**Identificador de ejecución:** " + str(result.get("ui_context", {}).get("run_id", experience.get("session_id", "No disponible"))))
        st.json(summary)
        if saved:
            st.json(saved)
        if records:
            st.json(records[-1])


def show_results(result, section="Resumen"):
    if section == "Resumen":
        show_summary(result)
        return
    result_context(result)
    configuration_warnings(result["summary"])
    {"Tráfico": show_traffic, "Semáforo virtual": show_controller,
     "Historial y resultados": show_history}[section](result)
