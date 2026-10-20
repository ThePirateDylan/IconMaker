# IconMaker

**A Windows utility for converting images into multi-size Windows icon (`.ico`) files.**

IconMaker 1.3.0 includes a graphical interface, persistent conversion settings, safer output naming, per-file error reporting, clear conversion summaries, and in-app diagnostic output.

## Download for Windows

For normal use, download **`IconMaker.exe`** from the [latest GitHub Release](https://github.com/ThePirateDylan/IconMaker/releases/latest).

- No Python installation is required when using the standalone executable.
- No `.bat` launcher or separate command window is required.
- Open the app's **Settings → Diagnostic Output…** menu to view runtime details, recent activity logs, and crash reports inside IconMaker.

Run `IconMaker.exe` from a folder where your Windows account can write files, such as a folder under Documents or Downloads. IconMaker creates `inputs`, `outputs`, `logs`, `crashlog`, and `settings.json` beside the executable as needed. Avoid placing it in a protected directory such as `C:\Program Files` unless you have configured writable data locations.

## Features

- Convert an entire folder (including subfolders) or select individual images.
- Supports PNG, JPG, JPEG, WEBP, BMP, GIF, TIF, and TIFF.
- Select which icon sizes to include: 16, 24, 32, 48, 64, 128, and 256 pixels.
- Choose how the image fits on the 256 × 256 canvas:
  - **Contain (transparent padding):** preserves proportions and centers the image on a transparent canvas.
  - **Stretch to square:** fills the square and may distort the source image.
  - **Cover (center crop):** fills the square while preserving proportions, cropping edges as needed.
- Choose output naming: original filename, `_icon` suffix, or custom prefix.
- Configure output-conflict behavior: add a numbered suffix, skip existing output, or overwrite existing output.
- Recursively processes subfolders and preserves their relative structure when converting a folder.
- Corrects image orientation using EXIF metadata when available.
- Continues after individual image errors and reports the affected file and error.
- Displays progress, success/skip/failure counts, and the activity-log location.
- Saves settings to `settings.json` between runs.
- Provides diagnostic information from the **Settings** menu without opening a console window.

## Quick Start

1. Download `IconMaker.exe` from the [latest release](https://github.com/ThePirateDylan/IconMaker/releases/latest).
2. Save it in a writable folder.
3. Double-click `IconMaker.exe`.
4. Choose an input folder or select individual image files.
5. Choose an output folder and preferred conversion settings.
6. Click **Start conversion**.
7. Review the conversion summary. For troubleshooting, open **Settings → Diagnostic Output…**.

## Settings

### Icon sizes

Select one or more sizes. The default includes 16, 24, 32, 48, 64, 128, and 256 pixels.

### Image fitting

- **Contain (transparent padding)** preserves the full image and avoids distortion.
- **Stretch to square** fills the canvas but can distort the image.
- **Cover (center crop)** fills the canvas and crops the outer edges as needed.

### Output naming

- **Original filename:** `logo.png` becomes `logo.ico`.
- **Add _icon suffix:** `logo.png` becomes `logo_icon.ico`.
- **Custom prefix:** a prefix such as `app_` makes `logo.png` become `app_logo.ico`.

### Name conflicts

- **Add numbered suffix:** avoids overwriting output files by using names such as `logo (2).ico` and `logo (3).ico`. This is the default.
- **Skip existing output:** preserves the existing output and marks the source as skipped.
- **Overwrite existing output:** explicitly replaces an existing output. Use this option carefully.

## Diagnostic Output

Open **Settings → Diagnostic Output…** inside the application to view:

- Runtime and application information.
- The five most recent activity logs.
- The five most recent crash reports.
- Buttons to refresh the report or open the log folders.

You can also open **Settings → Open Logs Folder** or **Settings → Open Crash Reports Folder**. Logs may contain local file paths or filenames, so inspect them and remove personal information before sharing a report publicly.

## Developer Build

The repository includes a GitHub Actions workflow at `.github/workflows/build-windows-exe.yml`. It builds a one-file, windowed Windows executable on a GitHub-hosted Windows runner.

- **Manual build:** open the repository's **Actions** tab, select **Build IconMaker Windows EXE**, and choose **Run workflow**. Download `IconMaker-Windows-EXE` from the completed workflow run's Artifacts section.
- **Release build:** push a version tag such as `v1.3.0`. The workflow builds `IconMaker.exe` and attaches it to the matching GitHub Release.

The packaged application is built with PyInstaller and Pillow. The application source and MIT license remain available in this repository.

## Folder and File Reference

- `convert_icons.py` — conversion engine and GUI source.
- `inputs/` — default input folder created at runtime if needed.
- `outputs/` — default output folder created at runtime if needed.
- `logs/` — timestamped activity logs.
- `crashlog/` — unexpected application startup/crash reports.
- `settings.json` — saved GUI options, created at runtime.
- `CHANGELOG.md` — version history.
- `LICENSE` — MIT License.
- `.github/workflows/build-windows-exe.yml` — automated Windows executable build/release workflow.

## Troubleshooting

### IconMaker won't start

If the GUI cannot start, the app attempts to save a crash report and display an error dialog. Open `crashlog` beside the executable or use **Settings → Diagnostic Output…** after starting the application.

### Some images fail

IconMaker continues the batch and identifies the failed file in the Activity panel and activity log. Corrupted images, unreadable files, or unsupported encodings may fail. Open **Settings → Diagnostic Output…** or the `logs` folder for details.

### Files are skipped

The **Skip existing output** policy intentionally skips a source when its target output already exists or conflicts with an earlier source. Choose **Add numbered suffix** if you want to retain both results.

### Animated images

Animated formats such as GIF are converted as still icons using the frame Pillow selects (normally the first frame). Animation is not preserved in `.ico` files.

## Project Status

IconMaker is a hobby project under active development. Bug reports, suggestions, and contributions are welcome. When reporting an issue, include steps to reproduce it and relevant diagnostic details. Remove personal information from logs before sharing them.

## License

IconMaker is distributed under the MIT License. See [LICENSE](LICENSE) for details.
