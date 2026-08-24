@echo off
setlocal EnableExtensions

set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "VENV_DIR=%ROOT%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

rem Bill X-Ray intentionally uses CPython 3.11-3.13 for predictable Windows wheels.
rem Python 3.14 is not selected yet because some pinned native dependencies may
rem otherwise try to compile locally and require Visual Studio Build Tools.

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo Existing Bill X-Ray environment uses an incompatible Python version.
        echo Rebuilding it with a supported Python version...
        rmdir /s /q "%VENV_DIR%"
    )
)

if not exist "%VENV_PY%" (
    echo Creating Bill X-Ray's private Python environment...
    call :try_python 3.11
    if exist "%VENV_PY%" goto :venv_ready
    call :try_python 3.12
    if exist "%VENV_PY%" goto :venv_ready
    call :try_python 3.13
    if exist "%VENV_PY%" goto :venv_ready

    python -c "import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1
    if not errorlevel 1 (
        python -m venv "%VENV_DIR%"
        if not errorlevel 1 goto :venv_ready
    )

    echo.
    echo ERROR: Bill X-Ray needs Python 3.11, 3.12, or 3.13.
    echo Python 3.14 is currently skipped to avoid local compiler requirements.
    echo Install Python 3.11 from python.org, then run this file again.
    exit /b 10
)

:venv_ready
"%VENV_PY%" -c "import fastapi, uvicorn, jinja2, pydantic, pytest" >nul 2>&1
if errorlevel 1 (
    echo Installing Bill X-Ray requirements. This is normally needed only once...
    "%VENV_PY%" -m pip install --disable-pip-version-check --only-binary=:all: -r "%ROOT%\requirements.txt"
    if errorlevel 1 (
        echo.
        echo ERROR: Bill X-Ray requirements could not be installed as prebuilt packages.
        echo This is not a request to install Rust or Visual Studio Build Tools.
        echo Confirm Python 3.11-3.13 is installed, then run the launcher again.
        exit /b 11
    )
)

"%VENV_PY%" -c "import sys, fastapi, uvicorn, jinja2, pydantic; assert (3,11) <= sys.version_info[:2] <= (3,13)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Bill X-Ray environment verification failed.
    exit /b 12
)

exit /b 0

:try_python
py -%1 -c "import sys" >nul 2>&1
if errorlevel 1 exit /b 1
py -%1 -m venv "%VENV_DIR%"
exit /b %ERRORLEVEL%
