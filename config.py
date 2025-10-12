class Wifi:
    # Overground
    SSID_OVG = "overground_5G"
    PASS_OVG = ""
    IP_OVG = ""

    # Caren
    SSID_CAREN = "CAREN_5G"
    PASS_CAREN = ""
    IP_CAREN = ""

    # Network Devices
    DEV_MAC = "en0"
    DEV_WIN = "Wi-Fi"

class Jetson:
    # Sully
    USER_SULLY = "sully"
    HOST_SULLY = ""
    
    # default PORT
    PORT = 22

class Remote_Paths:
    COMPARE   = "/home/sully/hip-exo-controllers/readiness/config_compare.py"
    REQ_PATH  = "/home/sully/hip-exo-controllers/controllers/controller_configs.json"
    META_PATH = "/home/sully/hip-exo-controllers/readiness/meta.json"
    OUTPUT    = "/home/sully/hip-exo-controllers/readiness/comparison_output.txt"

class Colors:
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    RESET = "\033[0m"

    @staticmethod
    def green(msg): return f"{Colors.GREEN}{msg}{Colors.RESET}"
    @staticmethod
    def red(msg): return f"{Colors.RED}{msg}{Colors.RESET}"
    @staticmethod
    def yellow(msg): return f"\033[33m{msg}{Colors.RESET}"
