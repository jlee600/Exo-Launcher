import sys, platform, signal, webbrowser, threading, time
from config import Wifi, Jetson, Colors, Local_Paths, HTML
from util.html import start_static_server, start_api_server
from util.utils import write_dashboard_info
from util.ssh import ensure_master, close_master, periodic_sync, run_remote_controller, stop_remote_controller
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
    write_dashboard_info(Jetson.USER_SULLY, Wifi.SSID_CAREN)

    # 3. API server (Thread 1)
    api = start_api_server(run_remote_controller, stop_remote_controller, host="127.0.0.1", port=HTML.API_PORT)

    # 4. Static server (dashboard) (Thread 2)
    httpd = start_static_server(Local_Paths.ROOT, port = HTML.POLL_PORT)
    url = f"http://127.0.0.1:{HTML.POLL_PORT}/dashboard.html"
    print(Colors.yellow(f"[UI] Opening dashboard at {url}\n"))
    webbrowser.open(url)

    # Graceful shutdown closes control master
    def _cleanup(*_):
        print(Colors.yellow("\n[parse] Stopping sync..."))
        try:
            close_master(Jetson.USER_SULLY, Jetson.HOST_SULLY)
        finally:
            try:
                api.shutdown()
            except Exception:
                pass
            httpd.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # 5. Sync thread (Thread 3)
    sync_thread = threading.Thread(target=periodic_sync, args=(Jetson.USER_SULLY, Jetson.HOST_SULLY, Wifi.SSID_CAREN, 4), daemon=True)
    sync_thread.start()    

    # Main Thread
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _cleanup()

if __name__ == "__main__":
    main()