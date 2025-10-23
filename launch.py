from config import Wifi, Jetson, Colors, Local_Paths, HTML
import sys, platform, signal, webbrowser
from util.html import start_static_server
from util.utils import write_dashboard_info
from util.ssh import ensure_master, close_master, periodic_sync
from util.wifi import connect_wifi

def main():
    sys_os = platform.system()
    _os = "Mac" if sys_os == "Darwin" else sys_os
    print(Colors.green(f"Detected OS: {_os}\n"))

    # 1. connect to the wifi
    print(Colors.green("[WIFI] Connecting to Wi-Fi: Overground"))
    if not connect_wifi(sys_os, Wifi.SSID_OVG, Wifi.PASS_OVG, Wifi.IP_OVG):
        print(Colors.green("[WIFI] Connecting to Wi-Fi: Caren_5G"))
        if not connect_wifi(sys_os, Wifi.SSID_CAREN, Wifi.PASS_CAREN, Wifi.IP_CAREN):
            sys.exit(1)

    # 2. ssh into sully with control master
    print(Colors.green("\n[SSH] Connecting to SULLY\n"))
    if not ensure_master(Jetson.USER_SULLY, Jetson.HOST_SULLY, persist="5m"):
        sys.exit(1)

    # 3. write dashboard info (wifi, jetson)
    write_dashboard_info(Jetson.USER_SULLY, Wifi.SSID_CAREN)

    # 4. open dashboard in browser
    httpd = start_static_server(Local_Paths.ROOT, port = HTML.PORT)
    url = f"http://127.0.0.1:{HTML.PORT}/dashboard.html"
    print(Colors.green(f"[UI] Opening dashboard at {url}\n"))
    webbrowser.open(url)

    # Graceful shutdown closes control master
    def _cleanup(*_):
        print(Colors.yellow("\n[parse] Stopping sync..."))
        try:
            close_master(Jetson.USER_SULLY, Jetson.HOST_SULLY)
        finally:
            httpd.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # 5. Loop: batch compare + pull every 5s
    periodic_sync(Jetson.USER_SULLY, Jetson.HOST_SULLY, interval_sec=5)
    
    # print("\nAll operations completed successfully.")

if __name__ == "__main__":
    main()