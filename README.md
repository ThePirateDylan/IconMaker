# IconMaker

**A lightweight Windows utility for converting images into multi-size Windows icon (`.ico`) files.**

IconMaker simplifies icon creation by automatically resizing images, generating multiple icon sizes, processing batches of images, and organizing the converted files into an output directory.

## Features

- Batch conversion of supported images into `.ico` files.
- Supports PNG, JPG, JPEG, WEBP, BMP, GIF, TIF, and TIFF.
- Generates icon sizes of 16, 24, 32, 48, 64, 128, and 256 pixels.
- Fits images onto a transparent 256 × 256 canvas.
- Corrects image orientation using EXIF metadata when available.
- Recursively processes images inside subfolders.
- Preserves the input folder structure in the output directory.
- Displays conversion progress and a completion summary.
- Records activity logs and unexpected crashes.
- Includes a Windows batch launcher with a numbered menu.

## Download

Visit the repository's **Releases** page to download the latest packaged version of IconMaker.

1. Download the latest `IconMaker` ZIP package.
2. Extract the ZIP file to a folder on your computer.
3. Open the extracted folder.
4. Follow the installation instructions below.

**Note:** Download the packaged ZIP from Releases when available. GitHub's automatically generated source-code ZIP is not necessarily the same as the ready-to-use package.

## Requirements

- Windows
- Python 3
- The Pillow Python imaging library

The launcher includes an option to install or update Pillow. Python must already be installed and accessible through the `py` launcher.

## Installation

1. Download and install Python 3 from [python.org](https://www.python.org/downloads/), if it is not already installed.
2. Extract the IconMaker ZIP package.
3. Keep `convert_icons.py` and `Run_IconMaker.bat` in the same folder.
4. Double-click `Run_IconMaker.bat`.
5. If necessary, select the menu option to install or repair Pillow.

If Python is already installed but the launcher cannot find it, verify that the Python Launcher is available from Command Prompt.

## Usage

1. Run `Run_IconMaker.bat`.
2. Follow the numbered menu.
3. Place the images you want to convert in the `inputs` folder.
4. Select the conversion option.
5. Wait for the conversion to finish.
6. Find your converted `.ico` files in the `outputs` folder.

The program creates its working directories automatically when needed.

## Folder Structure

- `inputs/` — Source images to convert.
- `outputs/` — Converted ICO files.
- `logs/` — Timestamped activity logs.
- `crashlog/` — Reports from unexpected crashes.

The output directory preserves the relative folder structure of images found in the input directory.

## Supported Formats

| Format | Extension |
|---|---|
| PNG | `.png` |
| JPEG | `.jpg`, `.jpeg` |
| WebP | `.webp` |
| Bitmap | `.bmp` |
| GIF | `.gif` |
| TIFF | `.tif`, `.tiff` |

Animated images and unusual image formats may have limitations depending on how Pillow processes them.

## Troubleshooting

### Python is not recognized

Install Python 3 and make sure the Python Launcher (`py`) is available. Close and reopen the launcher after installing Python.

### Pillow is missing

Run the launcher and use its Pillow installation or repair option. If installation fails, open Command Prompt and run:

```bat
py -m pip install --upgrade Pillow
```

### No images are converted

Check that your supported image files are inside `inputs` or its subfolders. Review the activity logs for errors.

### Converted files are missing

Check the `outputs` folder and its subfolders. Review the activity logs to identify any files that failed to convert.

### Two images have the same filename

Files with identical names but different extensions may target the same output filename. Avoid duplicate basenames until filename conflict handling is improved.

## Project Status

IconMaker is under development. Current functionality may change as the project improves.

See [CHANGELOG.md](CHANGELOG.md) for version history and planned improvements.

## Coming Soon

Planned features include:

- Graphical user interface.
- Image previews before conversion.
- Drag-and-drop support.
- Configurable icon dimensions and image-fitting options.
- Improved duplicate-filename handling.
- Conversion history and retry options.
- A standalone Windows executable that does not require a separate Python installation.

These features are planned and are not necessarily available in the current release.

## License

IconMaker is distributed under the MIT License. See [LICENSE](LICENSE) for details.

## Contributing and Bug Reports

Bug reports, suggestions, and contributions are welcome. If you encounter an issue, include the steps to reproduce it and any relevant error messages. Remove personal information from logs before sharing them.