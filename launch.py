import os, subprocess, sys, socket, platform, json
from config import Wifi, Jetson, Remote_Paths, Colors
from generate_profile import generate_wifi_xml

def run(cmd):
    return subprocess.run(cmd, text=True, capture_output=True)

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
            print(Colors.yellow(f"Already connected to {ssid}"))
            return True
                
        for i in range(3):
            print(f"Wi-Fi attempt {i+1}/3...")
            run(["networksetup", "-setairportnetwork", Wifi.DEV_MAC, ssid, password])
            
            if validate_ip_mac(ssid, expected_ip):
                return True
    # windows
    elif operating == "Windows":
        if validate_ip_win(ssid, expected_ip):
            print(Colors.yellow(f"Already connected to {ssid}"))
            return True
        
        xml_dir = Wifi.XML_WIN
        filename = f"{ssid}.xml"
        xml_path = os.path.join(xml_dir, filename)
        if not os.path.exists(xml_path):
            print(Colors.red(f"Wi-Fi profile not found: {xml_path}. Generating..."))
            generate_wifi_xml(ssid, password, xml_path)
        run(["netsh", "wlan", "add", "profile", f"filename={xml_path}"])

        for i in range(3):
            print(f"Wi-Fi attempt {i+1}/3...")
            run(["netsh", "wlan", "connect", f"name={ssid}"])
            
            if validate_ip_win(ssid, expected_ip):
                print(Colors.yellow(f"Connected to {ssid}"))
                return True
    # linux   
    else: 
        print(Colors.red("Unsupported OS."))
        sys.exit(1)

    print(Colors.red(f"Failed to connect to {ssid} after few attempts."))
    return False

def ssh_reachable(host, port=22, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
    
def ssh_and_validate(user, host):
    cmp_result = None
    for i in range(3):
        print(f"SSH attempt {i+1}/3...")

        if not ssh_reachable(host):
            print(Colors.red("SSH not reachable, retrying"))
            continue

        print(Colors.yellow(f"SSH reachable, running compare on {user}"))
        cmp_result = run([
            "ssh", "-o", "StrictHostKeyChecking=accept-new", f"{user}@{host}",
            f"python3 {Remote_Paths.COMPARE} --req {Remote_Paths.REQ_PATH} --meta {Remote_Paths.META_PATH} --out {Remote_Paths.OUTPUT}"
        ])

        if cmp_result.returncode in (0, 2):
            pull = run([
                "ssh", "-o", "StrictHostKeyChecking=accept-new", f"{user}@{host}",
                f"cat {Remote_Paths.OUTPUT}"
            ])
            if pull.returncode == 0 and pull.stdout:
                try:
                    payload = json.loads(pull.stdout)
                    return True, payload  
                except json.JSONDecodeError as e:
                    print(Colors.red(f"[parse error] comparison output is not valid JSON: {e}"))
            else:
                print(Colors.red("Could not read comparison_output.json from Jetson, retrying"))
        else:
            print(Colors.red("Remote compare failed, retrying"))

    print(Colors.red("Failed to SSH into Jetson or run comparison after few attempts."))
    return False, None

def main():
    sys_os = platform.system()
    _os = "Mac" if sys_os == "Darwin" else sys_os
    print(Colors.green(f"Detected OS: {_os}\n"))

    # wifi
    print(Colors.green("Connecting to Wi-Fi: Overground"))
    if not connect_wifi(sys_os, Wifi.SSID_OVG, Wifi.PASS_OVG, Wifi.IP_OVG):
        print(Colors.green("Connecting to Wi-Fi: Caren_5G"))
        if not connect_wifi(sys_os, Wifi.SSID_CAREN, Wifi.PASS_CAREN, Wifi.IP_CAREN):
            sys.exit(1)

    # ssh
    print(Colors.green("\nConnecting to SULLY\n"))
    ok, payload = ssh_and_validate(Jetson.USER_SULLY, Jetson.HOST_SULLY)
    if not ok:
        sys.exit(1)

    summary = (payload or {}).get("summary", {})
    print(Colors.yellow("\n=== Local summary (from comparison_output.json) ==="))
    print(f"Ready: {summary.get('ready', 0)}  |  Blocked: {summary.get('blocked', 0)}  |  Unknown: {summary.get('unknown', 0)}")
    print(f"Timestamp: {summary.get('timestamp', 'n/a')}")
    # print("\nAll operations completed successfully.")

if __name__ == "__main__":
    main()