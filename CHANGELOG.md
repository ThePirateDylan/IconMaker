# Changelog

All notable changes to IconMaker will be documented in this file.

This project follows a version-based release history. Features listed under upcoming releases are planned and may change before implementation.

## [1.1.0] - Current Development Version

### Added
- Automatic creation of the `inputs`, `outputs`, `logs`, and `crashlog` directories.
- Batch conversion of supported image files into Windows `.ico` files.
- Support for PNG, JPG, JPEG, WEBP, BMP, GIF, TIF, and TIFF images.
- Automatic resizing and fitting of images onto a transparent 256 × 256 canvas.
- Generation of ICO files containing multiple icon sizes: 16, 24, 32, 48, 64, 128, and 256 pixels.
- Automatic correction of image orientation using EXIF metadata when available.
- Recursive processing of images inside subdirectories.
- Preservation of the input folder structure in the output directory.
- Progress reporting and conversion summaries.
- Timestamped activity logs for tracking conversion results and errors.
- Separate crash reports for unexpected program failures.
- A Windows batch launcher with a numbered menu for conversion, folder access, dependency installation, system checks, and help.

### Improved
- Image processing and output organization.
- Error reporting and troubleshooting information.
- Windows command-line usability through the launcher menu.

### Requirements
- Windows.
- Python installed and accessible through the `py` launcher.
- Pillow, which the launcher can help install.

### Known Limitations
- Files with the same name but different extensions in the same folder may target the same output filename.
- A graphical user interface is not currently included.
- Python and Pillow must be available for the script to run.

---

## Upcoming

The following improvements are planned for future versions and are not yet guaranteed.

### Planned Features
- Graphical user interface for easier conversion management.
- Image previews before conversion.
- Drag-and-drop image and folder support.
- Configurable icon dimensions, padding, and image-fitting options.
- Improved handling of duplicate filenames and output conflicts.
- More detailed per-file error reporting and retry options.
- Conversion history and additional batch-processing controls.
- A standalone Windows executable that does not require a separate Python installation.
- Optional update notifications for new releases.

---

## Version History

- **1.1.0** — Development version featuring batch conversion, multi-size ICO generation, logging, crash reports, and a Windows launcher.