@echo off
chcp 65001 > nul
echo ====================================================
echo   Сборка winLoadXRAY для Windows 10/11 и Windows 7
echo ====================================================

:: 1. Сборка для Windows 10 / 11 (через основной Python)
echo.
echo [1/2] Компиляция версии для Windows 10/11...
python -m PyInstaller --clean --noconfirm --onefile --windowed ^
  --name "winLoadXRAY" ^
  --icon="img/icon.ico" ^
  --add-binary "xray/xray.exe;xray" ^
  --add-binary "xray/geoip.dat;xray" ^
  --add-binary "xray/geosite.dat;xray" ^
  --add-data "img/ico.png;img" ^
  --add-data "img/ref.png;img" ^
  --add-data "img/icon.ico;img" ^
  --add-data "img/logo.png;img" ^
  --add-data "func;func" ^
  winLoadXRAY.py

:: 2. Сборка для Windows 7 (через виртуальное окружение venv_win7 или py -3.8)
echo.
echo [2/2] Компиляция версии для Windows 7...
py -3.8 -m PyInstaller --clean --noconfirm --onefile --windowed ^
  --name "winLoadXRAY-win7" ^
  --icon="img/icon.ico" ^
  --add-binary "xray-win7/xray.exe;xray" ^
  --add-binary "xray/geoip.dat;xray" ^
  --add-binary "xray/geosite.dat;xray" ^
  --add-data "img/ico.png;img" ^
  --add-data "img/ref.png;img" ^
  --add-data "img/icon.ico;img" ^
  --add-data "img/logo.png;img" ^
  --add-data "func;func" ^
  winLoadXRAY.py

echo.
echo ====================================================
echo   Готово! Оба файла лежат в папке dist:
echo   - dist\winLoadXRAY.exe
echo   - dist\winLoadXRAY-win7.exe
echo ====================================================
pause