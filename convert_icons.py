
#!/usr/bin/env python3
"""
IconMaker 1.1.0
Batch image-to-Windows-ICO converter.
"""

from datetime import datetime
from pathlib import Path
import logging
import sys
import traceback

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:
    print("[ERROR] Pillow is not installed.")
    print("Run option 6 in Run_IconMaker.bat to install it.")
    sys.exit(3)


APP_NAME = "IconMaker"
VERSION = "1.1.0"

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "inputs"
OUTPUT_DIR = BASE_DIR / "outputs"
LOG_DIR = BASE_DIR / "logs"
CRASHLOG_DIR = BASE_DIR / "crashlog"

ICON_SIZES = [
    (16, 16),
    (24, 24),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
]

SUPPORTED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp",
    ".bmp", ".gif", ".tif", ".tiff",
}


def timestamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def create_folders():
    for folder in (
        INPUT_DIR,
        OUTPUT_DIR,
        LOG_DIR,
        CRASHLOG_DIR,
    ):
        folder.mkdir(parents=True, exist_ok=True)


def setup_logging():
    log_path = LOG_DIR / f"IconMaker_{timestamp()}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    return log_path


def write_crash_log(title, details):
    CRASHLOG_DIR.mkdir(parents=True, exist_ok=True)

    crash_path = (
        CRASHLOG_DIR /
        f"IconMaker_crash_{timestamp()}.log"
    )

    crash_path.write_text(
        f"{APP_NAME} {VERSION} - Crash Report\n"
        f"Time: {datetime.now().isoformat(timespec='seconds')}\n"
        f"Issue: {title}\n\n"
        f"{details}\n",
        encoding="utf-8",
    )

    return crash_path


def find_images():
    """Find supported images, including those in nested folders."""
    return sorted(
        path for path in INPUT_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def convert_image(source):
    """Convert one image while preserving its relative folder path."""
    relative_path = source.relative_to(INPUT_DIR)

    destination = (
        OUTPUT_DIR / relative_path
    ).with_suffix(".ico")

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGBA")

        # Fit the image into a transparent square without stretching
        # or cropping it.
        canvas_size = 256

        image.thumbnail(
            (canvas_size, canvas_size),
            Image.Resampling.LANCZOS,
        )

        canvas = Image.new(
            "RGBA",
            (canvas_size, canvas_size),
            (0, 0, 0, 0),
        )

        x = (canvas_size - image.width) // 2
        y = (canvas_size - image.height) // 2

        canvas.alpha_composite(image, (x, y))

        canvas.save(
            destination,
            format="ICO",
            sizes=ICON_SIZES,
        )

        logging.info(
            "[SUCCESS] %s -> %s",
            relative_path,
            destination.relative_to(BASE_DIR),
        )

        return True

    except (UnidentifiedImageError, OSError, ValueError):
        logging.exception("[FAILED] %s", relative_path)
        return False


def main():
    create_folders()
    log_path = setup_logging()

    print()
    print("=" * 54)
    print(f"  {APP_NAME} - Image-to-ICO Converter")
    print(f"  Version {VERSION}")
    print("=" * 54)
    print()

    images = find_images()

    if not images:
        logging.info("No supported images were found.")
        logging.info("Place images inside: %s", INPUT_DIR)
        logging.info("Supported: PNG, JPG, WEBP, BMP, GIF, TIFF")
        return 0

    total = len(images)
    succeeded = 0
    failed = 0

    logging.info("Found %d image(s). Starting conversion.", total)

    for index, source in enumerate(images, start=1):
        relative_path = source.relative_to(INPUT_DIR)

        print(f"\n[{index}/{total}] Processing: {relative_path}")

        if convert_image(source):
            succeeded += 1
        else:
            failed += 1

    print()
    print("=" * 54)
    print(f"  {APP_NAME} - RUN SUMMARY")
    print("=" * 54)
    print(f"  Total images : {total}")
    print(f"  Successful   : {succeeded}")
    print(f"  Failed       : {failed}")
    print(f"  Output       : {OUTPUT_DIR}")
    print(f"  Activity log : {log_path}")
    print(f"  Crash reports: {CRASHLOG_DIR}")

    if failed == 0:
        print()
        print("[ALL SUCCESS] Every image converted successfully!")
        logging.info("All %d image(s) converted successfully.", total)
        return 0

    print()
    print("[COMPLETED WITH ERRORS] Some images failed.")
    print("Check the logs folder for details.")
    logging.warning(
        "Finished with %d successes and %d failures.",
        succeeded,
        failed,
    )

    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())

    except KeyboardInterrupt:
        print("\n[INFO] Conversion cancelled by user.")
        sys.exit(130)

    except Exception:
        details = traceback.format_exc()

        try:
            crash_path = write_crash_log(
                "Unexpected application crash",
                details,
            )

            print(f"\n[CRASH] {APP_NAME} encountered an error.")
            print(f"[CRASH] Report: {crash_path}")

        except Exception:
            print("[CRASH] Could not write the crash report.")
            print(details)

        sys.exit(2)
