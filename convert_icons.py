#!/usr/bin/env python3
"""IconMaker 1.4.0 - Windows ICO converter with GUI and batch support."""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
import webbrowser
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

APP_NAME = "IconMaker"
VERSION = "1.4.0"
GITHUB_REPOSITORY = "https://github.com/ThePirateDylan/IconMaker"
GITHUB_RELEASES_URL = f"{GITHUB_REPOSITORY}/releases/latest"
GITHUB_LATEST_RELEASE_API = "https://api.github.com/repos/ThePirateDylan/IconMaker/releases/latest"
SUPPORTED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"
}
AVAILABLE_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
DEFAULT_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

# When frozen by PyInstaller, keep user data beside the executable rather than
# inside the temporary extraction directory.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

INPUT_DIR = BASE_DIR / "inputs"
OUTPUT_DIR = BASE_DIR / "outputs"
LOG_DIR = BASE_DIR / "logs"
CRASHLOG_DIR = BASE_DIR / "crashlog"
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
ASSET_DIR = RESOURCE_DIR / "assets"
APP_ICON_ICO = ASSET_DIR / "iconmaker.ico"
APP_ICON_PNG = ASSET_DIR / "iconmaker.png"
SETTINGS_PATH = BASE_DIR / "settings.json"

LogCallback = Callable[[str, str], None]


@dataclass
class ConversionOptions:
    input_dir: str
    output_dir: str
    icon_sizes: list[int]
    fit_mode: str = "Contain (transparent padding)"
    naming_mode: str = "Original filename"
    custom_prefix: str = "icon_"
    conflict_policy: str = "Add numbered suffix"
    source_files: list[str] | None = None


@dataclass
class ConversionSummary:
    total: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    log_path: str = ""
    output_dir: str = ""
    cancelled: bool = False
    elapsed_seconds: float = 0.0


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def version_key(version: str) -> tuple[int, ...]:
    """Convert a version/tag like v1.4.0 into a sortable numeric key."""
    numbers = re.findall(r"\d+", str(version))
    if not numbers:
        raise ValueError(f"Invalid version string: {version!r}")
    values = [int(part) for part in numbers[:4]]
    while len(values) < 3:
        values.append(0)
    return tuple(values)


def fetch_latest_release(timeout: float = 5.0) -> dict:
    """Fetch latest stable release metadata from the public GitHub API."""
    request = urllib.request.Request(
        GITHUB_LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"IconMaker-Updater/{VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        raise ValueError("GitHub did not return a stable release.")
    tag = str(payload.get("tag_name", "")).strip()
    url = str(payload.get("html_url", "")).strip()
    if not tag or not url.startswith("https://github.com/ThePirateDylan/IconMaker/releases/"):
        raise ValueError("GitHub returned an invalid release tag or URL.")
    version_key(tag)
    return {"tag": tag, "version": tag.lstrip("vV"), "url": url, "name": str(payload.get("name") or tag)}


def create_folders() -> None:
    for folder in (INPUT_DIR, OUTPUT_DIR, LOG_DIR, CRASHLOG_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def unique_timestamped_path(folder: Path, prefix: str, suffix: str) -> Path:
    base = folder / f"{prefix}{timestamp()}{suffix}"
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = folder / f"{prefix}{timestamp()}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def write_crash_log(title: str, details: str) -> Path:
    CRASHLOG_DIR.mkdir(parents=True, exist_ok=True)
    path = unique_timestamped_path(CRASHLOG_DIR, "IconMaker_crash_", ".log")
    path.write_text(
        f"{APP_NAME} {VERSION} - Crash Report\n"
        f"Time: {datetime.now().isoformat(timespec='seconds')}\n"
        f"Issue: {title}\n\n{details}\n",
        encoding="utf-8",
    )
    return path


def load_settings() -> dict:
    defaults = {
        "input_dir": str(INPUT_DIR),
        "output_dir": str(OUTPUT_DIR),
        "icon_sizes": list(DEFAULT_ICON_SIZES),
        "fit_mode": "Contain (transparent padding)",
        "naming_mode": "Original filename",
        "custom_prefix": "icon_",
        "conflict_policy": "Add numbered suffix",
        "theme": "System",
        "check_updates_on_startup": True,
    }
    try:
        if SETTINGS_PATH.is_file():
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                defaults.update(saved)
    except (OSError, json.JSONDecodeError) as exc:
        # --windowed PyInstaller builds can have no stderr stream.
        if sys.stderr is not None:
            print(f"[WARNING] Could not read settings file: {exc}", file=sys.stderr)
    raw_sizes = defaults.get("icon_sizes", DEFAULT_ICON_SIZES)
    if not isinstance(raw_sizes, (list, tuple, set)):
        raw_sizes = DEFAULT_ICON_SIZES
    cleaned_sizes = []
    for size in raw_sizes:
        try:
            parsed_size = int(size)
        except (TypeError, ValueError):
            continue
        if parsed_size in AVAILABLE_ICON_SIZES and parsed_size not in cleaned_sizes:
            cleaned_sizes.append(parsed_size)
    defaults["icon_sizes"] = cleaned_sizes or list(DEFAULT_ICON_SIZES)
    if defaults.get("fit_mode") not in {
        "Contain (transparent padding)", "Stretch to square", "Cover (center crop)"
    }:
        defaults["fit_mode"] = "Contain (transparent padding)"
    if defaults.get("naming_mode") not in {
        "Original filename", "Add _icon suffix", "Custom prefix"
    }:
        defaults["naming_mode"] = "Original filename"
    if defaults.get("conflict_policy") not in {
        "Add numbered suffix", "Skip existing output", "Overwrite existing output"
    }:
        defaults["conflict_policy"] = "Add numbered suffix"
    if defaults.get("theme") not in {"System", "Light", "Dark"}:
        defaults["theme"] = "System"
    defaults["check_updates_on_startup"] = bool(defaults.get("check_updates_on_startup", True))
    return defaults


def save_settings(data: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def setup_job_logger() -> tuple[logging.Logger, Path]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = unique_timestamped_path(LOG_DIR, "IconMaker_", ".log")
    logger = logging.getLogger("IconMaker.job")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except OSError:
            pass
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    return logger, path


def discover_images(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input folder does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a folder: {input_dir}")
    found: list[Path] = []
    # Iteration may fail on inaccessible subfolders; collect accessible files and
    # let the user's per-file errors be visible rather than silently swallowing them.
    for path in input_dir.rglob("*"):
        try:
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                found.append(path)
        except OSError:
            continue
    return sorted(found, key=lambda item: str(item.relative_to(input_dir)).casefold())


def _image_modules():
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:
        if getattr(sys, "frozen", False):
            message = (
                "IconMaker could not load its bundled Pillow dependency. Download a fresh "
                f"IconMaker.exe from {GITHUB_RELEASES_URL}"
            )
        else:
            message = "Pillow is missing from this Python environment. Install it with: python -m pip install --upgrade Pillow"
        raise RuntimeError(message) from exc
    return Image, ImageOps, UnidentifiedImageError


def apply_fit(image, fit_mode: str, canvas_size: int = 256):
    Image, _, _ = _image_modules()
    image = image.convert("RGBA")
    if fit_mode == "Stretch to square":
        return image.resize((canvas_size, canvas_size), Image.Resampling.LANCZOS)
    if fit_mode == "Cover (center crop)":
        scale = max(canvas_size / image.width, canvas_size / image.height)
        new_width = max(1, round(image.width * scale))
        new_height = max(1, round(image.height * scale))
        resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        left = (new_width - canvas_size) // 2
        top = (new_height - canvas_size) // 2
        return resized.crop((left, top, left + canvas_size, top + canvas_size))

    # Keep the original proportions and center the image on a transparent canvas.
    image.thumbnail((canvas_size, canvas_size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    x = (canvas_size - image.width) // 2
    y = (canvas_size - image.height) // 2
    canvas.alpha_composite(image, (x, y))
    return canvas


def output_stem(source: Path, options: ConversionOptions) -> str:
    stem = source.stem
    if options.naming_mode == "Add _icon suffix":
        return f"{stem}_icon"
    if options.naming_mode == "Custom prefix":
        prefix = options.custom_prefix.strip()
        # Restrict prefixes to a filename-safe subset for Windows paths.
        for char in '<>:"/\\|?*':
            prefix = prefix.replace(char, "_")
        prefix = prefix.strip(" .")
        return f"{prefix}{stem}" if prefix else stem
    return stem


def choose_destination(
    output_root: Path,
    relative_source: Path,
    options: ConversionOptions,
    reserved: set[Path],
) -> tuple[Path | None, str]:
    parent = output_root / relative_source.parent
    target = parent / f"{output_stem(relative_source, options)}.ico"
    collision = target.exists() or target in reserved
    if not collision:
        reserved.add(target)
        return target, "convert"

    if options.conflict_policy == "Skip existing output":
        return None, "skip"
    if options.conflict_policy == "Overwrite existing output":
        # Explicit overwrite policy is allowed to reuse destinations, but tracks
        # that destination so later sources in this same job follow the policy.
        reserved.add(target)
        return target, "convert"

    original_stem = target.stem
    counter = 2
    while True:
        candidate = target.with_name(f"{original_stem} ({counter}){target.suffix}")
        if not candidate.exists() and candidate not in reserved:
            reserved.add(candidate)
            return candidate, "convert"
        counter += 1


def _save_icon_atomic(canvas, destination: Path, sizes: list[int]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.stem}_", suffix=".ico.tmp", dir=destination.parent,
            delete=False,
        ) as temp:
            temporary_path = Path(temp.name)
        # Pillow chooses output format from the format argument, not the suffix.
        canvas.save(temporary_path, format="ICO", sizes=[(size, size) for size in sizes])
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _convert_one(source: Path, destination: Path, fit_mode: str, sizes: list[int]) -> None:
    Image, ImageOps, _ = _image_modules()
    with Image.open(source) as opened:
        # Pillow's ICO conversion is still a still-image operation: for animated
        # formats, this converts the currently selected (normally first) frame.
        image = ImageOps.exif_transpose(opened).convert("RGBA")
    canvas = apply_fit(image, fit_mode, 256)
    _save_icon_atomic(canvas, destination, sizes)


def run_conversion(
    options: ConversionOptions,
    emit: LogCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> ConversionSummary:
    """Convert supported images independently; cancellation finishes the current file first."""
    started_at = time.perf_counter()

    def send(kind: str, message: str) -> None:
        if emit:
            emit(kind, message)

    summary = ConversionSummary(output_dir=options.output_dir)

    def send_done() -> None:
        summary.elapsed_seconds = round(time.perf_counter() - started_at, 2)
        send("done", json.dumps(asdict(summary)))

    input_root = Path(options.input_dir).expanduser().resolve()
    output_root = Path(options.output_dir).expanduser().resolve()
    try:
        logger, log_path = setup_job_logger()
    except Exception as exc:
        summary.failed = 1
        send("fatal", f"Could not create the activity log: {type(exc).__name__}: {exc}")
        send_done()
        return summary
    summary.log_path = str(log_path)

    def log(level: int, message: str, *args) -> None:
        logger.log(level, message, *args)
        try:
            formatted = message % args if args else message
        except (TypeError, ValueError):
            formatted = message
        send("log", formatted)

    send("status", "Scanning for supported images…")
    try:
        if not options.icon_sizes:
            raise ValueError("Select at least one ICO size before converting.")
        if options.source_files is not None:
            # Explicitly selected files are flattened into the chosen output folder;
            # numbered-suffix collision handling keeps identical basenames distinct.
            image_items = []
            for raw_path in options.source_files:
                source_path = Path(raw_path).expanduser().resolve()
                relative_path = Path(source_path.name)
                image_items.append((source_path, relative_path))
            image_items.sort(key=lambda item: str(item[0]).casefold())
        else:
            image_items = [
                (source_path, source_path.relative_to(input_root))
                for source_path in discover_images(input_root)
            ]
        summary.total = len(image_items)
        send("scan_count", str(summary.total))
        output_root.mkdir(parents=True, exist_ok=True)
        log(logging.INFO, "IconMaker %s conversion started", VERSION)
        log(logging.INFO, "Input: %s", "selected files" if options.source_files is not None else input_root)
        log(logging.INFO, "Output: %s", output_root)
        log(logging.INFO, "Found %d selected image/file(s)", len(image_items))
        if not image_items:
            log(logging.INFO, "No supported images were found. Supported extensions: %s", ", ".join(sorted(SUPPORTED_EXTENSIONS)))
            send("progress", "0/0")
            send_done()
            logger.handlers[0].flush()
            logger.handlers[0].close()
            logger.handlers.clear()
            return summary

        # Import once up front so a missing Pillow installation is reported once.
        _image_modules()
        reserved: set[Path] = set()
        total_items = len(image_items)
        for index, (source, relative_source) in enumerate(image_items, start=1):
            if cancel_event is not None and cancel_event.is_set():
                summary.cancelled = True
                log(logging.WARNING, "[CANCELLED] Cancellation requested; remaining files were not processed.")
                break

            percent_before = round((index - 1) / total_items * 100) if total_items else 0
            send("status", f"Converting {index} of {total_items} ({percent_before}% complete): {relative_source}")
            if not source.is_file() or source.suffix.lower() not in SUPPORTED_EXTENSIONS:
                summary.skipped += 1
                log(logging.WARNING, "[SKIPPED] %s — missing file or unsupported extension", source)
            else:
                destination, action = choose_destination(output_root, relative_source, options, reserved)
                if action == "skip" or destination is None:
                    summary.skipped += 1
                    log(logging.WARNING, "[SKIPPED] %s — output already exists: %s", relative_source, output_root / relative_source.parent / f"{output_stem(relative_source, options)}.ico")
                else:
                    try:
                        _convert_one(source, destination, options.fit_mode, sorted(set(options.icon_sizes)))
                        summary.succeeded += 1
                        log(logging.INFO, "[SUCCESS] %s -> %s", relative_source, destination.relative_to(output_root))
                    except Exception as exc:
                        summary.failed += 1
                        log(logging.ERROR, "[FAILED] %s — %s: %s", relative_source, type(exc).__name__, exc)
                        logger.exception("Details for failed file %s", relative_source)

            send("counts", f"Success: {summary.succeeded} | Skipped: {summary.skipped} | Failed: {summary.failed}")
            percent_after = round(index / total_items * 100) if total_items else 100
            send("progress", f"{index}/{total_items}")
            send("progress_detail", f"{index} of {total_items} — {percent_after}%")

        if summary.cancelled:
            log(logging.WARNING, "Cancelled after %.2f seconds; %d file(s) completed before cancellation.", time.perf_counter() - started_at, summary.succeeded + summary.skipped + summary.failed)
        log(logging.INFO, "Summary: total=%d, succeeded=%d, skipped=%d, failed=%d, cancelled=%s", summary.total, summary.succeeded, summary.skipped, summary.failed, summary.cancelled)
        log(logging.INFO, "Activity log: %s", log_path)
        send_done()
        return summary
    except Exception as exc:
        summary.failed += 1
        log(logging.ERROR, "[JOB FAILED] %s: %s", type(exc).__name__, exc)
        logger.exception("Conversion job could not complete")
        send("fatal", f"{type(exc).__name__}: {exc}")
        send_done()
        return summary
    finally:
        for handler in list(logger.handlers):
            try:
                handler.flush()
                handler.close()
            except OSError:
                pass
            logger.removeHandler(handler)


def make_options_from_settings(settings: dict) -> ConversionOptions:
    return ConversionOptions(
        input_dir=str(settings.get("input_dir", INPUT_DIR)),
        output_dir=str(settings.get("output_dir", OUTPUT_DIR)),
        icon_sizes=[int(size) for size in settings.get("icon_sizes", DEFAULT_ICON_SIZES) if int(size) in AVAILABLE_ICON_SIZES],
        fit_mode=str(settings.get("fit_mode", "Contain (transparent padding)")),
        naming_mode=str(settings.get("naming_mode", "Original filename")),
        custom_prefix=str(settings.get("custom_prefix", "icon_")),
        conflict_policy=str(settings.get("conflict_policy", "Add numbered suffix")),
    )


def run_cli(args: argparse.Namespace) -> int:
    create_folders()
    settings = load_settings()
    options = make_options_from_settings(settings)
    if args.input_dir:
        options.input_dir = args.input_dir
    if args.output_dir:
        options.output_dir = args.output_dir
    if args.fit_mode:
        options.fit_mode = args.fit_mode
    if args.naming_mode:
        options.naming_mode = args.naming_mode
    if args.conflict_policy:
        options.conflict_policy = args.conflict_policy
    if args.sizes:
        options.icon_sizes = args.sizes

    def emit(kind: str, message: str) -> None:
        if kind in {"log", "status", "fatal"}:
            print(message)
    summary = run_conversion(options, emit)
    print("\n" + "=" * 54)
    print(f" {APP_NAME} {VERSION} — RUN SUMMARY")
    print("=" * 54)
    print(f" Total images : {summary.total}")
    print(f" Successful   : {summary.succeeded}")
    print(f" Skipped      : {summary.skipped}")
    print(f" Failed       : {summary.failed}")
    print(f" Output       : {summary.output_dir}")
    print(f" Activity log : {summary.log_path}")
    print(f" Crash reports: {CRASHLOG_DIR}")
    return 1 if summary.failed else 0


class IconMakerGUI:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.root.title(f"{APP_NAME} {VERSION}")
        self.root.geometry("940x720")
        self.root.minsize(820, 620)
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.scan_worker: threading.Thread | None = None
        self.update_worker: threading.Thread | None = None
        self.busy = False
        self.scanning = False
        self.update_check_running = False
        self.cancel_event = threading.Event()
        self.close_after_conversion = False
        create_folders()
        self.settings = load_settings()

        self.input_var = tk.StringVar(value=self.settings["input_dir"])
        self.output_var = tk.StringVar(value=self.settings["output_dir"])
        self.selection_var = tk.StringVar(value="Folder mode: supported images in the folder and subfolders will be converted.")
        self.selected_files: list[str] = []
        self.fit_var = tk.StringVar(value=self.settings["fit_mode"])
        self.naming_var = tk.StringVar(value=self.settings["naming_mode"])
        self.prefix_var = tk.StringVar(value=self.settings["custom_prefix"])
        self.conflict_var = tk.StringVar(value=self.settings["conflict_policy"])
        self.theme_var = tk.StringVar(value=self.settings.get("theme", "System"))
        self.check_updates_var = tk.BooleanVar(value=self.settings.get("check_updates_on_startup", True))
        self.size_vars = {size: tk.BooleanVar(value=size in self.settings["icon_sizes"]) for size in AVAILABLE_ICON_SIZES}
        self.status_var = tk.StringVar(value="Ready. Choose a source folder and start converting.")
        self.counts_var = tk.StringVar(value="Success: 0 | Skipped: 0 | Failed: 0")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_detail_var = tk.StringVar(value="0 of 0 — 0%")
        self.selection_scan_var = tk.StringVar(value="")
        self.style = ttk.Style(self.root)
        self.apply_theme()
        try:
            if APP_ICON_ICO.is_file():
                self.root.iconbitmap(str(APP_ICON_ICO))
            elif APP_ICON_PNG.is_file():
                self._app_icon_photo = tk.PhotoImage(file=str(APP_ICON_PNG))
                self.root.iconphoto(True, self._app_icon_photo)
        except Exception:
            pass

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.poll_events)
        if self.check_updates_var.get():
            self.root.after(1200, lambda: self.check_for_updates(manual=False))

    def apply_theme(self):
        """Apply a readable light, dark, or platform-default ttk theme."""
        requested = self.theme_var.get() if hasattr(self, "theme_var") else "System"
        bg, fg, select_bg = "#f3f5f8", "#202124", "#cfe3ff"
        try:
            if requested == "System":
                names = self.style.theme_names()
                target = "vista" if os.name == "nt" and "vista" in names else ("aqua" if sys.platform == "darwin" and "aqua" in names else "clam")
                self.style.theme_use(target)
                bg = str(self.root.cget("bg"))
                fg, select_bg = "SystemButtonText", "#316ac5"
                self.text_colors = ("white", "black", select_bg)
                return
            self.style.theme_use("clam")
            if requested == "Dark":
                bg, panel, fg, field_bg, field_fg = "#202124", "#292a2d", "#f1f3f4", "#303134", "#f1f3f4"
                select_bg, border = "#375a7f", "#55585c"
            else:
                bg, panel, fg, field_bg, field_fg = "#f3f5f8", "#ffffff", "#202124", "#ffffff", "#202124"
                select_bg, border = "#cfe3ff", "#c6cbd2"
            self.root.configure(background=bg)
            self.style.configure("TFrame", background=bg)
            self.style.configure("TLabelframe", background=bg, bordercolor=border)
            self.style.configure("TLabelframe.Label", background=bg, foreground=fg)
            self.style.configure("TLabel", background=bg, foreground=fg)
            self.style.configure("TButton", background=panel, foreground=fg, bordercolor=border, focusthickness=2, focuscolor=select_bg, padding=(8, 4))
            self.style.map("TButton", background=[("active", select_bg), ("disabled", bg)], foreground=[("disabled", "#888888")])
            self.style.configure("TEntry", fieldbackground=field_bg, foreground=field_fg, insertcolor=field_fg)
            self.style.configure("TCombobox", fieldbackground=field_bg, foreground=field_fg, background=panel, arrowcolor=fg)
            self.style.map("TCombobox", fieldbackground=[("readonly", field_bg)], foreground=[("readonly", field_fg)])
            self.style.configure("TCheckbutton", background=bg, foreground=fg)
            self.style.map("TCheckbutton", background=[("active", bg)], foreground=[("disabled", "#888888")])
            self.style.configure("Horizontal.TProgressbar", background="#2188ff", troughcolor=panel, bordercolor=border)
            self.text_colors = (field_bg, field_fg, select_bg)
        except Exception:
            self.text_colors = ("white", "black", "#316ac5")

    def change_theme(self):
        self.apply_theme()
        if hasattr(self, "log_text"):
            bg, fg, select_bg = getattr(self, "text_colors", ("white", "black", "#316ac5"))
            self.log_text.configure(background=bg, foreground=fg, insertbackground=fg, selectbackground=select_bg)
        if hasattr(self, "menu_widgets"):
            if self.theme_var.get() == "Dark":
                menu_colors = {"background": "#292a2d", "foreground": "#f1f3f4", "activebackground": "#375a7f", "activeforeground": "#ffffff"}
            elif self.theme_var.get() == "Light":
                menu_colors = {"background": "#ffffff", "foreground": "#202124", "activebackground": "#cfe3ff", "activeforeground": "#202124"}
            else:
                menu_colors = getattr(self, "native_menu_options", {})
            for menu in self.menu_widgets:
                try:
                    menu.configure(**menu_colors)
                except Exception:
                    pass
        self.save_current_settings(quiet=True)

    def _build_ui(self):
        tk, ttk = self.tk, self.ttk
        native_menu = tk.Menu(self.root, tearoff=False)
        try:
            self.native_menu_options = {
                key: native_menu.cget(key)
                for key in ("background", "foreground", "activebackground", "activeforeground")
            }
        finally:
            native_menu.destroy()

        # Keep diagnostic access inside the application; end users should not
        # need a console window or batch launcher to troubleshoot problems.
        if self.theme_var.get() == "Dark":
            menu_options = {"background": "#292a2d", "foreground": "#f1f3f4", "activebackground": "#375a7f", "activeforeground": "#ffffff"}
        elif self.theme_var.get() == "Light":
            menu_options = {"background": "#ffffff", "foreground": "#202124", "activebackground": "#cfe3ff", "activeforeground": "#202124"}
        else:
            menu_options = {}
        menubar = tk.Menu(self.root, tearoff=False, **menu_options)
        settings_menu = tk.Menu(menubar, tearoff=False, **menu_options)
        settings_menu.add_command(label="Check for updates now…", command=lambda: self.check_for_updates(manual=True))
        settings_menu.add_checkbutton(label="Check for updates on startup", variable=self.check_updates_var, command=lambda: self.save_current_settings(quiet=True))
        theme_menu = tk.Menu(settings_menu, tearoff=False, **menu_options)
        for theme_name in ("System", "Light", "Dark"):
            theme_menu.add_radiobutton(label=theme_name, value=theme_name, variable=self.theme_var, command=self.change_theme)
        settings_menu.add_cascade(label="Theme", menu=theme_menu)
        settings_menu.add_separator()
        settings_menu.add_command(label="Diagnostic Output…", command=self.show_diagnostic_output)
        settings_menu.add_command(label="Open Logs Folder", command=lambda: self.open_folder(str(LOG_DIR)))
        settings_menu.add_command(label="Open Crash Reports Folder", command=lambda: self.open_folder(str(CRASHLOG_DIR)))
        settings_menu.add_separator()
        settings_menu.add_command(label="Open Settings File", command=self.open_settings_file)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        help_menu = tk.Menu(menubar, tearoff=False, **menu_options)
        help_menu.add_command(label="About IconMaker…", command=self.show_about)
        help_menu.add_command(label="GitHub repository", command=lambda: webbrowser.open(GITHUB_REPOSITORY))
        menubar.add_cascade(label="Help", menu=help_menu)
        self.menu_widgets = [menubar, settings_menu, theme_menu, help_menu]
        self.root.configure(menu=menubar)

        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        heading = ttk.Frame(outer)
        heading.pack(fill="x", pady=(0, 12))
        ttk.Label(heading, text="IconMaker", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(heading, text=f"Batch image-to-ICO converter · Version {VERSION}").pack(anchor="w", pady=(2, 0))
        ttk.Label(heading, text="Made by The Pirate Dylan").pack(anchor="w", pady=(2, 0))

        folders = ttk.LabelFrame(outer, text="Folders", padding=10)
        folders.pack(fill="x", pady=(0, 10))
        ttk.Label(folders, text="Input folder").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(folders, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(folders, text="Browse folder…", command=self.browse_input).grid(row=0, column=2, padx=(8, 0), pady=4)
        ttk.Button(folders, text="Select images…", command=self.browse_files).grid(row=0, column=3, padx=(8, 0), pady=4)
        ttk.Label(folders, text="Output folder").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(folders, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(folders, text="Browse…", command=self.browse_output).grid(row=1, column=2, padx=(8, 0), pady=4)
        ttk.Label(folders, textvariable=self.selection_var).grid(row=2, column=1, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Label(folders, textvariable=self.selection_scan_var).grid(row=3, column=1, columnspan=3, sticky="w", pady=(2, 0))
        folders.columnconfigure(1, weight=1)

        settings = ttk.LabelFrame(outer, text="Conversion settings", padding=10)
        settings.pack(fill="x", pady=(0, 10))
        sizes_frame = ttk.Frame(settings)
        sizes_frame.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(sizes_frame, text="ICO sizes:").pack(side="left", padx=(0, 10))
        for size in AVAILABLE_ICON_SIZES:
            ttk.Checkbutton(sizes_frame, text=str(size), variable=self.size_vars[size]).pack(side="left", padx=4)
        ttk.Button(sizes_frame, text="All", command=self.select_all_sizes).pack(side="left", padx=(10, 2))
        ttk.Button(sizes_frame, text="Default", command=self.default_sizes).pack(side="left", padx=2)

        ttk.Label(settings, text="Image fitting").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Combobox(settings, textvariable=self.fit_var, state="readonly", values=(
            "Contain (transparent padding)", "Stretch to square", "Cover (center crop)"
        ), width=31).grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(settings, text="Presets the image shape behavior on a 256 × 256 canvas.").grid(row=1, column=2, sticky="w", padx=(12, 0), pady=4)

        ttk.Label(settings, text="Output naming").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Combobox(settings, textvariable=self.naming_var, state="readonly", values=(
            "Original filename", "Add _icon suffix", "Custom prefix"
        ), width=31).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(settings, text="Custom prefix").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Entry(settings, textvariable=self.prefix_var, width=34).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(settings, text="Used when output naming is set to Custom prefix.").grid(row=3, column=2, sticky="w", padx=(12, 0), pady=4)

        ttk.Label(settings, text="Name conflicts").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Combobox(settings, textvariable=self.conflict_var, state="readonly", values=(
            "Add numbered suffix", "Skip existing output", "Overwrite existing output"
        ), width=31).grid(row=4, column=1, sticky="w", pady=4)
        ttk.Label(settings, text="Default protects existing files by adding (2), (3), etc.").grid(row=4, column=2, sticky="w", padx=(12, 0), pady=4)
        settings.columnconfigure(2, weight=1)

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 10))
        self.start_button = ttk.Button(actions, text="Start conversion", command=self.start_conversion)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="Cancel conversion", command=self.cancel_conversion, state="disabled")
        self.cancel_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Manage selection…", command=self.manage_selected_images).pack(side="left", padx=(8, 0))
        self.scan_button = ttk.Button(actions, text="Scan source", command=self.scan_source)
        self.scan_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open outputs", command=lambda: self.open_folder(self.output_var.get())).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open logs", command=lambda: self.open_folder(str(LOG_DIR))).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Save settings", command=self.save_current_settings).pack(side="right")

        progress_frame = ttk.Frame(outer)
        progress_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(progress_frame, textvariable=self.status_var).pack(anchor="w")
        self.progress = ttk.Progressbar(progress_frame, maximum=100, variable=self.progress_var, mode="determinate")
        self.progress.pack(fill="x", pady=(6, 2))
        ttk.Label(progress_frame, textvariable=self.progress_detail_var).pack(anchor="e")
        ttk.Label(progress_frame, textvariable=self.counts_var).pack(anchor="w")

        log_frame = ttk.LabelFrame(outer, text="Activity", padding=8)
        log_frame.pack(fill="both", expand=True)
        text_bg, text_fg, select_bg = getattr(self, "text_colors", ("white", "black", "#316ac5"))
        self.log_text = tk.Text(
            log_frame, wrap="word", height=12, state="disabled", font=("Consolas", 9),
            background=text_bg, foreground=text_fg, insertbackground=text_fg,
            selectbackground=select_bg, borderwidth=1, relief="solid",
        )
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._append_log(f"IconMaker {VERSION} ready.")
        self._append_log("Supported formats: PNG, JPG, JPEG, WEBP, BMP, GIF, TIF, TIFF.")

    def _append_log(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def show_diagnostic_output(self):
        """Show recent logs and runtime details in a window inside IconMaker."""
        from tkinter import messagebox

        existing = getattr(self, "_diagnostic_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    return
            except Exception:
                pass

        tk, ttk = self.tk, self.ttk
        window = tk.Toplevel(self.root)
        self._diagnostic_window = window
        window.title(f"{APP_NAME} — Diagnostic Output")
        window.geometry("900x650")
        window.minsize(700, 450)

        toolbar = ttk.Frame(window, padding=(10, 10, 10, 6))
        toolbar.pack(fill="x")
        ttk.Label(
            toolbar,
            text="Runtime information, recent activity logs, and crash reports",
        ).pack(side="left")

        body = ttk.Frame(window, padding=(10, 0, 10, 10))
        body.pack(fill="both", expand=True)
        output = tk.Text(body, wrap="word", font=("Consolas", 9), state="disabled")
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=output.yview)
        output.configure(yscrollcommand=scrollbar.set)
        output.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def render_diagnostics():
            sections = [
                f"{APP_NAME} {VERSION} — DIAGNOSTIC OUTPUT",
                "=" * 76,
                f"Time: {datetime.now().isoformat(timespec='seconds')}",
                f"Platform: {sys.platform} ({os.name})",
                f"Python: {sys.version.split()[0]}",
                f"Standalone executable: {'Yes' if getattr(sys, 'frozen', False) else 'No'}",
                f"Application path: {BASE_DIR}",
                f"Executable: {sys.executable}",
                f"Logs folder: {LOG_DIR}",
                f"Crash reports folder: {CRASHLOG_DIR}",
                "",
                "RECENT ACTIVITY LOGS",
                "-" * 76,
            ]
            try:
                activity_files = sorted(
                    (item for item in LOG_DIR.glob("*.log") if item.is_file()),
                    key=lambda item: item.stat().st_mtime,
                    reverse=True,
                )[:5]
            except OSError as exc:
                activity_files = []
                sections.append(f"Could not list activity logs: {type(exc).__name__}: {exc}")

            if not activity_files:
                sections.append("No activity log files found yet.")
            for log_file in activity_files:
                sections.extend(["", f"--- {log_file.name} ---"])
                try:
                    content = log_file.read_text(encoding="utf-8", errors="replace")
                    if len(content) > 24000:
                        content = "[Earlier contents omitted; showing the end of this log.]\n\n" + content[-24000:]
                    sections.append(content.rstrip() or "[Log file is empty]")
                except OSError as exc:
                    sections.append(f"Could not read log: {type(exc).__name__}: {exc}")

            sections.extend(["", "RECENT CRASH REPORTS", "-" * 76])
            try:
                crash_files = sorted(
                    (item for item in CRASHLOG_DIR.glob("*.log") if item.is_file()),
                    key=lambda item: item.stat().st_mtime,
                    reverse=True,
                )[:5]
            except OSError as exc:
                crash_files = []
                sections.append(f"Could not list crash reports: {type(exc).__name__}: {exc}")

            if not crash_files:
                sections.append("No crash reports found.")
            for crash_file in crash_files:
                sections.extend(["", f"--- {crash_file.name} ---"])
                try:
                    content = crash_file.read_text(encoding="utf-8", errors="replace")
                    if len(content) > 24000:
                        content = "[Earlier contents omitted; showing the end of this report.]\n\n" + content[-24000:]
                    sections.append(content.rstrip() or "[Crash report is empty]")
                except OSError as exc:
                    sections.append(f"Could not read crash report: {type(exc).__name__}: {exc}")

            output.configure(state="normal")
            output.delete("1.0", "end")
            output.insert("1.0", "\n".join(sections) + "\n")
            output.configure(state="disabled")
            output.see("1.0")

        ttk.Button(toolbar, text="Refresh", command=render_diagnostics).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Open logs folder", command=lambda: self.open_folder(str(LOG_DIR))).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Open crash reports", command=lambda: self.open_folder(str(CRASHLOG_DIR))).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Close", command=window.destroy).pack(side="right", padx=(6, 0))
        render_diagnostics()

    def open_settings_file(self):
        from tkinter import messagebox
        self.save_current_settings(quiet=True)
        try:
            if os.name == "nt":
                os.startfile(str(SETTINGS_PATH))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(SETTINGS_PATH)])
            else:
                subprocess.Popen(["xdg-open", str(SETTINGS_PATH)])
        except Exception as exc:
            messagebox.showerror("Could not open settings file", f"Settings file: {SETTINGS_PATH}\n\n{exc}")

    def browse_input(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="Choose a folder containing images", initialdir=self.input_var.get() or str(BASE_DIR))
        if folder:
            self.input_var.set(folder)
            self.selected_files = []
            self.selection_var.set("Folder mode: supported images in folders and subfolders. Use Scan source to count them.")
            self.selection_scan_var.set("")
            self.save_current_settings(quiet=True)

    def browse_files(self):
        from tkinter import filedialog
        filetypes = [
            ("Supported images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff"),
            ("All files", "*.*"),
        ]
        files = filedialog.askopenfilenames(
            title="Select images to convert",
            initialdir=self.input_var.get() or str(BASE_DIR),
            filetypes=filetypes,
        )
        if files:
            # The main Select images action replaces the list; use Manage selection
            # → Add images to append files to an existing batch.
            self.selected_files = list(dict.fromkeys(str(Path(item).resolve()) for item in files))
            self.selection_var.set(f"Individual-file mode: {len(self.selected_files)} file(s) selected.")
            self.selection_scan_var.set(f"{len(self.selected_files)} selected file(s). Use Manage selection to preview or remove files.")

    def browse_output(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="Choose where converted icons will be saved", initialdir=self.output_var.get() or str(BASE_DIR))
        if folder:
            self.output_var.set(folder)
            self.save_current_settings(quiet=True)

    def select_all_sizes(self):
        for variable in self.size_vars.values():
            variable.set(True)

    def default_sizes(self):
        for size, variable in self.size_vars.items():
            variable.set(size in DEFAULT_ICON_SIZES)

    def current_options(self) -> ConversionOptions:
        selected_sizes = [size for size, variable in self.size_vars.items() if variable.get()]
        return ConversionOptions(
            input_dir=self.input_var.get().strip(),
            output_dir=self.output_var.get().strip(),
            icon_sizes=selected_sizes,
            fit_mode=self.fit_var.get(),
            naming_mode=self.naming_var.get(),
            custom_prefix=self.prefix_var.get(),
            conflict_policy=self.conflict_var.get(),
            source_files=list(self.selected_files) if self.selected_files else None,
        )

    def save_current_settings(self, quiet: bool = False):
        from tkinter import messagebox
        options = self.current_options()
        data = asdict(options)
        data["theme"] = self.theme_var.get()
        data["check_updates_on_startup"] = bool(self.check_updates_var.get())
        # File selections are temporary for the current session; don't persist
        # absolute paths to individual user files in settings.json.
        data.pop("source_files", None)
        try:
            save_settings(data)
            if not quiet:
                messagebox.showinfo("Settings saved", f"Your settings were saved to:\n{SETTINGS_PATH}")
        except OSError as exc:
            if not quiet:
                messagebox.showerror("Could not save settings", str(exc))
            self._append_log(f"[ERROR] Could not save settings: {exc}")

    def start_conversion(self):
        from tkinter import messagebox
        if self.busy:
            return
        options = self.current_options()
        if not options.input_dir and not options.source_files:
            messagebox.showerror("Missing input folder", "Choose an input folder or select image files first.")
            return
        if not options.output_dir:
            messagebox.showerror("Missing output folder", "Choose an output folder first.")
            return
        if not options.icon_sizes:
            messagebox.showerror("No icon sizes selected", "Select at least one ICO size.")
            return
        self.save_current_settings(quiet=True)
        self.busy = True
        self.cancel_event = threading.Event()
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal", text="Cancel conversion")
        self.scan_button.configure(state="disabled")
        self.progress.configure(maximum=100)
        self.progress_var.set(0)
        self.progress_detail_var.set("Preparing scan…")
        self.counts_var.set("Success: 0 | Skipped: 0 | Failed: 0")
        self._append_log("\n--- Starting conversion ---")

        def worker():
            try:
                run_conversion(options, lambda kind, message: self.events.put((kind, message)), self.cancel_event)
            except Exception:
                details = traceback.format_exc()
                try:
                    crash_path = write_crash_log("Unexpected GUI worker error", details)
                    self.events.put(("fatal", f"Unexpected error. Crash report: {crash_path}"))
                except Exception:
                    self.events.put(("fatal", details))
                fallback = ConversionSummary(failed=1, output_dir=options.output_dir)
                self.events.put(("done", json.dumps(asdict(fallback))))

        self.worker = threading.Thread(target=worker, daemon=True, name="IconMaker-conversion")
        self.worker.start()

    def cancel_conversion(self):
        if not self.busy:
            return
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled", text="Cancelling…")
        self.status_var.set("Cancellation requested — finishing the current image safely…")
        self._append_log("[INFO] Cancellation requested. The current image may finish before stopping.")

    def scan_source(self):
        if self.busy or self.scanning:
            return
        self.scanning = True
        self.scan_button.configure(state="disabled")
        self.selection_scan_var.set("Scanning source…")
        selected_files = list(self.selected_files)
        input_dir = self.input_var.get().strip()

        def worker():
            try:
                if selected_files:
                    count = sum(1 for item in selected_files if Path(item).suffix.lower() in SUPPORTED_EXTENSIONS and Path(item).is_file())
                    result = {"count": count, "mode": "selected", "error": ""}
                else:
                    count = len(discover_images(Path(input_dir).expanduser().resolve()))
                    result = {"count": count, "mode": "folder", "error": ""}
            except Exception as exc:
                result = {"count": 0, "mode": "selected" if selected_files else "folder", "error": f"{type(exc).__name__}: {exc}"}
            self.events.put(("scan_result", json.dumps(result)))

        self.scan_worker = threading.Thread(target=worker, daemon=True, name="IconMaker-scan")
        self.scan_worker.start()

    def manage_selected_images(self):
        """Manage the selected-image batch and preview an image's basic properties."""
        from tkinter import filedialog
        tk, ttk = self.tk, self.ttk
        window = tk.Toplevel(self.root)
        window.title("Manage selected images")
        window.geometry("760x470")
        window.minsize(620, 390)
        window.transient(self.root)
        container = ttk.Frame(window, padding=12)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="Selected images", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        body = ttk.Frame(container)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        listbox = tk.Listbox(left, selectmode="extended", exportselection=False, width=44)
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        right = ttk.Frame(body, padding=(14, 0, 0, 0), width=300)
        right.pack(side="right", fill="both")
        right.pack_propagate(False)
        preview_bg, preview_fg, select_bg = getattr(self, "text_colors", ("white", "black", "#316ac5"))
        preview = tk.Label(right, text="Select an image to preview", anchor="center", relief="groove", width=32, height=14, bg=preview_bg, fg=preview_fg)
        preview.pack(fill="both", expand=True)
        details = ttk.Label(right, text="No image selected", wraplength=280, justify="left")
        details.pack(fill="x", pady=(8, 0))

        def redraw():
            listbox.delete(0, "end")
            for raw in self.selected_files:
                listbox.insert("end", raw)
            self.selection_var.set(
                f"Individual-file mode: {len(self.selected_files)} file(s) selected." if self.selected_files
                else "Folder mode: supported images in the input folder and subfolders will be converted."
            )
            self.selection_scan_var.set(f"{len(self.selected_files)} selected file(s)." if self.selected_files else "No individual files selected.")

        def show_preview(_event=None):
            indices = listbox.curselection()
            if not indices:
                preview.configure(image="", text="Select an image to preview")
                preview.image = None
                details.configure(text="No image selected")
                return
            path = Path(self.selected_files[indices[0]])
            try:
                Image, ImageOps, _ = _image_modules()
                with Image.open(path) as source:
                    fmt = source.format or path.suffix.lstrip(".").upper()
                    width, height = source.size
                    transparency = source.mode in {"RGBA", "LA"} or "transparency" in source.info
                    oriented = ImageOps.exif_transpose(source).convert("RGBA")
                    oriented.thumbnail((300, 270), Image.Resampling.LANCZOS)
                    from PIL import ImageTk
                    photo = ImageTk.PhotoImage(oriented)
                preview.configure(image=photo, text="")
                preview.image = photo
                try:
                    byte_count = path.stat().st_size
                    file_size = f"{byte_count / 1024:.1f} KB" if byte_count < 1024 * 1024 else f"{byte_count / (1024 * 1024):.2f} MB"
                except OSError:
                    file_size = "Unknown"
                details.configure(text=f"{path.name}\nDimensions: {width} × {height}\nFormat: {fmt}\nTransparency: {'Yes' if transparency else 'No'}\nFile size: {file_size}")
            except Exception as exc:
                preview.configure(image="", text="Preview unavailable")
                preview.image = None
                details.configure(text=f"{path.name}\nCould not preview this image.\n{type(exc).__name__}: {exc}")

        def remove_selected():
            indices = sorted(listbox.curselection())
            if not indices:
                return
            target = min(indices[0], max(0, len(self.selected_files) - len(indices) - 1))
            remove = set(indices)
            self.selected_files = [item for i, item in enumerate(self.selected_files) if i not in remove]
            redraw()
            if self.selected_files:
                listbox.selection_set(target)
                show_preview()
            else:
                show_preview()

        def add_more():
            chosen = filedialog.askopenfilenames(
                parent=window, title="Add images", initialdir=self.input_var.get() or str(BASE_DIR),
                filetypes=[("Supported images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff"), ("All files", "*.*")],
            )
            known = {str(Path(item).resolve()).casefold() for item in self.selected_files}
            for item in chosen:
                resolved = str(Path(item).resolve())
                if resolved.casefold() not in known:
                    self.selected_files.append(resolved)
                    known.add(resolved.casefold())
            redraw()

        toolbar = ttk.Frame(container)
        toolbar.pack(fill="x", pady=(10, 0))
        ttk.Button(toolbar, text="Add images…", command=add_more).pack(side="left")
        ttk.Button(toolbar, text="Remove selected", command=remove_selected).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Clear selection", command=lambda: (setattr(self, "selected_files", []), redraw(), show_preview())).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="Done", command=window.destroy).pack(side="right")
        listbox.bind("<<ListboxSelect>>", show_preview)
        redraw()
        if self.selected_files:
            listbox.selection_set(0)
            show_preview()

    def check_for_updates(self, manual: bool = True):
        if self.update_check_running:
            if manual:
                self._append_log("[INFO] An update check is already running.")
            return
        self.update_check_running = True
        if manual:
            self.status_var.set("Checking GitHub for updates…")
            self._append_log("[INFO] Checking GitHub for the latest stable release…")

        def worker():
            result = {"manual": manual, "error": ""}
            try:
                release = fetch_latest_release(timeout=5.0)
                result.update(release)
                result["is_newer"] = version_key(release["version"]) > version_key(VERSION)
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}: {exc}"
            self.events.put(("update_result", json.dumps(result)))

        self.update_worker = threading.Thread(target=worker, daemon=True, name="IconMaker-update-check")
        self.update_worker.start()

    def show_about(self):
        tk, ttk = self.tk, self.ttk
        window = tk.Toplevel(self.root)
        window.title(f"About {APP_NAME}")
        window.resizable(False, False)
        window.transient(self.root)
        frame = ttk.Frame(window, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 18, "bold")).pack()
        ttk.Label(frame, text=f"Version {VERSION}").pack(pady=(2, 12))
        ttk.Label(frame, text="Batch image-to-ICO converter").pack()
        ttk.Label(frame, text="Made by The Pirate Dylan", font=("Segoe UI", 10, "bold")).pack(pady=(12, 4))
        ttk.Label(frame, text="Open-source software released under the MIT License").pack()
        ttk.Button(frame, text="Open GitHub repository", command=lambda: webbrowser.open(GITHUB_REPOSITORY)).pack(fill="x", pady=(16, 6))
        ttk.Button(frame, text="Report a bug", command=lambda: webbrowser.open(f"{GITHUB_REPOSITORY}/issues/new")).pack(fill="x", pady=4)
        ttk.Button(frame, text="Close", command=window.destroy).pack(pady=(10, 0))
        window.update_idletasks()
        window.geometry(f"{window.winfo_reqwidth()}x{window.winfo_reqheight()}")

    def poll_events(self):
        from tkinter import messagebox
        try:
            while True:
                kind, message = self.events.get_nowait()
                if kind == "log":
                    self._append_log(message)
                elif kind == "status":
                    self.status_var.set(message)
                elif kind == "progress":
                    try:
                        current, total = map(int, message.split("/"))
                        if total > 0:
                            self.progress.configure(maximum=total)
                            self.progress_var.set(current)
                    except ValueError:
                        pass
                elif kind == "progress_detail":
                    self.progress_detail_var.set(message)
                elif kind == "counts":
                    self.counts_var.set(message)
                elif kind == "scan_count":
                    self.selection_scan_var.set(f"{message} selected item(s) found in the conversion source.")
                elif kind == "scan_result":
                    self.scanning = False
                    self.scan_button.configure(state="normal" if not self.busy else "disabled")
                    data = json.loads(message)
                    if data.get("error"):
                        self.selection_scan_var.set("Source scan failed. See the Activity panel.")
                        self._append_log(f"[ERROR] Source scan failed: {data['error']}")
                        messagebox.showerror("Source scan failed", data["error"])
                    else:
                        count = int(data.get("count", 0))
                        mode = data.get("mode")
                        label = (f"{count} supported selected image(s) found." if mode == "selected"
                                 else f"{count} supported image(s) found in the folder and subfolders.")
                        self.selection_scan_var.set(label)
                        self._append_log(f"[INFO] Source scan found {count} supported image(s).")
                elif kind == "fatal":
                    self._append_log(f"[ERROR] {message}")
                    self.status_var.set("Conversion did not complete successfully.")
                elif kind == "done":
                    data = json.loads(message)
                    self.busy = False
                    self.start_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled", text="Cancel conversion")
                    self.scan_button.configure(state="normal")
                    total = int(data.get("total", 0))
                    completed = int(data.get("succeeded", 0)) + int(data.get("skipped", 0)) + int(data.get("failed", 0))
                    self.progress.configure(maximum=max(1, total))
                    if not data.get("cancelled") and total > 0:
                        self.progress_var.set(total)
                        self.progress_detail_var.set(f"{total} of {total} — 100%")
                    elif total == 0:
                        self.progress_var.set(0)
                        self.progress_detail_var.set("0 of 0 — 0%")
                    else:
                        self.progress_var.set(min(completed, max(1, total)))
                        pct = round(completed / total * 100) if total else 0
                        self.progress_detail_var.set(f"{completed} of {total} — {pct}% before cancellation")
                    self.counts_var.set(
                        f"Success: {data.get('succeeded', 0)} | Skipped: {data.get('skipped', 0)} | Failed: {data.get('failed', 0)}"
                    )
                    elapsed = float(data.get("elapsed_seconds", 0.0))
                    self._append_log("--- Conversion finished ---")
                    self._append_log(
                        f"Summary: {data.get('succeeded', 0)} successful, {data.get('skipped', 0)} skipped, "
                        f"{data.get('failed', 0)} failed, {elapsed:.2f} seconds."
                    )
                    self._append_log(f"Output folder: {data.get('output_dir', '')}")
                    if data.get("log_path"):
                        self._append_log(f"Activity log: {data['log_path']}")
                    if data.get("cancelled"):
                        remaining = max(0, total - completed)
                        self.status_var.set(f"Conversion cancelled. {remaining} file(s) were not processed.")
                        self.show_conversion_summary(data, result_state="cancelled")
                    elif data.get("failed", 0):
                        self.status_var.set("Conversion finished with errors. See the Activity panel and log.")
                        self.show_conversion_summary(data, result_state="errors")
                    elif total == 0:
                        self.status_var.set("Scan complete. No supported images were found.")
                        source_description = f"the {len(self.selected_files)} selected file(s)" if self.selected_files else self.input_var.get()
                        messagebox.showinfo("No images found", f"No supported images were found in:\n{source_description}")
                    else:
                        self.status_var.set("Conversion complete.")
                        self.show_conversion_summary(data, result_state="success")
                    if self.close_after_conversion:
                        self.save_current_settings(quiet=True)
                        self.root.after(50, self.root.destroy)
                        return
                elif kind == "update_result":
                    self.update_check_running = False
                    data = json.loads(message)
                    manual = bool(data.get("manual"))
                    if data.get("error"):
                        self._append_log(f"[WARNING] Update check could not complete: {data['error']}")
                        if manual:
                            if not self.busy:
                                self.status_var.set("Update check unavailable. IconMaker is still ready to use.")
                            messagebox.showwarning(
                                "Update check unavailable",
                                "IconMaker could not reach GitHub to check for updates.\n\n"
                                "Check your connection and try again later. The app will continue working normally.",
                            )
                    elif data.get("is_newer"):
                        if manual and not self.busy:
                            self.status_var.set(f"IconMaker {data['version']} is available.")
                        self._append_log(f"[INFO] IconMaker {data['version']} is available.")
                        if messagebox.askyesno(
                            "IconMaker update available",
                            f"IconMaker {data['version']} is available.\nCurrent version: {VERSION}\n\n"
                            "Open the GitHub release page to read the notes and download it?",
                        ):
                            webbrowser.open(data["url"])
                    else:
                        if manual and not self.busy:
                            self.status_var.set("Ready. IconMaker is up to date.")
                        self._append_log(f"[INFO] IconMaker is up to date (version {VERSION}).")
                        if manual:
                            messagebox.showinfo("No updates available", f"You're using the latest release of IconMaker ({VERSION}).")
        except queue.Empty:
            pass
        if not self.close_after_conversion:
            self.root.after(100, self.poll_events)

    def show_conversion_summary(self, data: dict, result_state: str = "success"):
        """Show conversion totals and direct links to the output folder and activity log."""
        tk, ttk = self.tk, self.ttk
        titles = {
            "success": "Conversion complete",
            "errors": "Conversion finished with errors",
            "cancelled": "Conversion cancelled",
        }
        window = tk.Toplevel(self.root)
        window.title(titles.get(result_state, "Conversion summary"))
        window.resizable(False, False)
        window.transient(self.root)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=titles.get(result_state, "Conversion summary"), font=("Segoe UI", 13, "bold")).pack(anchor="w")
        total = int(data.get("total", 0))
        completed = int(data.get("succeeded", 0)) + int(data.get("skipped", 0)) + int(data.get("failed", 0))
        remaining = max(0, total - completed) if result_state == "cancelled" else 0
        ttk.Label(frame, text=(
            f"Successful: {data.get('succeeded', 0)}\n"
            f"Skipped: {data.get('skipped', 0)}\n"
            f"Failed: {data.get('failed', 0)}\n"
            + (f"Cancelled / not processed: {remaining}\n" if result_state == "cancelled" else "")
            + f"Elapsed time: {float(data.get('elapsed_seconds', 0)):.2f} seconds"
        ), justify="left").pack(anchor="w", pady=(12, 10))
        ttk.Label(frame, text=f"Output: {data.get('output_dir') or '(unavailable)'}", wraplength=520, justify="left").pack(anchor="w", pady=(0, 6))
        if data.get("log_path"):
            ttk.Label(frame, text=f"Activity log: {data['log_path']}", wraplength=520, justify="left").pack(anchor="w", pady=(0, 10))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Open output folder", command=lambda: self.open_folder(str(data.get("output_dir") or OUTPUT_DIR))).pack(side="left")
        if data.get("log_path"):
            ttk.Button(buttons, text="Open activity log", command=lambda: self.open_file(str(data["log_path"]))).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side="right")
        window.update_idletasks()
        window.geometry(f"{window.winfo_reqwidth()}x{window.winfo_reqheight()}")
        window.grab_set()

    def open_file(self, path: str):
        file_path = Path(path).expanduser()
        try:
            if not file_path.is_file():
                raise FileNotFoundError(f"File does not exist: {file_path}")
            if os.name == "nt":
                os.startfile(str(file_path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(file_path)])
            else:
                subprocess.Popen(["xdg-open", str(file_path)])
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("Could not open file", f"File: {file_path}\n\n{exc}")

    def open_folder(self, path: str):
        folder = Path(path).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("Could not open folder", str(exc))

    def on_close(self):
        if self.busy:
            from tkinter import messagebox
            if not messagebox.askyesno(
                "Conversion running",
                "A conversion is in progress. Cancel after the current image finishes and close IconMaker?",
            ):
                return
            self.close_after_conversion = True
            self.cancel_conversion()
            return
        self.save_current_settings(quiet=True)
        self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} {VERSION}")
    parser.add_argument("--cli", action="store_true", help="Run the batch converter in the console instead of opening the GUI.")
    parser.add_argument("--self-test", action="store_true", help="Verify packaged runtime dependencies and exit.")
    parser.add_argument("--input-dir", help="Input directory (CLI mode)")
    parser.add_argument("--output-dir", help="Output directory (CLI mode)")
    parser.add_argument("--sizes", nargs="+", type=int, choices=AVAILABLE_ICON_SIZES, help="ICO sizes to generate (CLI mode)")
    parser.add_argument("--fit-mode", choices=("Contain (transparent padding)", "Stretch to square", "Cover (center crop)"), help="Image fitting mode (CLI mode)")
    parser.add_argument("--naming-mode", choices=("Original filename", "Add _icon suffix", "Custom prefix"), help="Output naming mode (CLI mode)")
    parser.add_argument("--conflict-policy", choices=("Add numbered suffix", "Skip existing output", "Overwrite existing output"), help="Collision policy (CLI mode)")
    args = parser.parse_args()
    create_folders()

    if args.self_test:
        test_root = None
        try:
            _image_modules()
            import tkinter as tk
            test_root = tk.Tk()
            test_root.withdraw()
            IconMakerGUI(test_root)
            test_root.update_idletasks()
            test_root.destroy()
            return 0
        except Exception:
            details = traceback.format_exc()
            try:
                if test_root is not None:
                    test_root.destroy()
            except Exception:
                pass
            try:
                write_crash_log("Packaged runtime/GUI self-test failed", details)
            except Exception:
                pass
            return 3

    if args.cli:
        return run_cli(args)

    try:
        import tkinter as tk
    except ImportError:
        if sys.stderr is not None:
            print("[ERROR] Tkinter is not available in this Python installation.", file=sys.stderr)
            print("Use --cli to run the batch converter without the graphical interface.", file=sys.stderr)
        return 4
    try:
        root = tk.Tk()
        IconMakerGUI(root)
        root.mainloop()
        return 0
    except Exception:
        details = traceback.format_exc()
        report_text = details
        try:
            crash_path = write_crash_log("Could not start the graphical interface", details)
            report_text = f"IconMaker could not start.\n\nCrash report saved to:\n{crash_path}\n\n{details}"
        except OSError as log_exc:
            report_text = f"IconMaker could not start, and the crash report could not be saved: {log_exc}\n\n{details}"
        # A PyInstaller --windowed build has no console for stderr. Use a dialog
        # so users always receive a visible explanation and crash-report path.
        try:
            import tkinter as tk
            from tkinter import messagebox
            alert_root = tk.Tk()
            alert_root.withdraw()
            messagebox.showerror(f"{APP_NAME} startup error", report_text, parent=alert_root)
            alert_root.destroy()
        except Exception:
            if sys.stderr is not None:
                print(report_text, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
