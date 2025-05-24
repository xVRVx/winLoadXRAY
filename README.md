# winLoadXRAY ВПН клиент для Windows
VPN приложение для vless tcp reality и голых конфигов ядра XRAY на Windows 10 и 11 (на других не тестировал).

По сути, это python обертка вокруг готового [ядра XRAY](https://github.com/XTLS/Xray-core) для win64.

**Умеет:**
- парсить подписку и запускать vless tcp reality и xhttp reality в mode:auto
- парсить голый vless://
- парсить чистый конфиг xray для клиента.

**Запускает:**
- socks5 прокси на 2080 порту
- системный прокси

## Внимание! Предустановлен роутинг для ру зоны, ру сайты в direct.

**Запустить:**
Скачайте последнюю версию ядра [XRAY](https://github.com/XTLS/Xray-core/releases) для Windows64 и положите рядом с файлом winLoadXRAY.py
```bash
cd C:\Xray-windows-64

python winLoadXRAY.py
```
**Сборка:**
```bash
pyinstaller --onefile --windowed --icon=icon.ico --add-binary "xray.exe;." --add-binary "geoip.dat;." --add-binary "geosite.dat;."  --add-data "ico.png;." --add-data "icon.ico;." --add-data "logo.png;." winLoadXRAY.py
```

**Последняя версия скомпилирована с:**

https://github.com/XTLS/Xray-core/releases/download/v25.5.16/Xray-windows-64.zip

**Скриншот:**

<img src="screen.png" alt="Скриншот" width="400"/>


