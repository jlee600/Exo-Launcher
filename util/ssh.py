import os, socket, json, time, datetime, re, shlex
from config import Remote_Paths, Colors, Local_Paths
from util.utils import run, write_json, write_dashboard_info, write_flexible_config

##############################
# SSH control master helpers
##############################
def ssh_reachable(host, port=22, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
    
def control_path(user, host, port=22):
    return os.path.expanduser(f"~/.ssh/cm-{user}@{host}:{port}")

def remote_path(user, relative):
    return f"/home/{user}/{relative.lstrip('/')}"

def ensure_master(user, host, persist="60s"):
    # Check if SSH is reachable
    if not ssh_reachable(host):
        print(Colors.red("[SSH] SSH not reachable"))
        return False
    cp = control_path(user, host)
    # Check if a master is already running
    chk = run(["ssh", "-O", "check", "-S", cp, f"{user}@{host}"])
    if chk.returncode == 0:
        return True
    # Start a new master in the background
    print(Colors.yellow("[SSH] Starting SSH control master..."))
    r = run([
       "ssh", "-M", "-N", "-f",
        "-o", f"ControlPath={cp}",
        "-o", f"ControlPersist={persist}", 
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=5",
        f"{user}@{host}"
    ])
    if r.returncode != 0:
        print(Colors.red(f"[SSH] Failed to start control master:\n{r.stderr}"))
        return False
    return True

def close_master(user, host):
    cp = control_path(user, host)
    run(["ssh", "-O", "exit", "-S", cp, f"{user}@{host}"])

def ssh_run(user, host, cmd):
    if not ensure_master(user, host):
        return None
    
    cp = control_path(user, host)
    return run([
        "ssh",
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={cp}",
        "-o", "StrictHostKeyChecking=accept-new",
        f"{user}@{host}",
        cmd
    ])

def ssh_bash(user, host, bash_cmd):
    return ssh_run(user, host, f"bash -lc {shlex.quote(bash_cmd)}")

##############################
# batch ssh calls (cmp + pull)
##############################
BEGIN_CMP  = "__BEGIN_CMP__"
BEGIN_META = "__BEGIN_META__"
def batch_compare_and_pull(user, host, ssid):
    """
    runs compare on Jetson, then prints both JSONs with markers.
    single SSH, single round-trip.
    """
    remote_cmd = (
        f"python3 {remote_path(user, Remote_Paths.COMPARE)} "
        f"--req {remote_path(user, Remote_Paths.REQ_PATH)} "
        f"--meta {remote_path(user, Remote_Paths.META_PATH)} "
        f"--out {remote_path(user, Remote_Paths.OUTPUT)} >/dev/null 2>&1; "
        f"echo {BEGIN_CMP}; cat {remote_path(user, Remote_Paths.OUTPUT)}; "
        f"echo {BEGIN_META}; cat {remote_path(user, Remote_Paths.META_PATH)}"
    )
    batch_compare = ssh_run(user, host, remote_cmd)
    if not batch_compare:
        print(Colors.red("[SSH] SSH Master failed to execute batch compare"))
        return None, None
    if batch_compare.returncode != 0:
        print(Colors.red(f"[SSH] Remote batch failed:\n{batch_compare.stderr}"))
        return None, None
    out = batch_compare.stdout or ""

    try:
        write_dashboard_info(user, ssid, host)
        _, after_cmp = out.split(BEGIN_CMP, 1)
        cmp_json_str, after_meta = after_cmp.split(BEGIN_META, 1)
        cmp_json_str = cmp_json_str.strip()
        meta_json_str = after_meta.strip()

        cmp_payload = json.loads(cmp_json_str)
        meta_payload = json.loads(meta_json_str)
        return cmp_payload, meta_payload
    except Exception as e:
        print(Colors.red(f"[SSH] Failed to parse batch output: {e}"))
        return None, None
    
##############################
# Sync loop
##############################
def periodic_sync(user, host, ssid, interval_sec=3):
    """
    every interval:
      - run compare remotely and fetch both JSONs in ONE ssh
      - write them locally for the dashboard
    """
    # 1. kill watchdog and connection hub just in case
    remote_cmd = f"sudo pkill -15 -f connection_hub.py"
    kill = ssh_run(user, host, remote_cmd)
    if not kill:
        print(Colors.red("[SSH] SSH Master failed to execute connection hub kill"))
        return (False, "SSH Master failed to execute connection hub kill")
    if kill.returncode != 0:        
        print(Colors.red(f"[SSH] Failed to stop connection hub:\n{kill.stderr}"))
        return (False, f"Failed to stop connection hub: {kill.stderr.strip() or kill.stdout.strip()}")
    print(Colors.green(f"[SSH] Stopped existing connection hub process (if any)"))
    
    remote_cmd = "sudo pkill -15 -f setup_watchdog.py"
    pkill = ssh_run(user, host, remote_cmd)
    if not pkill:
        print(Colors.red("[SSH] SSH Master failed to execute watchdog kill"))
        return (False, "SSH Master failed to execute watchdog kill")
    if pkill.returncode != 0:
        print(Colors.red(f"[SSH] Failed to kill watchdog process:\n{pkill.stderr}"))
        return (False, f"Failed to kill watchdog process: {pkill.stderr.strip() or pkill.stdout.strip()}")
    print(Colors.green(f"[SSH] Stopped existing watchdog process (if any)"))

    # 2. remote call setup_devices.sh
    path = remote_path(user, Remote_Paths.SETUP_DEVICES)
    print(Colors.yellow(f"[SYNC] Setting up devices with {path}"))
    remote_cmd = f"sudo -n {shlex.quote(path)}"
    setup_devices = ssh_run(user, host, remote_cmd)
    if not setup_devices:
        print(Colors.red("[SSH] SSH Master failed to execute device setup"))
        return
    if setup_devices.returncode != 0:
        print(Colors.red(f"[SYNC] Device setup failed:\n{setup_devices.stderr}"))
    else:
        print(Colors.green(f"[SYNC] Device setup successful"))
    
    # 3. periodic compare + pull
    while True:
        cmp_payload, meta_payload = batch_compare_and_pull(user, host, ssid)
        curr = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if cmp_payload and meta_payload:
            write_json(Local_Paths.OUTPUT, cmp_payload)
            write_json(Local_Paths.META, meta_payload)
            
            print(f"[SYNC {curr}] Updated successfully")
        else:
            print(Colors.red(f"[SYNC {curr}] Update failed"))

        time.sleep(interval_sec)

##############################
# Launch controller remotely
###############################
SAFE_NAME_RE = re.compile(r'^[A-Za-z0-9_\-\.]+$')

def ready_locally(name):
    if not SAFE_NAME_RE.match(name):
        return False
    try:
        with open(Local_Paths.OUTPUT, "r") as f:
            cmp = json.load(f)
        controllers = cmp.get("controllers", {})
        entry = controllers.get(name) or controllers.get(f"{name}.py")
        return bool(entry and entry.get("status") == 1)
    except Exception:
        return False

def run_remote_controller(name, user, host):
    """
    Runs the named controller via the SSH control master.
    Returns (ok: bool, message: str).
    """
    normalized = name if name.endswith(".py") else f"{name}.py"
    if not ready_locally(normalized):
        return (False, f"Unknown controller: {normalized}")
    
    # 1. remote kill setup_watchdog.py
    remote_cmd = "sudo pkill -15 -f setup_watchdog.py"
    pkill = ssh_run(user, host, remote_cmd)
    if not pkill:
        print(Colors.red("[SSH] SSH Master failed to execute watchdog kill"))
        return (False, "SSH Master failed to execute watchdog kill")
    if pkill.returncode != 0:
        print(Colors.red(f"[SSH] Failed to kill watchdog process:\n{pkill.stderr}"))
        return (False, f"Failed to kill watchdog process: {pkill.stderr.strip() or pkill.stdout.strip()}")
    print(Colors.green(f"[SSH] Stopped existing watchdog process (if any)"))

    # 2. Run the controller
    remote_cmd = (
        "source ~/miniconda3/etc/profile.d/conda.sh && "
        f"conda activate /home/{user}/miniconda3/envs/{user} && "
        f"cd {shlex.quote(remote_path(user, Remote_Paths.CONTROLLERS))} && "
        f"/home/{user}/miniconda3/envs/{user}/bin/python {shlex.quote(normalized)}"
    )
    print(Colors.yellow(f"[SSH] Running {name} on Jetson..."))
    ctrl = ssh_run(user, host, remote_cmd)
    if not ctrl:
        print(Colors.red("[SSH] SSH Master failed to execute controller run"))
        return (False, "SSH Master failed to execute controller run")
    if ctrl.returncode != 0:
        print(Colors.red(f"[SSH] Remote run failed:\n{ctrl.stderr}"))
        return (False, f"Failed to run remote controller: {ctrl.stderr.strip() or ctrl.stdout.strip()}")
    print(Colors.green(f"[SSH] Flexible controller started successfully"))
    
    # 3. remote call devices.sh    
    device = remote_path(user, Remote_Paths.DEVICES)
    remote_cmd = f"sudo -n {shlex.quote(device)}"
    print(Colors.yellow(f"[SYNC] Setting up devices with {device}"))
    devices = ssh_bash(user, host, remote_cmd)  
    if not devices:
        print(Colors.red("[SSH] SSH Master failed to execute device setup"))
        return (False, "SSH Master failed to execute device setup")
    if devices.returncode != 0:
        print(Colors.red(f"[SYNC] Device setup failed:\n{devices.stderr}"))
    else:
        print(Colors.green(f"[SYNC] Device setup successful"))

    return (True, "Remote controller started successfully")

def run_flexible_controller(name, config, user, host):
    """
    Writes the provided config JSON locally and to the Jetson, then runs
    <name>.py remotely via SSH.

    Steps:
      1. Save config to local data/flexible_config.json
      2. Copy it to Jetson: ../hip-exo-controllers/readiness/flexible_config.json
      3. Run the controller on Jetson
    """
    local_path = Local_Paths.FLEX
    remote = remote_path(user, Remote_Paths.FLEX_CONFIG)
    
    # 1. Write locally
    if not write_flexible_config(config):
        return (False, "Failed to write local flexible config")

    # 2. Ensure SSH master
    if not ensure_master(user, host, persist="5m"):
        return (False, "SSH control master not available")

    # 3. Copy to Jetson
    cp = control_path(user, host)
    copy = run([
        "scp",
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={cp}",
        "-o", "StrictHostKeyChecking=accept-new",
        local_path,
        f"{user}@{host}:{remote}",
    ])
    if not copy:
        print(Colors.red("[SSH] SSH Master failed to execute SCP"))
        return (False, "SSH Master failed to execute SCP")
    if copy.returncode != 0:
        print(Colors.red(f"[SSH] SCP failed:\n{copy.stderr}"))
        return (False, f"Failed to copy config to Jetson: {copy.stderr.strip() or copy.stdout.strip()}")
    print(Colors.green(f"[SSH] Copied flexible config to Jetson: {remote}"))

    # 4. Stop any existing watchdog
    remote_cmd = "sudo pkill -15 -f setup_watchdog.py"
    pkill = ssh_run(user, host, remote_cmd)
    if not pkill:
        print(Colors.red("[SSH] SSH Master failed to execute watchdog kill"))
        return (False, "SSH Master failed to execute watchdog kill")
    if pkill.returncode != 0:
        print(Colors.red(f"[SSH] Failed to kill watchdog process:\n{pkill.stderr}"))
        return (False, f"Failed to kill watchdog process: {pkill.stderr.strip() or pkill.stdout.strip()}")
    print(Colors.green(f"[SSH] Stopped existing watchdog process (if any)"))

    # 5. Run the controller
    path = remote_path(user, Remote_Paths.CONTROLLERS)
    remote_cmd = (
        "source ~/miniconda3/etc/profile.d/conda.sh && "
        f"conda activate /home/{user}/miniconda3/envs/{user} && "
        f"cd {shlex.quote(path)} && "
        f"/home/{user}/miniconda3/envs/{user}/bin/python {shlex.quote(name)}"
    )
    print(Colors.yellow(f"[SSH] Running {name} on Jetson..."))
    ctrl = ssh_run(user, host, remote_cmd)
    if not ctrl:
        print(Colors.red("[SSH] SSH Master failed to execute controller run"))
        return (False, "SSH Master failed to execute controller run")
    if ctrl.returncode != 0:
        print(Colors.red(f"[SSH] Remote run failed:\n{ctrl.stderr}"))
        return (False, f"Failed to run remote controller: {ctrl.stderr.strip() or ctrl.stdout.strip()}")
    print(Colors.green(f"[SSH] Flexible controller started successfully"))
    
    # 6. Setup devices
    path = remote_path(user, Remote_Paths.DEVICES)
    remote_cmd = f"sudo -n {shlex.quote(path)}"
    print(Colors.yellow(f"[SYNC] Setting up devices with {path}"))
    devices = ssh_bash(user, host, remote_cmd)
    if not devices:
        print(Colors.red("[SSH] SSH Master failed to execute device setup"))
        return (False, "SSH Master failed to execute device setup")
    if devices.returncode != 0:
        print(Colors.red(f"[SYNC] Device setup failed:\n{devices.stderr}"))
    else:
        print(Colors.green(f"[SYNC] Device setup successful"))

    return (True, "Flexible controller started successfully")

def stop_remote_controller(name, user, host):
    """
    Stops the named controller via pkill.
    Returns (ok: bool, message: str).
    """
    normalized = name if name.endswith(".py") else f"{name}.py"

    if not ensure_master(user, host, persist="5m"):
        return (False, "SSH control master not available")

    # 1. Kill the connection hub
    remote_cmd = f"sudo pkill -15 -f connection_hub.py"
    kill = ssh_run(user, host, remote_cmd)
    if not kill:
        print(Colors.red("[SSH] SSH Master failed to execute connection hub kill"))
        return (False, "SSH Master failed to execute connection hub kill")
    if kill.returncode != 0:        
        print(Colors.red(f"[SSH] Failed to stop connection hub:\n{kill.stderr}"))
    print(Colors.green(f"[SSH] Stopped existing connection hub process (if any)"))

    # 2. Stop the controller itself
    remote_cmd = f"sudo pkill -15 -f {shlex.quote(normalized)}"
    print(Colors.yellow(f"\n[SSH] Stopping remote controller: {normalized}"))
    stop_ctrl = ssh_run(user, host, remote_cmd)
    if not stop_ctrl:
        print(Colors.red("[SSH] SSH Master failed to execute controller stop"))
        return (False, "SSH Master failed to execute controller stop")
    if stop_ctrl.returncode != 0:
        print(Colors.red(f"[SSH] Remote stop failed:\n{stop_ctrl.stderr}"))
        return (False, f"Remote stop failed: {stop_ctrl.stderr.strip() or stop_ctrl.stdout.strip()}")
    
    # 3. Setup devices
    path = remote_path(user, Remote_Paths.SETUP_DEVICES)
    remote_cmd = f"sudo -n {shlex.quote(path)}"
    print(Colors.yellow(f"[SYNC] Setting up devices with {path}"))

    devices = ssh_bash(user, host, remote_cmd)
    if not devices:
        print(Colors.red("[SSH] SSH Master failed to execute device setup"))
        return (False, "SSH Master failed to execute device setup")
    if devices.returncode != 0:
        print(Colors.red(f"[SYNC] Device setup failed:\n{devices.stderr}"))
    else:
        print(Colors.green(f"[SYNC] Device setup successful"))
    
    print(Colors.green(f"[SSH] Remote controller stopped:\n{stop_ctrl.stdout}"))
    return (True, "Stopped.")