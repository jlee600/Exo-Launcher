import os, subprocess, sys, socket, platform, json, time, signal
from config import Wifi, Jetson, Remote_Paths, Local_Paths,Colors
from generate_profile import generate_wifi_xml

##############################
# Utils
##############################
def run(cmd):
    return subprocess.run(cmd, text=True, capture_output=True)

def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)

def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)

##############################
# WIFI Helpers
##############################
def validate_ip_mac(ssid, expected_ip):
    ip = run(["ipconfig", "getifaddr", Wifi.DEV_MAC]).stdout.strip()
    if ip:
        ip = ".".join(ip.split('.')[:-1]) 
        if ip == expected_ip:
            # print(Colors.yellow(f"Already Connected to {ssid}"))
            return True
    return False

def validate_ip_win(ssid, expected_ip):
    ip = run(["netsh", "interface", "ip", "show", "address", Wifi.DEV_WIN]).stdout
    ip = next((line.split(":", 1)[-1].strip() for line in ip.splitlines() if "IP Address" in line), None)
    if ip:
        ip = ".".join(ip.split('.')[:-1])
        if ip == expected_ip:
            # print(Colors.yellow(f"Already Connected to {ssid}"))
            return True
    return False

def connect_wifi(operating, ssid, password, expected_ip):
    # mac
    if operating == "Darwin":
        if validate_ip_mac(ssid, expected_ip):
            print(Colors.yellow(f"[WIFI] Already connected to {ssid}"))
            return True
                
        for i in range(3):
            print(f"[WIFI] attempt {i+1}/3...")
            run(["networksetup", "-setairportnetwork", Wifi.DEV_MAC, ssid, password])
            
            if validate_ip_mac(ssid, expected_ip):
                return True
    # windows
    elif operating == "Windows":
        if validate_ip_win(ssid, expected_ip):
            print(Colors.yellow(f"[WIFI] Already connected to {ssid}"))
            return True
        
        xml_dir = Local_Paths.ROOT
        filename = f"{ssid}.xml"
        xml_path = os.path.join(xml_dir, filename)
        if not os.path.exists(xml_path):
            print(Colors.red(f"[WIFI] profile not found: {xml_path}. Generating..."))
            generate_wifi_xml(ssid, password, xml_path)
        run(["netsh", "wlan", "add", "profile", f"filename={xml_path}"])

        for i in range(3):
            print(f"[WIFI] attempt {i+1}/3...")
            run(["netsh", "wlan", "connect", f"name={ssid}"])
            
            if validate_ip_win(ssid, expected_ip):
                print(Colors.yellow(f"[WIFI] Connected to {ssid}"))
                return True
    # linux   
    else: 
        print(Colors.red("[WIFI] Unsupported OS."))
        sys.exit(1)

    print(Colors.red(f"[WIFI] Failed to connect to {ssid} after few attempts."))
    return False

##############################
# SSH control master helpers
##############################
def ssh_reachable(host, port=22, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
    
def control_path(user, host, port=22):
    return os.path.expanduser(f"~/.ssh/cm-{user}@{host}:{port}")

def ensure_master(user, host, persist="60s"):
    cp = control_path(user, host)
    # Check if a master is already running
    chk = run(["ssh", "-O", "check", "-S", cp, f"{user}@{host}"])
    if chk.returncode == 0:
        return True
    # Start a new master in the background
    print(Colors.yellow("[SSH] Starting SSH control master..."))
    r = run([
        "ssh", "-M", "-N", "-f",
        "-o", f"ControlPath={cp}",
        "-o", f"ControlPersist={persist}",
        f"{user}@{host}",
    ])
    if r.returncode != 0:
        print(Colors.red(f"[SSH] Failed to start control master:\n{r.stderr}"))
        return False
    return True

def close_master(user, host):
    cp = control_path(user, host)
    run(["ssh", "-O", "exit", "-S", cp, f"{user}@{host}"])

##############################
# batch ssh calls (cmp + pull)
##############################
BEGIN_CMP  = "__BEGIN_CMP__"
BEGIN_META = "__BEGIN_META__"
def batch_compare_and_pull(user, host):
    """
    runs compare on Jetson, then prints both JSONs with markers.
    single SSH, single round-trip.
    """
    if not ssh_reachable(host):
        print(Colors.red("[SSH] SSH not reachable"))
        return None, None

    cp = control_path(user, host)
    remote_cmd = (
        f"python3 {Remote_Paths.COMPARE} "
        f"--req {Remote_Paths.REQ_PATH} "
        f"--meta {Remote_Paths.META_PATH} "
        f"--out {Remote_Paths.OUTPUT} >/dev/null 2>&1; "
        f"echo {BEGIN_CMP}; cat {Remote_Paths.OUTPUT}; "
        f"echo {BEGIN_META}; cat {Remote_Paths.META_PATH}"
    )

    r = run([
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-S", cp, f"{user}@{host}",
        remote_cmd
    ])

    if r.returncode != 0:
        print(Colors.red(f"[SSH] Remote batch failed:\n{r.stderr}"))
        return None, None

    out = r.stdout or ""
    try:
        _, after_cmp = out.split(BEGIN_CMP, 1)
        cmp_json_str, after_meta = after_cmp.split(BEGIN_META, 1)
        cmp_json_str = cmp_json_str.strip()
        meta_json_str = after_meta.strip()

        cmp_payload = json.loads(cmp_json_str)
        meta_payload = json.loads(meta_json_str)
        return cmp_payload, meta_payload
    except Exception as e:
        print(Colors.red(f"[parse] Failed to parse batch output: {e}"))
        return None, None

##############################
# Dashboard helper
##############################
def write_dashboard_info(user, ssid):
    dashboard_info = {
        "JetsonHost": f"{user}: {Jetson.HOST_SULLY}",
        "WiFi": f"{ssid}",  
    }
    write_json(os.path.join(Local_Paths.DATA_DIR, "dash_info.json"), dashboard_info)
    print("[INFO] Dashboard info written.")

##############################
# Sync loop
##############################
def periodic_sync(user, host, interval_sec=5):
    """
    every interval:
      - run compare remotely and fetch both JSONs in ONE ssh
      - write them locally for the dashboard
    """
    while True:
        cmp_payload, meta_payload = batch_compare_and_pull(user, host)
        if cmp_payload and meta_payload:
            write_json(Local_Paths.OUTPUT, cmp_payload)
            write_json(Local_Paths.META, meta_payload)
            print(Colors.green("[SYNC] Updated comparison_output.json and meta.json"))
        else:
            print(Colors.red("[SYNC] Update failed"))

        time.sleep(interval_sec)

##############################
# Main
##############################
def main():
    sys_os = platform.system()
    _os = "Mac" if sys_os == "Darwin" else sys_os
    print(Colors.green(f"Detected OS: {_os}\n"))

    # wifi
    print(Colors.green("[WIFI] Connecting to Wi-Fi: Overground"))
    if not connect_wifi(sys_os, Wifi.SSID_OVG, Wifi.PASS_OVG, Wifi.IP_OVG):
        print(Colors.green("[WIFI] Connecting to Wi-Fi: Caren_5G"))
        if not connect_wifi(sys_os, Wifi.SSID_CAREN, Wifi.PASS_CAREN, Wifi.IP_CAREN):
            sys.exit(1)

    # ssh
    print(Colors.green("\n[SSH] Connecting to SULLY\n"))
    if not ensure_master(Jetson.USER_SULLY, Jetson.HOST_SULLY, persist="5m"):
        sys.exit(1)

    # write dashboard info (wifi, jetson)
    write_dashboard_info(Jetson.USER_SULLY, Wifi.SSID_CAREN if validate_ip_win(Wifi.SSID_CAREN, Wifi.IP_CAREN) or validate_ip_mac(Wifi.SSID_CAREN, Wifi.IP_CAREN) else Wifi.SSID_OVG)

    # Graceful shutdown closes control master
    def _cleanup(*_):
        print(Colors.yellow("\n[parse] Stopping sync..."))
        close_master(Jetson.USER_SULLY, Jetson.HOST_SULLY)
        sys.exit(0)
    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # Loop: batch compare + pull every 5s
    periodic_sync(Jetson.USER_SULLY, Jetson.HOST_SULLY, interval_sec=5)
    
    # print("\nAll operations completed successfully.")

if __name__ == "__main__":
    main()