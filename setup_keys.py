import os
import subprocess
from util.profiles import load_store
from config import Colors

def check_or_generate_key():
    ssh_dir = os.path.expanduser("~/.ssh")
    ed25519_key = os.path.join(ssh_dir, "id_ed25519")
    rsa_key = os.path.join(ssh_dir, "id_rsa")

    # Check if a key already exists
    if os.path.exists(ed25519_key) or os.path.exists(rsa_key):
        print(Colors.green("[SSH] SSH key already exists on this laptop."))
        return True
    
    print(Colors.yellow("[SSH] No SSH key found. Generating a new ed25519 key..."))
    try:
        # Run ssh-keygen with no passphrase (-N "")
        subprocess.run([
            "ssh-keygen", "-t", "ed25519", "-N", "", "-f", ed25519_key
        ], check=True)
        print(Colors.green("[SSH] Successfully generated new SSH key."))
        return True
    except subprocess.CalledProcessError as e:
        print(Colors.red(f"[ERROR] Failed to generate SSH key: {e}"))
        return False

def setup_passwordless_login():
    print(Colors.yellow("\n=== Exo-Launcher SSH Key Setup ==="))
    if not check_or_generate_key():
        return
    
    store = load_store()
    profiles = store.get("profiles", {})
    
    if not profiles:
        print(Colors.red("[ERROR] No profiles found in data/jetson_profiles.json"))
        return
        
    print(Colors.yellow(f"\nFound {len(profiles)} saved profiles. Ready to copy keys."))
    print(Colors.red("Note: You will be prompted to enter the password for each Jetson one last time.\n"))
    
    for name, data in profiles.items():
        user = data.get("user")
        host = data.get("host")
        target = f"{user}@{host}"
        
        print(Colors.yellow(f"--- Setting up profile '{name}' ({target}) ---"))
        try:
            subprocess.run(["ssh-copy-id", target])
            print(Colors.green(f"[SUCCESS] Key copied to {name}!\n"))
        except FileNotFoundError:
            print(Colors.red("[ERROR] 'ssh-copy-id' command not found on this OS."))
        except Exception as e:
            print(Colors.red(f"[ERROR] Failed to copy key to {target}: {e}\n"))

    print(Colors.green("=== Setup Complete! ==="))
    print(Colors.green("You can now use the Exo-Launcher dashboard without typing passwords.\n"))

if __name__ == "__main__":
    setup_passwordless_login()