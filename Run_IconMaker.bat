
@echo off
setlocal EnableExtensions
title IconMaker 1.4.0
cd /d "%~dp0"

:menu
cls
echo ====================================================
echo                 IconMaker 1.4.0
echo             Image-to-ICO Converter
echo             Made by The Pirate Dylan
echo ====================================================
echo.
echo   CONVERSION
echo     [1] Convert images
echo.
echo   FOLDERS
echo     [2] Open inputs
echo     [3] Open outputs
echo     [4] Open activity logs
echo     [5] Open crash reports
echo.
echo   MAINTENANCE
echo     [6] Install or repair Pillow
echo     [7] Check Python and Pillow
echo     [8] Quick-start instructions
echo.
echo     [0] Exit
echo.
set "choice="
set /p "choice=Enter a menu number: "

if "%choice%"=="1" goto convert
if "%choice%"=="2" goto inputs
if "%choice%"=="3" goto outputs
if "%choice%"=="4" goto logs
if "%choice%"=="5" goto crashlog
if "%choice%"=="6" goto install
if "%choice%"=="7" goto check
if "%choice%"=="8" goto instructions
if "%choice%"=="0" goto end

echo.
echo [ERROR] Invalid selection.
pause
goto menu

:convert
cls
echo ====================================================
echo                 IconMaker
echo ====================================================
echo.

if not exist "convert_icons.py" (
    echo [ERROR] convert_icons.py was not found.
    echo Keep both files in the same folder.
    pause
    goto menu
)

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Install Python 3 from https://www.python.org/downloads/
    pause
    goto menu
)

py "convert_icons.py"
set "result=%errorlevel%"

echo.
if "%result%"=="0" (
    echo [SUCCESS] Conversion finished successfully.
) else if "%result%"=="1" (
    echo [WARNING] Conversion finished with errors.
) else (
    echo [ERROR] IconMaker exited with code %result%.
)

pause
goto menu

:inputs
if not exist "inputs" mkdir "inputs"
start "" explorer "%~dp0inputs"
goto menu

:outputs
if not exist "outputs" mkdir "outputs"
start "" explorer "%~dp0outputs"
goto menu

:logs
if not exist "logs" mkdir "logs"
start "" explorer "%~dp0logs"
goto menu

:crashlog
if not exist "crashlog" mkdir "crashlog"
start "" explorer "%~dp0crashlog"
goto menu

:install
cls
echo ====================================================
echo          IconMaker - Pillow Installation
echo ====================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found.
    echo Install Python 3 before continuing.
    pause
    goto menu
)

py -m pip install --upgrade Pillow

if errorlevel 1 (
    echo.
    echo [ERROR] Pillow installation failed.
) else (
    echo.
    echo [SUCCESS] Pillow installation completed.
)

pause
goto menu

:check
cls
echo ====================================================
echo            IconMaker - System Check
echo ====================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [FAILED] Python launcher not found.
    echo Install Python 3 from python.org.
    pause
    goto menu
)

py --version
if errorlevel 1 (
    echo [FAILED] Python could not start.
    pause
    goto menu
)

py -c "import PIL; print('Pillow version:', PIL.__version__)"
if errorlevel 1 (
    echo [FAILED] Pillow is missing.
    echo Select option 6 to install it.
) else (
    echo.
    echo [SUCCESS] Python and Pillow are ready.
)

pause
goto menu

:instructions
cls
echo ====================================================
echo             IconMaker - Quick Start
echo ====================================================
echo.
echo 1. Keep both program files in the same folder.
echo 2. Select 7 to check Python and Pillow.
echo 3. Select 6 if Pillow needs installation.
echo 4. Put images inside the inputs folder.
echo 5. Select 1 to convert your images.
echo 6. Find icons inside outputs.
echo 7. Open logs or crash reports if needed.
echo.
echo Supported: PNG, JPG, JPEG, WEBP, BMP, GIF, TIFF
echo.
pause
goto menu

:end
echo.
echo Thanks for using IconMaker!
endlocal
exit /b 0
