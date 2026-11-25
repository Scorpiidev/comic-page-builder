@echo off
rem Double-click to start Comic Hub on Windows.
rem The first run installs what the hub needs (PySide6, pypdfium2) if it's missing.
cd /d "%~dp0.."
set "PYTHONPATH=%CD%\core;%CD%\hub"
python -c "import PySide6, pypdfium2" 2>nul || (
    echo Installing the hub's packages, this happens once...
    python -m pip install -r hub\requirements.txt || (echo Couldn't install the hub's packages. & pause & exit /b 1)
)
where pythonw >nul 2>nul && (start "" pythonw -m comic_hub) || (python -m comic_hub)
