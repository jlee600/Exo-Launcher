import os
import subprocess
from util.profiles import load_store
from config import Colors
from util.log import logger

def check_or_generate_key():
    ssh_dir = os.path.expanduser("~/.ssh")
    ed25519_key = os.path.join(ssh_dir, "id_ed25519")
    rsa_key = os.path.join(ssh_dir, "id_rsa")

    # Check if a key already exists
    if os.path.exists(ed25519_key) or os.path.exists(rsa_key):
        logger.info("[SSH] SSH key already exists on this laptop.")
        return True
    
    logger.warning("[SSH] No SSH key found. Generating a new ed25519 key...")
    try:
        # Run ssh-keygen with no passphrase (-N "")
        subprocess.run([
            "ssh-keygen", "-t", "ed25519", "-N", "", "-f", ed25519_key
        ], check=True)
        logger.info("[SSH] Successfully generated new SSH key.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error("[ERROR] Failed to generate SSH key: %s", e)
        return False

def setup_passwordless_login():
    logger.info("\n=== Exo-Launcher SSH Key Setup ===")
    if not check_or_generate_key():
        return
    
    store = load_store()
    profiles = store.get("profiles", {})
    
    if not profiles:
        logger.error("[ERROR] No profiles found in data/jetson_profiles.json")
        return
        
    logger.info(f"\nFound {len(profiles)} saved profiles. Ready to copy keys.")
    logger.warning("Note: You will be prompted to enter the password for each Jetson one last time.\n")
    
    for name, data in profiles.items():
        user = data.get("user")
        host = data.get("host")
        target = f"{user}@{host}"
        
        logger.info(f"--- Setting up profile '{name}' ({target}) ---")
        try:
            subprocess.run(["ssh-copy-id", target])
            logger.info(f"[SUCCESS] Key copied to {name}!")
        except FileNotFoundError:
            logger.error("[ERROR] 'ssh-copy-id' command not found on this OS.")
        except Exception as e:
            logger.error("[ERROR] Failed to copy key to %s: %s", target, e)

    logger.info("=== Setup Complete! ===")
    logger.info("You can now use the Exo-Launcher dashboard without typing passwords.\n")

if __name__ == "__main__":
    setup_passwordless_login()