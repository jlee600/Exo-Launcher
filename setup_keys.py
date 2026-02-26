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
    logger.info("=== Exo-Launcher SSH Key Setup ===")
    if not check_or_generate_key():
        return
    
    store = load_store()
    profiles = store.get("profiles", {})
    
    if not profiles:
        logger.error("[ERROR] No profiles found in data/jetson_profiles.json")
        return
        
    profile_names = list(profiles.keys())
    print("\nAvailable Jetson profiles:")
    for idx, name in enumerate(profile_names):
        target = f"{profiles[name].get('user')}@{profiles[name].get('host')}"
        print(f"  {idx + 1}. {name} ({target})")
    print(f"  {len(profile_names) + 1}. All profiles")

    choice = input("\nEnter the number of the profile to setup (or 'q' to quit): ").strip()
    if choice.lower() == 'q':
        return

    selected_profiles = {}
    try:
        choice_idx = int(choice) - 1
        if 0 <= choice_idx < len(profile_names):
            selected_name = profile_names[choice_idx]
            selected_profiles[selected_name] = profiles[selected_name]
        elif choice_idx == len(profile_names):
            selected_profiles = profiles
        else:
            logger.error("[ERROR] Invalid selection.")
            return
    except ValueError:
        logger.error("[ERROR] Invalid input. Please enter a number.")
        return

    logger.warning("\nNote: You will be prompted to enter the password for the selected Jetson(s) one last time.\n")
    
    for name, data in selected_profiles.items():
        user = data.get("user")
        host = data.get("host")
        target = f"{user}@{host}"
        
        logger.info("--- Setting up profile '%s' (%s) ---", name, target)
        try:
            subprocess.run(["ssh-copy-id", target])
            logger.info("[SUCCESS] Key copied to %s!\n", name)
        except FileNotFoundError:
            logger.error("[ERROR] 'ssh-copy-id' command not found on this OS.")
        except Exception as e:
            logger.error("[ERROR] Failed to copy key to %s: %s\n", target, e)

    logger.info("=== Setup Complete! ===")
    logger.info("You can now use the Exo-Launcher dashboard without typing passwords.\n")

if __name__ == "__main__":
    setup_passwordless_login()