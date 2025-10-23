import os, sys
from config import Wifi, Local_Paths,Colors
from util.utils import run

XML_TEMPLATE = """<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{password}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>
"""

def generate_wifi_xml(ssid, password, filepath): 
    xml_content = XML_TEMPLATE.format(ssid=ssid, password=password)
    with open(filepath, "w") as f:
        f.write(xml_content)
    print(Colors.green(f"\nGenerated Wi-Fi profile XML: {filepath}"))
    return filepath

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
                print(Colors.yellow(f"[WIFI] Connected to {ssid}"))
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
            print(Colors.yellow(f"[WIFI] profile not found: {xml_path}. Generating..."))
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