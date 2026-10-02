import json
from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

from streamlit_app import (decision_explanation, humanize_eligibility,
                           humanize_light_state, humanize_phase_name,
                           humanize_reward, humanize_trend, session_experiences)


def render_results(result):
    from streamlit_app import show_results
    show_results(result)


class PresentationTests(unittest.TestCase):
    def test_trends_and_insufficient_information(self):
        self.assertIn("creciendo", humanize_trend("growing"))
        self.assertIn("estable", humanize_trend("stable"))
        self.assertIn("disminuyendo", humanize_trend("decreasing"))
        for status in ("insufficient_history", "missing_current", None):
            self.assertIn("Aún no hay suficiente", humanize_trend("stable", status))
        self.assertIn("Aún no hay suficiente", humanize_trend("unknown"))

    def test_light_names(self):
        self.assertIn("Verde", humanize_light_state("GREEN"))
        self.assertIn("Amarillo", humanize_light_state("YELLOW"))
        self.assertIn("Tiempo de despeje", humanize_light_state("ALL_RED"))
        self.assertEqual(humanize_light_state(None), "Estado no disponible")

    def test_reward_band_is_only_presentation(self):
        self.assertIn("positivo", humanize_reward(0.51))
        self.assertIn("empeoró", humanize_reward(-0.51))
        for reward in (-0.5, 0, 0.5):
            self.assertIn("no produjo un cambio claro", humanize_reward(reward))
        self.assertIn("No se pudo evaluar", humanize_reward(None))

    def test_phase_names_do_not_expose_internal_ids(self):
        phases = [{"id": "phase_ns", "name": "Norte - Sur"}]
        self.assertEqual(humanize_phase_name("phase_ns", phases), "Norte - Sur")
        self.assertNotIn("phase_unknown", humanize_phase_name("phase_unknown", phases))
        self.assertEqual(humanize_phase_name(None, phases), "Sin dirección seleccionada")

    def test_eligibility_and_causes(self):
        self.assertIn("puede servir", humanize_eligibility({"training_eligible": True}))
        explanation = humanize_eligibility({"training_eligible": False, "reasons": [
            "Confianza low durante el verde", "Modo SAFE_MODE durante el verde",
            "Decisión no adaptativa", "Conteos faltantes o inválidos"]})
        self.assertIn("no se usará", explanation)
        self.assertIn("confiables", explanation)
        self.assertIn("modo seguro", explanation)
        self.assertIn("secuencia fija", explanation)
        self.assertIn("conteos válidos", explanation)
        self.assertNotIn("SAFE_MODE", explanation)
        self.assertNotIn("low", explanation)

    def test_decision_explanations_follow_recorded_reasons(self):
        self.assertIn("secuencia fija", decision_explanation({"mode": "SAFE_MODE"})[0])
        self.assertIn("más tiempo de espera", decision_explanation({
            "mode": "ADAPTIVE", "reasons": ["Anti-starvation: fase con mayor espera vencida"]})[0])
        self.assertIn("No había vehículos", decision_explanation({
            "mode": "ADAPTIVE", "reasons": ["Sin demanda: rotación fija con verde mínimo"]})[0])
        self.assertIn("parecidas", decision_explanation({
            "mode": "ADAPTIVE", "reasons": ["Margen de histéresis: continuidad tras el despeje"]})[0])

    def test_initial_screen(self):
        app = AppTest.from_file(str(Path(__file__).parent / "streamlit_app.py")).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "VISIÓN CITY")
        self.assertEqual(app.button[0].label, "ANALIZAR VIDEO")
        self.assertIn("1. Elige un video", [heading.value for heading in app.subheader])
        self.assertIn("2. Elige la configuración del cruce", [heading.value for heading in app.subheader])

    def test_results_render_friendly_table_and_keep_technical_details(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = {key: root / (key + ".json") for key in ("video", "csv", "json", "jsonl")}
            for path in paths.values():
                path.write_text("{}", encoding="utf-8")
            record = {"timestamp": 1, "analysis_timestamp": 1,
                      "vehicles_by_zone": {"north": 8}, "total_vehicles": 8,
                      "analysis": {"north": {"current_count": 8, "average_count": 8,
                                               "trend": "growing", "status": "ok", "growth_rate": 0.42}},
                      "priority": {"scores": {"north": {"score": 13.7, "components": {"growth": 0.84}}}},
                      "current_phase": "phase_ns", "current_light_state": "GREEN",
                      "mode": "ADAPTIVE", "planned_green": 34, "remaining_seconds": 30,
                      "decision": "INICIAR", "reasons": ["Prioridad de fase"],
                      "phase_priorities": {"phase_ns": {"demand": 8, "effective_score": 13.7}}}
            paths["jsonl"].write_text(json.dumps(record) + "\n", encoding="utf-8")
            dataset = root / "experiences.jsonl"
            experience = {"id": "id", "session_id": "session", "timestamp_decision": 1,
                          "decision": {"selected_phase": "phase_ns"},
                          "before": {"traffic_state": {"vehicles_by_zone": {"north": 8}}},
                          "after": {"traffic_state": {"vehicles_by_zone": {"north": 4}}, "elapsed_seconds": 34},
                          "evaluation": {"reward": 4, "training_eligible": True}}
            dataset.write_text(json.dumps(experience) + "\n" + json.dumps(dict(experience, session_id="other")) + "\n", encoding="utf-8")
            info = {"session_id": "session", "dataset_path": str(dataset), "generated": 1,
                    "dataset_count": 2, "incomplete": False, "rows": [{"reward": 4}], "average_reward": 4}
            summary = {"waiting_zones": [{"id": "north", "name": "Norte"}],
                       "traffic_phases": [{"id": "phase_ns", "name": "Norte - Sur", "zones": ["north"]}],
                       "final_decision": record, "experience": info}
            self.assertEqual(len(session_experiences(info)), 1)
            original = dataset.read_bytes()
            app = AppTest.from_function(render_results, args=({**paths, "summary": summary},)).run(timeout=20)
            self.assertFalse(app.exception)
            table = app.dataframe[0].value
            self.assertEqual(table.iloc[0]["Fase atendida"], "Norte - Sur")
            self.assertEqual(table.iloc[0]["Vehículos antes"], 8)
            self.assertIn("positivo", table.iloc[0]["Resultado"])
            self.assertNotIn("reward", table.columns)
            self.assertNotIn("training_eligible", table.columns)
            self.assertIn("Ver detalles técnicos", [expander.label for expander in app.expander])
            self.assertEqual(dataset.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
