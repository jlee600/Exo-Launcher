import os, subprocess, json
from config import Jetson, Local_Paths

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

def write_dashboard_info(user, ssid):
    dashboard_info = {
        "JetsonHost": f"{user}: {Jetson.HOST_SULLY}",
        "WiFi": f"{ssid}",  
    }
    write_json(os.path.join(Local_Paths.DATA_DIR, "dash_info.json"), dashboard_info)
    print("[INFO] Dashboard info written.")
