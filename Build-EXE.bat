@ECHO OFF
:: =============================================================================
:: Script:   Build-EXE.bat
:: Author:   Gabriel Clifton (built with Claude)
:: Created:  08-07-2026
:: Version:  1.0
::
:: Purpose:
::   Builds M365GUI as a ONE-FOLDER app (dist\M365GUI\) using PyInstaller.
::   Copy the whole dist\M365GUI folder to its destination and launch
::   M365GUI.exe inside it.
::
:: IMPORTANT - why one-folder and why the extract step:
::   Python 3.14 uses Tcl/Tk 9, which stores its script library INSIDE the DLL
::   as a virtual zip filesystem (//zipfs:/...). PyInstaller 6.21 does not copy
::   that library into the build, so the app crashes at startup with
::   "Tcl data directory _tcl_data not found". extract_tcl.py pulls the Tcl and
::   Tk libraries out of the zipfs into build_res\, and this script bundles them
::   with --add-data. One-folder (not one-file) also avoids the fragile
::   extract-to-%TEMP% behavior that failed intermittently.
::
:: Requirements:
::   Python 3.10+ on PATH and PyInstaller (py -m pip install pyinstaller).
:: =============================================================================
SETLOCAL ENABLEEXTENSIONS
CD /D "%~dp0"

py -m PyInstaller --version >NUL 2>&1
IF ERRORLEVEL 1 (
    ECHO PyInstaller is not installed. Run:  py -m pip install pyinstaller
    EXIT /B 1
)

ECHO Extracting Tcl/Tk libraries from zipfs...
py extract_tcl.py
IF ERRORLEVEL 1 (
    ECHO Failed to extract Tcl/Tk data. Build aborted.
    EXIT /B 1
)

py -m PyInstaller --onedir --windowed --name M365GUI ^
    --add-data "build_res\_tcl_data;_tcl_data" ^
    --add-data "build_res\_tk_data;_tk_data" ^
    M365GUI.py
IF ERRORLEVEL 1 (
    ECHO Build FAILED. Review the PyInstaller output above.
    EXIT /B 1
)

ECHO.
ECHO Build complete: dist\M365GUI\  (run M365GUI.exe inside it)
ECHO Copy the whole dist\M365GUI folder to its destination and launch
ECHO M365GUI.exe (keep the _internal folder next to it).
ENDLOCAL
