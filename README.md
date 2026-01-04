# winLoadXRAY ВПН клиент для Windows
VPN приложение для vless raw reality и голых конфигов ядра XRAY на Windows 10/11.

По сути это python обертка вокруг готового [ядра XRAY](https://github.com/XTLS/Xray-core) для win64, также используется [tun2proxy](https://github.com/tun2proxy/tun2proxy) для tun режима.

**Умеет:**
- парсить подписку и запускать vless raw reality, shadowsocks и xhttp reality в mode:auto
- парсить голый vless:// и ss://
- парсить чистый конфиг xray для клиента.

**Запускает:**
- socks5 прокси на 2080 порту
- системный прокси **(рекомендован для браузеров)**
- tun режим (от администратора)


## Внимание! Предустановлен роутинг для ru зоны, ru сайты в direct.

**Запуск**

Зависимости: pip install pillow requests pyinstaller

Скачайте последнюю версию ядра [XRAY](https://github.com/XTLS/Xray-core/releases) для Windows64 и положите в папку xray, скачайте последнюю вресию [tun2proxy](https://github.com/tun2proxy/tun2proxy) и положите в папку tun2proxy
```bash
cd C:\Xray-windows-64

python winLoadXRAY.py
```
**Сборка:**
```bash
pyinstaller --onefile --windowed --icon=img/icon.ico --add-binary "xray/xray.exe;xray" --add-binary "xray/geoip.dat;xray" --add-binary "xray/geosite.dat;xray" --add-data "img/ico.png;img" --add-data "img/ref.png;img" --add-data "img/icon.ico;img" --add-data "img/logo.png;img" --add-data "tun2proxy/tun2proxy-bin.exe;tun2proxy" --add-data "tun2proxy/tun2proxy.dll;tun2proxy" --add-data "tun2proxy/wintun.dll;tun2proxy" --add-data "tun2proxy/udpgw-server.exe;tun2proxy" --add-data "func;func" winLoadXRAY.py
```


**Последняя версия скомпилирована с:**

https://github.com/XTLS/Xray-core/releases/download/v25.10.15/Xray-windows-64.zip


https://github.com/tun2proxy/tun2proxy/releases/download/v0.7.16/tun2proxy-x86_64-pc-windows-msvc.zip

**Скриншот:**

<img src="img/screen.png" alt="Скриншот" width="400"/>


