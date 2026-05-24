@echo off
echo === Building UAssetParser.exe ===
pip install pyinstaller -q
pyinstaller --onefile --name UAssetParser --distpath . --paths src src\main.py
if %ERRORLEVEL% EQU 0 (
    echo.
    echo === Build successful ===
    echo Output: UAssetParser.exe
) else (
    echo.
    echo === Build failed ===
    exit /b %ERRORLEVEL%
)
exit /b 0
