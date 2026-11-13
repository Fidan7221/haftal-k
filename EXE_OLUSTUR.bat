@echo off
chcp 65001 >nul
title Tarladan Sofraya - .exe derleme
cd /d "%~dp0"

echo [1/3] Gerekli paketler kuruluyor...
python -m pip install -r requirements.txt pyinstaller waitress
if errorlevel 1 goto hata

echo.
echo [2/3] .exe derleniyor (3-5 dakika surebilir)...
python build_exe.py
if errorlevel 1 goto hata

echo.
echo [3/3] Bitti: dist\TarladanSofraya\TarladanSofraya.exe
explorer "dist\TarladanSofraya"
pause
exit /b 0

:hata
echo.
echo HATA OLDU. Bu pencerenin ekran goruntusunu Claude'a gonder.
pause
exit /b 1
