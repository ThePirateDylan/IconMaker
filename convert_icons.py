#!/usr/bin/env python3
"""IconMaker 1.3.0 - Windows ICO converter with GUI and batch support."""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import subprocess
import sys
import tempfile
import threading
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

APP_NAME = "IconMaker"
VERSION = "1.3.0"
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


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


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
    }
    try:
        if SETTINGS_PATH.is_file():
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                defaults.update(saved)
    except (OSError, json.JSONDecodeError) as exc:
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
        raise RuntimeError(
            "Pillow is not installed. Use the launcher's install option or run "
            "py -m pip install --upgrade Pillow."
        ) from exc
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


def run_conversion(options: ConversionOptions, emit: LogCallback | None = None) -> ConversionSummary:
    """Convert a folder's supported images, reporting each file independently."""
    def send(kind: str, message: str) -> None:
        if emit:
            emit(kind, message)

    summary = ConversionSummary(output_dir=options.output_dir)
    input_root = Path(options.input_dir).expanduser().resolve()
    output_root = Path(options.output_dir).expanduser().resolve()
    try:
        logger, log_path = setup_job_logger()
    except Exception as exc:
        summary.failed = 1
        send("fatal", f"Could not create the activity log: {type(exc).__name__}: {exc}")
        send("done", json.dumps(asdict(summary)))
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
        output_root.mkdir(parents=True, exist_ok=True)
        log(logging.INFO, "IconMaker %s conversion started", VERSION)
        log(logging.INFO, "Input: %s", "selected files" if options.source_files is not None else input_root)
        log(logging.INFO, "Output: %s", output_root)
        log(logging.INFO, "Found %d selected image/file(s)", len(image_items))
        if not image_items:
            log(logging.INFO, "No supported images were found. Supported extensions: %s", ", ".join(sorted(SUPPORTED_EXTENSIONS)))
            send("progress", "0/0")
            send("done", json.dumps(asdict(summary)))
            logger.handlers[0].flush()
            logger.handlers[0].close()
            logger.handlers.clear()
            return summary

        # Import once up front so a missing Pillow installation is reported once.
        _image_modules()
        reserved: set[Path] = set()
        for index, (source, relative_source) in enumerate(image_items, start=1):
            send("progress", f"{index}/{len(image_items)}")
            send("status", f"Converting {index} of {len(image_items)}: {relative_source}")
            if not source.is_file() or source.suffix.lower() not in SUPPORTED_EXTENSIONS:
                summary.skipped += 1
                log(logging.WARNING, "[SKIPPED] %s — missing file or unsupported extension", source)
                send("counts", f"Success: {summary.succeeded} | Skipped: {summary.skipped} | Failed: {summary.failed}")
                continue
            destination, action = choose_destination(output_root, relative_source, options, reserved)
            if action == "skip" or destination is None:
                summary.skipped += 1
                log(logging.WARNING, "[SKIPPED] %s — output already exists: %s", relative_source, output_root / relative_source.parent / f"{output_stem(relative_source, options)}.ico")
                continue
            try:
                _convert_one(source, destination, options.fit_mode, sorted(set(options.icon_sizes)))
                summary.succeeded += 1
                log(logging.INFO, "[SUCCESS] %s -> %s", relative_source, destination.relative_to(output_root))
            except Exception as exc:
                summary.failed += 1
                log(logging.ERROR, "[FAILED] %s — %s: %s", relative_source, type(exc).__name__, exc)
                logger.exception("Details for failed file %s", relative_source)
            send("counts", f"Success: {summary.succeeded} | Skipped: {summary.skipped} | Failed: {summary.failed}")

        log(logging.INFO, "Summary: total=%d, succeeded=%d, skipped=%d, failed=%d", summary.total, summary.succeeded, summary.skipped, summary.failed)
        log(logging.INFO, "Activity log: %s", log_path)
        send("done", json.dumps(asdict(summary)))
        return summary
    except Exception as exc:
        summary.failed += 1
        log(logging.ERROR, "[JOB FAILED] %s: %s", type(exc).__name__, exc)
        logger.exception("Conversion job could not complete")
        send("fatal", f"{type(exc).__name__}: {exc}")
        send("done", json.dumps(asdict(summary)))
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
        self.root.geometry("900x760")
        self.root.minsize(800, 650)
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.busy = False
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
        self.size_vars = {size: tk.BooleanVar(value=size in self.settings["icon_sizes"]) for size in AVAILABLE_ICON_SIZES}
        self.status_var = tk.StringVar(value="Ready. Choose a source folder and start converting.")
        self.counts_var = tk.StringVar(value="Success: 0 | Skipped: 0 | Failed: 0")
        self.progress_var = tk.DoubleVar(value=0)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.poll_events)

    def _build_ui(self):
        tk, ttk = self.tk, self.ttk

        # Keep diagnostic access inside the application; end users should not
        # need a console window or batch launcher to troubleshoot problems.
        menubar = tk.Menu(self.root)
        settings_menu = tk.Menu(menubar, tearoff=False)
        settings_menu.add_command(label="Diagnostic Output…", command=self.show_diagnostic_output)
        settings_menu.add_command(label="Open Logs Folder", command=lambda: self.open_folder(str(LOG_DIR)))
        settings_menu.add_command(label="Open Crash Reports Folder", command=lambda: self.open_folder(str(CRASHLOG_DIR)))
        settings_menu.add_separator()
        settings_menu.add_command(label="Open Settings File", command=self.open_settings_file)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        self.root.configure(menu=menubar)

        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        heading = ttk.Frame(outer)
        heading.pack(fill="x", pady=(0, 12))
        ttk.Label(heading, text="IconMaker", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(heading, text="Batch image-to-ICO converter · Version 1.3.0").pack(anchor="w", pady=(2, 0))

        folders = ttk.LabelFrame(outer, text="Folders", padding=10)
        folders.pack(fill="x", pady=(0, 10))
        ttk.Label(folders, text="Input folder").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(folders, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(folders, text="Browse folder…", command=self.browse_input).grid(row=0, column=2, padx=(8, 0), pady=4)
        ttk.Button(folders, text="Select images…", command=self.browse_files).grid(row=0, column=3, padx=(8, 0), pady=4)
        ttk.Label(folders, text="Output folder").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(folders, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(folders, text="Browse…", command=self.browse_output).grid(row=1, column=2, padx=(8, 0), pady=4)
        ttk.Label(folders, textvariable=self.selection_var, foreground="#666666").grid(row=2, column=1, columnspan=3, sticky="w", pady=(2, 0))
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
        ttk.Label(settings, text="Presets the image shape behavior on a 256 × 256 canvas.", foreground="#666666").grid(row=1, column=2, sticky="w", padx=(12, 0), pady=4)

        ttk.Label(settings, text="Output naming").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Combobox(settings, textvariable=self.naming_var, state="readonly", values=(
            "Original filename", "Add _icon suffix", "Custom prefix"
        ), width=31).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(settings, text="Custom prefix").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Entry(settings, textvariable=self.prefix_var, width=34).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(settings, text="Used when output naming is set to Custom prefix.", foreground="#666666").grid(row=3, column=2, sticky="w", padx=(12, 0), pady=4)

        ttk.Label(settings, text="Name conflicts").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Combobox(settings, textvariable=self.conflict_var, state="readonly", values=(
            "Add numbered suffix", "Skip existing output", "Overwrite existing output"
        ), width=31).grid(row=4, column=1, sticky="w", pady=4)
        ttk.Label(settings, text="Default protects existing files by adding (2), (3), etc.", foreground="#666666").grid(row=4, column=2, sticky="w", padx=(12, 0), pady=4)
        settings.columnconfigure(2, weight=1)

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 10))
        self.start_button = ttk.Button(actions, text="Start conversion", command=self.start_conversion)
        self.start_button.pack(side="left")
        ttk.Button(actions, text="Install / repair Pillow", command=self.install_pillow).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open outputs", command=lambda: self.open_folder(self.output_var.get())).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open logs", command=lambda: self.open_folder(str(LOG_DIR))).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Save settings", command=self.save_current_settings).pack(side="right")

        progress_frame = ttk.Frame(outer)
        progress_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(progress_frame, textvariable=self.status_var).pack(anchor="w")
        self.progress = ttk.Progressbar(progress_frame, maximum=100, variable=self.progress_var, mode="determinate")
        self.progress.pack(fill="x", pady=(6, 4))
        ttk.Label(progress_frame, textvariable=self.counts_var).pack(anchor="w")

        log_frame = ttk.LabelFrame(outer, text="Activity", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, wrap="word", height=12, state="disabled", font=("Consolas", 9))
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
            self.selection_var.set("Folder mode: supported images in the folder and subfolders will be converted.")
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
            self.selected_files = list(files)
            self.selection_var.set(f"Individual-file mode: {len(self.selected_files)} file(s) selected. Subfolders are not recreated for selected files.")

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
        if not options.input_dir:
            messagebox.showerror("Missing input folder", "Choose an input folder first.")
            return
        if not options.output_dir:
            messagebox.showerror("Missing output folder", "Choose an output folder first.")
            return
        if not options.icon_sizes:
            messagebox.showerror("No icon sizes selected", "Select at least one ICO size.")
            return
        self.save_current_settings(quiet=True)
        self.busy = True
        self.start_button.configure(state="disabled")
        self.progress.configure(maximum=1)
        self.progress_var.set(0)
        self.counts_var.set("Success: 0 | Skipped: 0 | Failed: 0")
        self._append_log("\n--- Starting conversion ---")

        def worker():
            try:
                run_conversion(options, lambda kind, message: self.events.put((kind, message)))
            except Exception:
                details = traceback.format_exc()
                try:
                    crash_path = write_crash_log("Unexpected GUI worker error", details)
                    self.events.put(("fatal", f"Unexpected error. Crash report: {crash_path}"))
                except Exception:
                    self.events.put(("fatal", details))
        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

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
                elif kind == "counts":
                    self.counts_var.set(message)
                elif kind == "fatal":
                    self._append_log(f"[ERROR] {message}")
                    self.status_var.set("Conversion did not complete successfully.")
                elif kind == "install_error":
                    self._append_log(f"[ERROR] {message}")
                    self.status_var.set("Pillow installation failed. See the Activity panel.")
                elif kind == "done":
                    data = json.loads(message)
                    self.busy = False
                    self.start_button.configure(state="normal")
                    self.progress_var.set(self.progress["maximum"])
                    self.counts_var.set(
                        f"Success: {data['succeeded']} | Skipped: {data['skipped']} | Failed: {data['failed']}"
                    )
                    self.status_var.set("Conversion complete.")
                    self._append_log("--- Conversion finished ---")
                    self._append_log(f"Summary: {data['succeeded']} successful, {data['skipped']} skipped, {data['failed']} failed.")
                    self._append_log(f"Output folder: {data['output_dir']}")
                    self._append_log(f"Activity log: {data['log_path']}")
                    if data["failed"]:
                        messagebox.showwarning("Conversion finished with errors", f"Successful: {data['succeeded']}\nSkipped: {data['skipped']}\nFailed: {data['failed']}\n\nSee the activity log for details:\n{data['log_path']}")
                    elif data["total"] == 0:
                        source_description = f"the {len(self.selected_files)} selected file(s)" if self.selected_files else f"{self.input_var.get()}"
                        messagebox.showinfo("No images found", f"No supported images were found in:\n{source_description}")
                    else:
                        messagebox.showinfo("Conversion complete", f"Successful: {data['succeeded']}\nSkipped: {data['skipped']}\nFailed: {data['failed']}\n\nOutput: {data['output_dir']}\nLog: {data['log_path']}")
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

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

    def install_pillow(self):
        from tkinter import messagebox
        if getattr(sys, "frozen", False):
            messagebox.showinfo("Standalone build", "Pillow is bundled in the standalone build. If conversion fails, download a fresh package from the official release page.")
            return
        if self.busy:
            messagebox.showwarning("Conversion running", "Wait for the current conversion to finish first.")
            return
        self._append_log("Checking / installing Pillow. This can take a little while…")
        def install_worker():
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "Pillow"],
                    capture_output=True, text=True, check=False,
                )
                output = (completed.stdout + "\n" + completed.stderr).strip()
                self.events.put(("log", output or "Pillow installer returned no output."))
                if completed.returncode == 0:
                    self.events.put(("status", "Pillow installed or already up to date."))
                    self.events.put(("log", "[SUCCESS] Pillow installation completed."))
                else:
                    self.events.put(("install_error", f"Pillow installation failed with exit code {completed.returncode}. See the output above."))
            except Exception as exc:
                self.events.put(("fatal", f"Could not run the Pillow installer: {exc}"))
        threading.Thread(target=install_worker, daemon=True).start()

    def on_close(self):
        if self.busy:
            from tkinter import messagebox
            if not messagebox.askyesno("Conversion running", "A conversion is in progress. Close IconMaker anyway? The current file may finish in the background."):
                return
        self.save_current_settings(quiet=True)
        self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} {VERSION}")
    parser.add_argument("--cli", action="store_true", help="Run the batch converter in the console instead of opening the GUI.")
    parser.add_argument("--input-dir", help="Input directory (CLI mode)")
    parser.add_argument("--output-dir", help="Output directory (CLI mode)")
    parser.add_argument("--sizes", nargs="+", type=int, choices=AVAILABLE_ICON_SIZES, help="ICO sizes to generate (CLI mode)")
    parser.add_argument("--fit-mode", choices=("Contain (transparent padding)", "Stretch to square", "Cover (center crop)"), help="Image fitting mode (CLI mode)")
    parser.add_argument("--naming-mode", choices=("Original filename", "Add _icon suffix", "Custom prefix"), help="Output naming mode (CLI mode)")
    parser.add_argument("--conflict-policy", choices=("Add numbered suffix", "Skip existing output", "Overwrite existing output"), help="Collision policy (CLI mode)")
    args = parser.parse_args()
    create_folders()

    if args.cli:
        return run_cli(args)

    try:
        import tkinter as tk
    except ImportError:
        print("[ERROR] Tkinter is not available in this Python installation.")
        print("Use --cli to run the batch converter without the graphical interface.")
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
            print(report_text, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
