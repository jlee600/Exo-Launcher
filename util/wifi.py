import os, sys
from config import Wifi, Local_Paths, Colors
from util.utils import run
from util.log import logger

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
    logger.info("Generated Wi-Fi profile XML: %s", filepath)
    return filepath

def validate_ip_mac(ssid, expected_ip):
    ip = run(["ipconfig", "getifaddr", Wifi.DEV_MAC]).stdout.strip()
    if ip:
        ip = ".".join(ip.split('.')[:-1]) 
        if ip == expected_ip:
            return True
    return False

def validate_ip_win(ssid, expected_ip):
    ip = run(["netsh", "interface", "ip", "show", "address", Wifi.DEV_WIN]).stdout
    ip = next((line.split(":", 1)[-1].strip() for line in ip.splitlines() if "IP Address" in line), None)
    if ip:
        ip = ".".join(ip.split('.')[:-1])
        if ip == expected_ip:
            return True
    return False

def validate_ip_linux(ssid, expected_ip):
    ip = run(["ip", "-4", "addr", "show", Wifi.DEV_LINUX]).stdout
    ip = next((line.split()[1].split("/")[0] for line in ip.splitlines() if line.strip().startswith("inet ")), None)
    if ip:
        ip = ".".join(ip.split('.')[:-1])
        if ip == expected_ip:
            return True
    return False

def connect_wifi(operating, ssid, password, expected_ip):
    # mac
    if operating == "Darwin":
        if validate_ip_mac(ssid, expected_ip):
            logger.warning("[WIFI] Already connected to %s", ssid)
            return True
                
        for i in range(3):
            logger.info("[WIFI] attempt %d/3...", i+1)
            run(["networksetup", "-setairportnetwork", Wifi.DEV_MAC, ssid, password])
            
            if validate_ip_mac(ssid, expected_ip):
                logger.warning("[WIFI] Connected to %s", ssid)
                return True
    # windows
    elif operating == "Windows":
        if validate_ip_win(ssid, expected_ip):
            logger.warning("[WIFI] Already connected to %s", ssid)
            return True
        
        xml_dir = Local_Paths.ROOT
        filename = f"{ssid}.xml"
        xml_path = os.path.join(xml_dir, filename)
        if not os.path.exists(xml_path):
            logger.warning("[WIFI] profile not found: %s. Generating...", xml_path)
            generate_wifi_xml(ssid, password, xml_path)
        run(["netsh", "wlan", "add", "profile", f"filename={xml_path}"])

        for i in range(3):
            logger.info("[WIFI] attempt %d/3...", i+1)
            run(["netsh", "wlan", "connect", f"name={ssid}"])
            
            if validate_ip_win(ssid, expected_ip):
                logger.warning("[WIFI] Connected to %s", ssid)
                return True
    # linux 
    elif operating == "Linux":
        if validate_ip_linux(ssid, expected_ip):
            logger.warning("[WIFI] Already connected to %s", ssid)
            return True

        for i in range(3):
            logger.info("[WIFI] attempt %d/3...", i+1)
            run(["nmcli", "dev", "wifi", "connect", ssid, "password", password])

            if validate_ip_linux(ssid, expected_ip):
                logger.warning("[WIFI] Connected to %s", ssid)
                return True
    else: 
        logger.error("[WIFI] Unsupported OS.")
        sys.exit(1)

    logger.error("[WIFI] Failed to connect to %s after few attempts.", ssid)
    return False