import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from app import main, process_video

CONFIG = Path(__file__).parent / "config/intersection.json"


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "input.avi"
        writer = cv2.VideoWriter(str(self.video), cv2.VideoWriter_fourcc(*"MJPG"), 2, (320, 240))
        self.assertTrue(writer.isOpened())
        for _ in range(4):
            writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
        writer.release()

    @patch("app.torch.cuda.is_available", return_value=False)
    @patch("app.YOLO")
    def test_shared_pipeline_outputs_progress_and_final_state(self, yolo, _cuda):
        yolo.return_value.track.side_effect = lambda frame, **kwargs: [
            Mock(boxes=None, plot=lambda: frame.copy())]
        updates = []
        with redirect_stdout(io.StringIO()):
            result = process_video(self.video, CONFIG, self.root / "results",
                                   lambda done, total: updates.append((done, total)))
        self.assertEqual(updates, [(0, None), (1, 4), (2, 4), (3, 4), (4, 4)])
        self.assertEqual(result["summary"]["frames_processed"], 4)
        self.assertEqual(result["summary"]["device"], "CPU")
        self.assertEqual(result["summary"]["final_decision"]["current_light_state"], "ALL_RED")
        for key in ("video", "csv", "json", "jsonl"):
            self.assertTrue(result[key].is_file())
            self.assertGreater(result[key].stat().st_size, 0)
        saved = json.loads(result["json"].read_text(encoding="utf-8"))
        self.assertEqual(saved, result["summary"])
        self.assertEqual(yolo.return_value.track.call_count, 4)
        self.assertEqual(yolo.return_value.track.call_args.kwargs["tracker"], "bytetrack.yaml")

    @patch("app.YOLO")
    def test_invalid_configuration_before_loading_model(self, yolo):
        bad = self.root / "bad.json"
        bad.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            process_video(self.video, bad, self.root / "results")
        yolo.assert_not_called()

    @patch("app.torch.cuda.is_available", return_value=False)
    @patch("app.YOLO")
    def test_two_video_sessions_append_using_shared_pipeline(self, yolo, _cuda):
        yolo.return_value.track.side_effect = lambda frame, **kwargs: [
            Mock(boxes=None, plot=lambda: frame.copy())]
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        config["waiting_zones"] = [{"id": "zone", "name": "Zona", "points": [[0, 0], [1, 0], [1, 1]]}]
        config["traffic_phases"] = [{"id": "phase", "name": "Fase", "zones": ["zone"]}]
        config["simulation_parameters"].update(min_green_seconds=0.25, max_green_seconds=0.25,
                                                safe_green_seconds=0.25, all_red_seconds=0.25)
        dataset = self.root / "experiences.jsonl"
        config["experience_evaluation"] = {"dataset_path": str(dataset)}
        path = self.root / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            first = process_video(self.video, path, self.root / "one")
            original = dataset.read_bytes()
            second = process_video(self.video, path, self.root / "two")
        self.assertTrue(dataset.read_bytes().startswith(original))
        self.assertEqual(first["summary"]["experience"]["generated"], 1)
        self.assertEqual(second["summary"]["experience"]["dataset_count"], 2)
        records = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
        self.assertNotEqual(records[0]["session_id"], records[1]["session_id"])

    @patch("app.torch.cuda.is_available", return_value=False)
    @patch("app.YOLO")
    def test_missing_video_and_model_error(self, yolo, _cuda):
        with redirect_stdout(io.StringIO()), self.assertRaises(FileNotFoundError):
            process_video(self.root / "missing.mp4", CONFIG, self.root / "results")
        yolo.side_effect = RuntimeError("No se pudo cargar el modelo")
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "modelo"):
            process_video(self.video, CONFIG, self.root / "results")

    @patch("app.torch.cuda.is_available", return_value=False)
    @patch("app.YOLO")
    def test_processing_error_releases_capture(self, yolo, _cuda):
        capture = cv2.VideoCapture(str(self.video))
        yolo.return_value.track.side_effect = RuntimeError("CUDA de prueba")
        with patch("app.open_source", return_value=capture), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "CUDA"):
                process_video(self.video, CONFIG, self.root / "results")
        self.assertFalse(capture.isOpened())

    @patch("app.process_video")
    @patch("app.parse_args")
    def test_cli_delegates_all_options(self, parse, process):
        parse.return_value = argparse.Namespace(source="video.mp4", config="config.json", output="out",
                                              model="model.pt", conf=0.4, show=True,
                                              simulation_confidence="low")
        main()
        process.assert_called_once_with("video.mp4", "config.json", "out", model="model.pt",
                                        conf=0.4, show=True, simulation_confidence="low")

    def test_table_excludes_repeated_analysis_between_samples(self):
        from streamlit_app import analysis_rows

        record = {"timestamp": 0, "analysis_timestamp": 0,
                  "analysis": {"a": {"current_count": 2, "average_count": 2, "trend": "stable"}},
                  "priority": {"scores": {"a": {"score": 3}}},
                  "current_phase": "phase", "current_light_state": "GREEN"}
        path = self.root / "traffic.jsonl"
        path.write_text(json.dumps(record) + "\n" + json.dumps(dict(record, timestamp=0.5)), encoding="utf-8")
        rows = analysis_rows(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["vehículos actuales"], 2)
        self.assertEqual(rows[0]["prioridad"], 3)


if __name__ == "__main__":
    unittest.main()
