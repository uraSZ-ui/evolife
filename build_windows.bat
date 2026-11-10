@echo off
echo EvoLife .exe dosyasina donusturuluyor...
py -3.13 -m pip install --upgrade pip
py -3.13 -m pip install pygame pyinstaller
py -3.13 -m PyInstaller --noconfirm --clean --onefile --windowed --name EvoLife EvoLife_GitHub_Hazirlik.py
echo.
echo Islem tamamlandi! dist klasorunu kontrol edin.
pause