import os, subprocess, json, datetime
from config import Local_Paths, Colors
from util.log import logger

def run(cmd, *, check=False, **kwargs):
    return subprocess.run(cmd, text=True, capture_output=True, check=check, **kwargs)

def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)

def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)

def write_dashboard_info(user, ssid, host):
    dashboard_info = {
        "JetsonHost": f"{user}: {host}",
        "WiFi": f"{ssid}",  
        "LastUpdated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    write_json(os.path.join(Local_Paths.DATA_DIR, "dash_info.json"), dashboard_info)

def write_flexible_config(config):
    try:
        write_json(Local_Paths.FLEX, config)
        logger.info("\n[INFO] Flexible config written to %s\n", Local_Paths.FLEX)
        return True
    except Exception as e:
        logger.error("\n[ERROR] Failed to write flexible config: %s\n", e)
        return False