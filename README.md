# IconMaker

**A Windows utility for converting images into multi-size Windows icon (`.ico`) files.**

IconMaker 1.4.0 is a hobby project by ThePirateDylan. Features a branded header, source/destination controls, side-by-side conversion settings and live batch preview, clear primary actions, a progress panel, and activity log. It also provides folder and individual-image workflows, persistent settings, conversion progress and cancellation, image preview, selectable themes, diagnostic logs, and an optional GitHub update checker.

## Download for Windows

For normal use, download **`IconMaker.exe`** from the [latest GitHub Release](https://github.com/ThePirateDylan/IconMaker/releases/latest).
It is recommended to place it inside of a IconMaker folder.

- The standalone executable bundles Python and Pillow; no separate Python or Pillow installation is required.
- No `.bat` launcher or separate command window is required for normal use. `Run_IconMaker.bat` is an optional source/developer launcher; running the Python source directly requires Python and Pillow.
- The application checks for a newer stable GitHub release on startup by default. You can change this in **Settings → Check for updates on startup** or check manually from **Settings → Check for updates now…**.
- Update checking is done in the background. If GitHub is unavailable, IconMaker continues to work and reports a problem only when you start a manual check.
- Open **Settings → Diagnostic Output…** to view runtime details, recent activity logs, and crash reports inside IconMaker.

Run `IconMaker.exe` from a folder where your Windows account can write files, such as a folder under Documents or Downloads. IconMaker creates `inputs`, `outputs`, `logs`, `crashlog`, and `settings.json` beside the executable as needed. Avoid protected folders such as `C:\Program Files` unless you have configured writable data locations.

## Features

- Convert an entire folder (including subfolders) or select individual images.
- Preview selected images and inspect dimensions, format, transparency, and file size before conversion.
- Manage a selected-image batch by adding images, removing selected items, or clearing the selection.
- Scan the chosen source to count supported images before conversion.
- Supports PNG, JPG, JPEG, WEBP, BMP, GIF, TIF, and TIFF.
- Select ICO sizes: 16, 24, 32, 48, 64, 128, and 256 pixels.
- Choose how the image fits on the 256 × 256 canvas:
  - **Contain (transparent padding):** preserves proportions and centers the image on a transparent canvas.
  - **Stretch to square:** fills the square and may distort the source image.
  - **Cover (center crop):** fills the square while preserving proportions, cropping edges as needed.
- Choose output naming: original filename, `_icon` suffix, or custom prefix.
- Configure output-conflict behavior: add a numbered suffix, skip existing output, or overwrite existing output.
- Recursively processes subfolders and preserves their relative structure when converting a folder.
- Corrects image orientation using EXIF metadata when available.
- Shows the current file, completed-file count, percentage progress, and success/skip/failure totals.
- Cancels safely between files; a file already being converted is allowed to finish so its output is not left partially written.
- Continues after individual image errors and identifies failed files and error reasons.
- Shows the final totals and elapsed time, with direct access to output and diagnostic logs.
- Offers System, Light, and Dark themes.
- Includes an About window with version, GitHub links, and the credit **Made by ThePirateDylan**.
- Optional update checking against the latest stable GitHub release.
- Saves conversion and application preferences to `settings.json` between runs.

## Quick Start

1. Download `IconMaker.exe` from the [latest release](https://github.com/ThePirateDylan/IconMaker/releases/latest).
2. Save it in a writable folder.
3. Double-click `IconMaker.exe`.
4. Choose an input folder or select individual image files.
5. Optionally select **Scan source** to count supported images, or use **Manage selection…** to preview and remove individual files.
6. Choose an output folder and conversion settings.
7. Click **Start conversion**. Use **Cancel conversion** to stop after the current image finishes.
8. Review the final summary. Open **Settings → Diagnostic Output…** or the Logs folder for troubleshooting.

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

### Themes and updates

Open **Settings → Theme** to select System, Light, or Dark. The choice is saved between launches. **Settings → Check for updates on startup** controls automatic update checking; **Settings → Check for updates now…** performs a manual check. IconMaker only opens a GitHub release page after asking you; it does not silently replace the running executable.

## Diagnostic Output

Open **Settings → Diagnostic Output…** inside the application to view:

- Runtime and application information.
- The five most recent activity logs.
- The five most recent crash reports.
- Buttons to refresh the report or open the log folders.

You can also open **Settings → Open Logs Folder** or **Settings → Open Crash Reports Folder**. Logs may contain local file paths or filenames, so inspect them and remove personal information before sharing a report publicly.

## Folder and File Reference

- `convert_icons.py` — conversion engine, GUI, updater, and application logic.
- `Run_IconMaker.bat` — optional source/developer launcher (not needed by users of `IconMaker.exe`).
- `assets/iconmaker.ico` — Windows executable icon passed directly to PyInstaller and used as the Tk window icon.
- `assets/iconmaker.png` — PNG source for the in-app header and Tk window icon.
- `version_info.txt` — Windows file/product version metadata embedded by PyInstaller during the build.
- `tests/` — automated regression tests.
- `inputs/` — default input folder created at runtime if needed.
- `outputs/` — default output folder created at runtime if needed.
- `logs/` — timestamped activity logs.
- `crashlog/` — unexpected application startup/crash reports.
- `settings.json` — saved preferences, created at runtime.
- `CHANGELOG.md` — version history.
- `LICENSE` — MIT License.
- `.github/workflows/build-windows-exe.yml` — automated Windows executable build, test, and release workflow.

## Troubleshooting

### IconMaker won't start

If the GUI cannot start, the app attempts to save a crash report and display an error dialog. Open `crashlog` beside the executable or use **Settings → Diagnostic Output…** after starting the application. If the packaged executable reports a missing bundled dependency, download a fresh copy from the [latest release](https://github.com/ThePirateDylan/IconMaker/releases/latest); end users should not need to install Pillow separately.

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
