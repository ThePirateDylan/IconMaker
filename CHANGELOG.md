# Changelog

All notable IconMaker changes are documented here.

## [1.4.0] - Unreleased

### Added
- Cancellation control that stops between files and lets the current file finish safely.
- Detailed completed-file progress and percentage reporting.
- Elapsed-time reporting and clearer cancellation/failure summaries.
- Selected-image manager with image preview, dimensions, format, transparency, file size, and remove/clear controls.
- Source scanning to count supported images before conversion.
- System, Light, and Dark theme choices with saved preference.
- About window with version, GitHub links, issue reporting, and "Made by The Pirate Dylan" credit.
- Optional background check for newer stable GitHub releases at startup and manual update-check menu action.
- Custom IconMaker application icon used by the Windows executable and app window.
- Automated regression tests for conversion, cancellation, conflict handling, nested folders, errors, and numeric version comparison.
- A packaged executable dependency smoke test in the GitHub Actions workflow.

### Improved
- Removed the Install / repair Pillow button from the main GUI.
- Replaced the end-user Pillow installation prompt with a clear recovery message if a packaged dependency fails to load.
- Improved file selection management and source-count visibility.
- Updated documentation and the Windows release workflow to test before attaching an executable.

### Compatibility
- Retains the existing multi-size ICO output, image-fit modes, supported formats, naming modes, conflict policies, EXIF orientation handling, recursive folder behavior, settings persistence, logs, and diagnostic window.

## [1.3.0] - 2026-10-20

### Added
- Graphical interface for choosing input/output folders or individual image files, conversion sizes, image fitting, output naming, and conflict behavior.
- Persistent GUI settings saved to `settings.json`.
- Configurable ICO sizes: 16, 24, 32, 48, 64, 128, and 256 pixels.
- Three image-fit behaviors: contain on transparent canvas, stretch to square, and center-crop cover.
- Output naming modes for original names, `_icon` suffixes, and custom prefixes.
- Output-conflict handling with numbered suffix, skip, and overwrite options.
- Per-file progress and a final summary showing successful, skipped, and failed conversions.
- Per-file exception handling so a failed image does not stop the remaining batch.
- Atomic output writing to reduce the chance of leaving a partially written ICO file.
- A Settings menu with Diagnostic Output, Open Logs Folder, Open Crash Reports Folder, and Open Settings File options.
- Diagnostic Output window displaying runtime details and recent activity logs/crash reports without opening a command window.
- Visible error dialog and crash report path if GUI startup fails in a windowed executable.
- GitHub Actions workflow to build a one-file, windowed Windows executable and attach it to tagged GitHub Releases.

### Improved
- Duplicate output names no longer silently overwrite files under the default conflict policy.
- Activity logs include file-specific error messages and locations.
- Existing recursive folder processing, EXIF orientation correction, supported image formats, and multi-size ICO output are retained.
- End users can run the standalone `IconMaker.exe` without a `.bat` launcher or separate Python installation.

### Notes
- The Windows executable is built on a Windows runner by GitHub Actions; the source package does not contain a prebuilt `.exe`.
- Animated image formats are converted as still images; animation is not preserved.
