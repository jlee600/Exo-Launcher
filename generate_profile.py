import os
from config import Wifi, Colors 

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

def generate_wifi_xml(ssid, password, filename=None):
    out_dir = "../MASTER-DASH/wifi/"
    os.makedirs(out_dir, exist_ok=True)  
    if filename is None:
        filename = f"{ssid}.xml"
    filepath = os.path.join(out_dir, filename)

    xml_content = XML_TEMPLATE.format(ssid=ssid, password=password)
    with open(filepath, "w") as f:
        f.write(xml_content)
    print(Colors.green(f"\nGenerated Wi-Fi profile XML: {filepath}"))
    return filepath
