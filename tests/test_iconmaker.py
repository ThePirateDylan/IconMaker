import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import convert_icons as app


class IconMakerCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.outputs = self.root / "outputs"
        self.logs = self.root / "logs"
        self.crashlogs = self.root / "crashlog"
        self.settings_path = self.root / "settings.json"
        self.inputs.mkdir()
        self.outputs.mkdir()
        self.log_patches = [
            patch.object(app, "LOG_DIR", self.logs),
            patch.object(app, "CRASHLOG_DIR", self.crashlogs),
            patch.object(app, "SETTINGS_PATH", self.settings_path),
        ]
        for item in self.log_patches:
            item.start()

    def tearDown(self):
        for item in self.log_patches:
            item.stop()
        self.temp.cleanup()

    def make_png(self, path: Path, color=(30, 120, 240, 255)):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (120, 80), color).save(path)

    def options(self, **overrides):
        values = dict(
            input_dir=str(self.inputs), output_dir=str(self.outputs),
            icon_sizes=list(app.AVAILABLE_ICON_SIZES),
            fit_mode="Contain (transparent padding)",
            naming_mode="Original filename", custom_prefix="icon_",
            conflict_policy="Add numbered suffix", source_files=None,
        )
        values.update(overrides)
        return app.ConversionOptions(**values)

    def test_custom_application_icon_contains_standard_windows_sizes(self):
        icon_path = Path(app.__file__).resolve().parent / "assets" / "iconmaker.ico"
        self.assertTrue(icon_path.is_file())
        with Image.open(icon_path) as icon:
            expected = {(size, size) for size in app.AVAILABLE_ICON_SIZES}
            self.assertTrue(expected.issubset(icon.ico.sizes()))

    def test_latest_release_metadata_is_parsed_and_release_url_validated(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        payload = {
            "tag_name": "v1.5.0", "name": "IconMaker 1.5.0",
            "html_url": "https://github.com/ThePirateDylan/IconMaker/releases/tag/v1.5.0",
            "draft": False, "prerelease": False,
        }
        with patch.object(app.urllib.request, "urlopen", return_value=FakeResponse(payload)):
            result = app.fetch_latest_release()
        self.assertEqual(result["version"], "1.5.0")
        self.assertEqual(result["url"], payload["html_url"])

        payload["html_url"] = "https://example.com/not-the-release"
        with patch.object(app.urllib.request, "urlopen", return_value=FakeResponse(payload)):
            with self.assertRaises(ValueError):
                app.fetch_latest_release()

    def test_version_tags_sort_numerically(self):
        self.assertGreater(app.version_key("v1.10.0"), app.version_key("v1.9.9"))
        self.assertEqual(app.version_key("1.4"), (1, 4, 0))

    def test_conversion_creates_ico_and_emits_summary(self):
        self.make_png(self.inputs / "sample.png")
        events = []
        summary = app.run_conversion(self.options(), lambda k, v: events.append((k, v)))
        output = self.outputs / "sample.ico"
        self.assertTrue(output.is_file())
        with Image.open(output) as icon:
            self.assertEqual(icon.format, "ICO")
            self.assertTrue({(size, size) for size in app.AVAILABLE_ICON_SIZES}.issubset(icon.ico.sizes()))
        self.assertEqual(summary.succeeded, 1)
        self.assertEqual(summary.failed, 0)
        self.assertGreaterEqual(summary.elapsed_seconds, 0)
        done = [json.loads(value) for kind, value in events if kind == "done"][-1]
        self.assertEqual(done["succeeded"], 1)
        self.assertIn(("progress_detail", "1 of 1 — 100%"), events)

    def test_default_conflict_policy_preserves_existing_icon(self):
        self.make_png(self.inputs / "sample.png")
        (self.outputs / "sample.ico").write_bytes(b"keep existing")
        summary = app.run_conversion(self.options())
        self.assertEqual(summary.succeeded, 1)
        self.assertEqual((self.outputs / "sample.ico").read_bytes(), b"keep existing")
        self.assertTrue((self.outputs / "sample (2).ico").is_file())

    def test_all_supported_source_formats_convert(self):
        samples = [
            ("sample.png", "PNG"), ("sample.jpg", "JPEG"), ("sample.jpeg", "JPEG"),
            ("sample.webp", "WEBP"), ("sample.bmp", "BMP"), ("sample.gif", "GIF"),
            ("sample.tif", "TIFF"), ("sample.tiff", "TIFF"),
        ]
        for filename, image_format in samples:
            Image.new("RGB", (48, 36), (90, 150, 210)).save(self.inputs / filename, format=image_format)
        summary = app.run_conversion(self.options())
        self.assertEqual(summary.total, len(samples))
        self.assertEqual(summary.succeeded, len(samples))
        self.assertEqual(summary.failed, 0)
        self.assertEqual(len(list(self.outputs.glob("*.ico"))), len(samples))
        self.assertTrue(all(item.is_file() for item in self.outputs.glob("*.ico")))

    def test_image_fitting_modes_keep_square_icon_canvas(self):
        self.make_png(self.inputs / "sample.png", color=(30, 120, 240, 200))
        for mode in ("Contain (transparent padding)", "Stretch to square", "Cover (center crop)"):
            out = self.root / (mode.split()[0].lower() + "-fit")
            summary = app.run_conversion(self.options(output_dir=str(out), fit_mode=mode))
            self.assertEqual(summary.succeeded, 1, mode)
            with Image.open(out / "sample.ico") as icon:
                self.assertEqual(icon.size, (256, 256), mode)

    def test_naming_modes_remain_available(self):
        self.make_png(self.inputs / "sample.png")
        for mode, expected in (("Original filename", "sample.ico"), ("Add _icon suffix", "sample_icon.ico"), ("Custom prefix", "app_sample.ico")):
            out = self.root / mode.replace(" ", "_")
            summary = app.run_conversion(self.options(output_dir=str(out), naming_mode=mode, custom_prefix="app_"))
            self.assertEqual(summary.succeeded, 1, mode)
            self.assertTrue((out / expected).is_file(), mode)

    def test_settings_keep_new_preferences_and_old_defaults(self):
        app.save_settings({"theme": "Dark", "check_updates_on_startup": False})
        loaded = app.load_settings()
        self.assertEqual(loaded["theme"], "Dark")
        self.assertFalse(loaded["check_updates_on_startup"])
        self.assertIn("icon_sizes", loaded)
        self.assertIn("fit_mode", loaded)

    def test_cancel_event_stops_before_processing_any_files(self):
        self.make_png(self.inputs / "sample.png")
        event = threading.Event()
        event.set()
        summary = app.run_conversion(self.options(), cancel_event=event)
        self.assertTrue(summary.cancelled)
        self.assertEqual(summary.succeeded, 0)
        self.assertFalse((self.outputs / "sample.ico").exists())

    def test_cancellation_requested_during_first_file_finishes_that_file_only(self):
        self.make_png(self.inputs / "first.png")
        self.make_png(self.inputs / "second.png", color=(220, 70, 50, 255))
        event = threading.Event()

        def emit(kind, message):
            if kind == "status" and message.startswith("Converting 1 of 2"):
                event.set()

        summary = app.run_conversion(self.options(), emit, event)
        self.assertTrue(summary.cancelled)
        self.assertEqual(summary.succeeded, 1)
        self.assertTrue((self.outputs / "first.ico").is_file())
        self.assertFalse((self.outputs / "second.ico").exists())

    def test_recursive_folder_conversion_preserves_relative_paths(self):
        self.make_png(self.inputs / "nested" / "sample.png")
        summary = app.run_conversion(self.options())
        self.assertEqual(summary.succeeded, 1)
        self.assertTrue((self.outputs / "nested" / "sample.ico").is_file())

    def test_invalid_images_are_reported_without_stopping_batch(self):
        (self.inputs / "broken.png").write_bytes(b"not a valid image")
        self.make_png(self.inputs / "good.png")
        summary = app.run_conversion(self.options())
        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.succeeded, 1)
        self.assertEqual(summary.failed, 1)
        self.assertTrue((self.outputs / "good.ico").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
