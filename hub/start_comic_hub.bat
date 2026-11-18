@echo off
rem Double-click to start Comic Hub on Windows.
rem The first run installs PySide6 (the hub's only dependency) if it's missing.
cd /d "%~dp0.."
set "PYTHONPATH=%CD%\core;%CD%\hub"
python -c "import PySide6" 2>nul || (
    echo Installing PySide6, this happens once...
    python -m pip install -r hub\requirements.txt || (echo Couldn't install PySide6. & pause & exit /b 1)
)
where pythonw >nul 2>nul && (start "" pythonw -m comic_hub) || (python -m comic_hub)
