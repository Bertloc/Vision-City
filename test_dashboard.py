"""Invariantes de la UI: navegación de solo lectura y resultados ligados a su ejecución."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from streamlit_app import ROOT, SECTIONS


def render_main():
    from streamlit_app import main
    main()


def fixture_result(root):
    phases = [{"id": "phase_a", "name": "Dirección de prueba", "zones": ["zone_a"]}]
    analysis = {"zone_a": {"current_count": 4, "average_count": 6, "trend": "decreasing",
                           "status": "ok", "growth_rate": -1, "sample_count": 4}}
    records = [{"timestamp": second, "analysis_timestamp": second, "total_vehicles": 4,
                "vehicles_by_zone": {"zone_a": 4}, "analysis": analysis,
                "current_phase": "phase_a", "current_light_state": state, "decision": action,
                "phase_priorities": {"phase_a": {"score": 8, "effective_score": 8, "demand": 4,
                                                  "starvation_bonus": 0, "waiting_seconds": 1}},
                "remaining_seconds": 1, "planned_green": 3, "elapsed_state_time": 0,
                "mode": "ADAPTIVE", "reasons": ["Prioridad de fase"]}
               for second, state, action in ((1, "GREEN", "INICIAR"), (4, "YELLOW", "FINALIZAR"), (5, "ALL_RED", "DESPEJAR"))]
    dataset = root / "experiences.jsonl"
    experience = {"id": "sample", "session_id": "run-a", "timestamp_decision": 1,
                  "decision": {"selected_phase": "phase_a"},
                  "before": {"traffic_state": {"vehicles_by_zone": {"zone_a": 8}}},
                  "after": {"traffic_state": {"vehicles_by_zone": {"zone_a": 4}}, "elapsed_seconds": 3},
                  "evaluation": {"reward": 4, "training_eligible": True}}
    dataset.write_text(json.dumps(experience) + "\n", encoding="utf-8")
    summary = {"generated_at": "2026-10-19T12:00:00", "video": {"source": "temporary.mp4"},
               "frames_processed": 150, "waiting_zones": [{"id": "zone_a", "name": "Zona de prueba"}],
               "traffic_phases": phases, "final_decision": records[-1],
               "maximum_simultaneous_by_class": {"automovil": 8},
               "crossings": {"line_a": {"name": "Línea de prueba", "directions": {"positive": "Entrada", "negative": "Salida"},
                                          "by_class": {"automovil": {"positive": 2, "negative": 1}},
                                          "totals": {"positive": 2, "negative": 1}}},
               "experience": {"session_id": "run-a", "source_video": "video-original.mp4", "dataset_path": str(dataset),
                              "enabled": True, "generated": 1, "dataset_count": 1, "incomplete": False}}
    paths = {key: root / name for key, name in (("json", "summary.json"), ("jsonl", "traffic.jsonl"),
                                               ("csv", "frames.csv"), ("video", "annotated.mp4"))}
    paths["json"].write_text(json.dumps(summary), encoding="utf-8")
    paths["jsonl"].write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    paths["csv"].write_text("fotograma,segundo,visibles_automovil\n149,5,4\n", encoding="utf-8-sig")
    paths["video"].write_bytes(b"test-video")
    return {**paths, "summary": summary, "ui_context": {"video_name": "video-original.mp4",
            "config_name": "config-original.json", "run_id": "run-a"}}


class DashboardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.result = fixture_result(self.root)

    def app(self, section="Resumen"):
        app = AppTest.from_function(render_main)
        app.session_state["result"] = self.result
        app.session_state["section"] = section
        return app

    @patch("streamlit_app.process_video")
    @patch("experience_logger.ExperienceLogger.save")
    def test_navigation_and_reruns_do_not_process_or_write(self, save, process):
        originals = {path: path.read_bytes() for path in self.root.iterdir()}
        app = self.app().run(timeout=20)
        for section in SECTIONS:
            app.radio(key="section").set_value(section).run(timeout=20)
            self.assertFalse(app.exception, section)
            if section != "Analizar video":
                self.assertIn("Video: video-original.mp4", [element.value for element in app.text])
                self.assertTrue(any("config-original.json" in element.value for element in app.caption))
        app.run(timeout=20)
        process.assert_not_called()
        save.assert_not_called()
        self.assertEqual(originals, {path: path.read_bytes() for path in self.root.iterdir()})

    def test_summary_does_not_call_clearance_an_active_green(self):
        app = self.app().run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "4")
        text = " ".join(item.value for item in app.markdown)
        self.assertNotIn("Fase con verde", text)
        self.assertTrue(any("Ninguna dirección tiene verde" in item.value for item in app.caption))
        self.assertGreaterEqual(len(app.get("download_button")), 4)

    def test_no_zones_or_phases_means_missing_data_not_zero(self):
        self.result["summary"].update(waiting_zones=[], traffic_phases=[])
        self.result["summary"]["final_decision"]["current_phase"] = None
        app = self.app().run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "Sin dato")
        self.assertTrue(any("Sin zonas" in item.value for item in app.warning))
        self.assertTrue(any("Sin fases" in item.value for item in app.warning))
        app.radio(key="section").set_value("Semáforo virtual").run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(any("No hay una dirección favorecida" in item.value for item in app.markdown))

    def test_modes_are_not_presented_as_detection_accuracy(self):
        for mode in ("FIXED_LOW", "SAFE_MODE"):
            self.result["summary"]["final_decision"]["mode"] = mode
            app = self.app("Semáforo virtual").run(timeout=20)
            self.assertFalse(app.exception)
            self.assertTrue(any("simula" in item.value.lower() for item in app.warning))
            self.assertTrue(any("no mide precisión" in item.value for item in app.caption))

    def test_missing_counts_and_insufficient_history_are_not_invented(self):
        records = [json.loads(line) for line in self.result["jsonl"].read_text().splitlines()]
        records[-1]["vehicles_by_zone"] = {}
        records[-1]["analysis"]["zone_a"].update(status="insufficient_history", growth_rate=None)
        self.result["jsonl"].write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        app = self.app("Tráfico").run(timeout=20)
        self.assertFalse(app.exception)
        row = app.dataframe[0].value.iloc[0]
        self.assertTrue(row["Vehículos presentes"] is None)
        self.assertIn("Aún no hay suficiente", row["Tendencia"])

    def prepare_inputs(self):
        (self.root / "config").mkdir()
        (self.root / "data/videos").mkdir(parents=True)
        (self.root / "data/videos/selected.mp4").write_bytes(b"input")
        data = (ROOT / "config/intersection.json").read_bytes()
        (self.root / "config/intersection.json").write_bytes(data)
        (self.root / "config/simulation.json").write_text('{"events": []}')

    def test_simulation_is_not_offered_and_invalid_config_prevents_processing(self):
        self.prepare_inputs()
        (self.root / "config/intersection.json").write_text('{"counting_lines": []}')
        with patch("streamlit_app.ROOT", self.root), patch("streamlit_app.process_video") as process:
            app = self.app("Analizar video").run(timeout=20)
            self.assertFalse(app.exception)
            self.assertEqual(app.selectbox[1].options, ["intersection.json"])
            self.assertTrue(app.button[0].disabled)
            self.assertIn("líneas de conteo", app.error[0].value)
            process.assert_not_called()

    def test_failed_analysis_preserves_previous_result(self):
        self.prepare_inputs()
        with patch("streamlit_app.ROOT", self.root), patch("streamlit_app.process_video", side_effect=RuntimeError("CUDA test")) as process:
            app = self.app("Analizar video").run(timeout=20)
            app.button[0].click().run(timeout=20)
            self.assertFalse(app.exception)
            self.assertIn("No pudimos terminar", app.error[0].value)
            self.assertEqual(app.session_state["result"]["ui_context"]["video_name"], "video-original.mp4")
            process.assert_called_once()

    def test_success_saves_input_identity_even_when_video_conversion_fails(self):
        self.prepare_inputs()

        def process(source, config, output, callback, **kwargs):
            output.mkdir(parents=True)
            callback(1, None)
            callback(2, 2)
            return deepcopy(self.result)

        with patch("streamlit_app.ROOT", self.root), patch("streamlit_app.process_video", side_effect=process) as pipeline, \
                patch("streamlit_app.browser_video", side_effect=RuntimeError("codec test")):
            app = self.app("Analizar video").run(timeout=20)
            app.button[0].click().run(timeout=20)
            self.assertFalse(app.exception)
            saved = app.session_state["result"]
            self.assertEqual(saved["ui_context"]["video_name"], "selected.mp4")
            self.assertEqual(saved["ui_context"]["config_name"], "intersection.json")
            self.assertTrue(saved["ui_context"]["configuration"].is_file())
            self.assertIsNone(saved["web_video"])
            app.radio(key="section").set_value("Resumen").run(timeout=20)
            self.assertFalse(app.exception)
            self.assertTrue(any("reproducción web" in item.value for item in app.warning))
            pipeline.assert_called_once()

    def test_large_download_has_a_visible_reason_and_keeps_path(self):
        with self.result["video"].open("wb") as target:
            target.truncate(21 * 1024 * 1024)
        app = self.app().run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(any("20 MiB" in item.value for item in app.info))
        labels = [item.proto.label for item in app.get("download_button")]
        self.assertNotIn("Descargar Video anotado", labels)


if __name__ == "__main__":
    unittest.main()
