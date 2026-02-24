import logging
import sys
import os
from config import Colors, Local_Paths

class ColorFormatter(logging.Formatter):
    # Standard format: [Time] - [Level] - [Message]
    FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

    FORMATTERS = {
        logging.DEBUG: logging.Formatter(FORMAT),
        logging.INFO: logging.Formatter(f"{Colors.GREEN}{FORMAT}{Colors.RESET}"),
        logging.WARNING: logging.Formatter(f"{Colors.YELLOW}{FORMAT}{Colors.RESET}"),
        logging.ERROR: logging.Formatter(f"{Colors.RED}{FORMAT}{Colors.RESET}"),
        logging.CRITICAL: logging.Formatter(f"{Colors.RED}{FORMAT}{Colors.RESET}")
    }

    def format(self, record):
        formatter = self.FORMATTERS.get(record.levelno, self.FORMATTERS[logging.DEBUG])
        return formatter.format(record)

def setup_logger():
    logger = logging.getLogger("Exo-Launcher")
    logger.setLevel(logging.INFO)

    # Prevent duplicating logs if imported multiple times
    if not logger.handlers:
        # 1. Terminal Output (with colors)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColorFormatter())
        logger.addHandler(console_handler)

        # 2. File Output (clean plain text for debugging)
        os.makedirs(Local_Paths.DATA_DIR, exist_ok=True)
        log_file = os.path.join(Local_Paths.DATA_DIR, "launcher.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(file_handler)

    return logger

logger = setup_logger()