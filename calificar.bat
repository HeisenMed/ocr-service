@echo off
chcp 65001 >nul
setlocal

REM ============================================================
REM  Califica un PDF de hojas de respuestas y exporta a Excel.
REM
REM  Formas de usar:
REM    1) Doble clic  -> te pregunta el PDF y la version.
REM    2) Arrastrar un PDF sobre este .bat -> te pregunta la version.
REM    3) Linea de comandos:
REM         calificar.bat "imagenes_prue
ba\GRADO 9.pdf" AUTO
REM ============================================================

cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"

REM --- PDF: argumento 1, o lo que se arrastro, o se pregunta ---
set "PDF=%~1"
if "%PDF%"=="" (
    set /p "PDF=Ruta del PDF (ej: imagenes_prueba\GRADO 9.pdf): "
)

REM --- Version: argumento 2, o se pregunta (por defecto AUTO) ---
set "VER=%~2"
if "%VER%"=="" (
    set /p "VER=Version de la clave [A / B / C / AUTO] (Enter = AUTO): "
)
if "%VER%"=="" set "VER=AUTO"

echo.
echo ============================================================
echo  PDF     : %PDF%
echo  Version : %VER%
echo ============================================================
echo.

echo [1/2] Calificando...
"%PY%" src\procesar_lote.py "%PDF%" %VER%
if errorlevel 1 (
    echo.
    echo *** Error al calificar. Revisa la ruta del PDF y la version. ***
    pause
    exit /b 1
)

echo.
echo [2/2] Exportando a Excel...
"%PY%" src\exportar_excel.py
if errorlevel 1 (
    echo.
    echo *** Error al exportar a Excel. ***
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  LISTO. Resultados en la carpeta:  resultados\
echo  Excel: resultados\calificaciones_San_Luis.xlsx
echo ============================================================
echo.
pause
endlocal