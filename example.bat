@echo off
echo === UAssetParser Example ===
echo.

set SAMPLE=D:\vr\ZMKJBS\Content\Blueprints\Global\Module\Character\BP_Character.uasset

echo Full tree export:
UAssetParser.exe "%SAMPLE%" -o output\BP_Character.json -v

echo.
echo Compact summary export:
UAssetParser.exe "%SAMPLE%" -o output\BP_Character_summary.json --summary-only --compact

echo.
echo Outputs:
echo   output\BP_Character.json
echo   output\BP_Character_summary.json
pause
