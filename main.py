import sys, platform, signal, webbrowser, time
from config import Colors, Wifi, Local_Paths, SERVER
from util.api import start_static_server, start_api_server
from util.login import on_login, close_active_master, set_active_ssid
from util.ssh import run_remote_controller, stop_remote_controller, run_flexible_controller
from util.wifi import connect_wifi
from util.log import logger

def main():
    sys_os = platform.system()
    _os = "Mac" if sys_os == "Darwin" else sys_os
    logger.info("Detected OS: %s", _os)

    # wifi
    ssid_used = None
    # logger.info("[WIFI] Connecting to Wi-Fi: Overground")
    # if connect_wifi(sys_os, Wifi.SSID_OVG, Wifi.PASS_OVG, Wifi.IP_OVG):
    #     ssid_used = Wifi.SSID_OVG
    # else:
    logger.info("[WIFI] Connecting to Wi-Fi: Caren_5G")
    if connect_wifi(sys_os, Wifi.SSID_CAREN, Wifi.PASS_CAREN, Wifi.IP_CAREN):
        ssid_used = Wifi.SSID_CAREN
    else:
        sys.exit(1)
    set_active_ssid(ssid_used)

    logger.info("[SSH] Waiting for Jetson login selection...")

    # API server (Thread 1)
    api = start_api_server(
        on_run=run_remote_controller,
        on_flex=run_flexible_controller,
        on_stop=stop_remote_controller,
        on_login=on_login,
        host="127.0.0.1",
        port=SERVER.API_PORT
    )

    # Static server (Thread 2)
    httpd = start_static_server(Local_Paths.ROOT, port=SERVER.POLL_PORT)
    login_url = f"http://127.0.0.1:{SERVER.POLL_PORT}/login.html"
    logger.info("[UI] Opening login at %s", login_url)
    webbrowser.open(login_url)

    # Graceful shutdown closes any active control master
    def _cleanup(*_):
        # TODO: reset meta.json, pkill watchdog
        logger.warning("\n[parse] Stopping sync ")
        try:
            close_active_master()
        finally:
            try:
                logger.warning("[API] Shutting down API server ")
                api.shutdown()
            except Exception:
                pass
            try:
                logger.warning("[UI] Shutting down static server ")
                httpd.shutdown()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # Main Thread loop
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _cleanup()

if __name__ == "__main__":
    main()