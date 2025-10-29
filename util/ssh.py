import os, socket, json, time, datetime, re, shlex
from config import Remote_Paths, Colors, Local_Paths, Jetson, SpecialControllers
from util.utils import run, write_json, write_dashboard_info

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
        f"{user}@{host}",
    ])
    if r.returncode != 0:
        print(Colors.red(f"[SSH] Failed to start control master:\n{r.stderr}"))
        return False
    return True

def close_master(user, host):
    cp = control_path(user, host)
    run(["ssh", "-O", "exit", "-S", cp, f"{user}@{host}"])

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
    cp = control_path(user, host)
    remote_cmd = (
        f"python3 {Remote_Paths.COMPARE} "
        f"--req {Remote_Paths.REQ_PATH} "
        f"--meta {Remote_Paths.META_PATH} "
        f"--out {Remote_Paths.OUTPUT} >/dev/null 2>&1; "
        f"echo {BEGIN_CMP}; cat {Remote_Paths.OUTPUT}; "
        f"echo {BEGIN_META}; cat {Remote_Paths.META_PATH}"
    )

    r = run([
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-S", cp, f"{user}@{host}",
        remote_cmd
    ])

    if r.returncode != 0:
        print(Colors.red(f"[SSH] Remote batch failed:\n{r.stderr}"))
        return None, None

    out = r.stdout or ""
    try:
        write_dashboard_info(user, ssid)
        _, after_cmp = out.split(BEGIN_CMP, 1)
        cmp_json_str, after_meta = after_cmp.split(BEGIN_META, 1)
        cmp_json_str = cmp_json_str.strip()
        meta_json_str = after_meta.strip()

        cmp_payload = json.loads(cmp_json_str)
        meta_payload = json.loads(meta_json_str)
        return cmp_payload, meta_payload
    except Exception as e:
        print(Colors.red(f"[parse] Failed to parse batch output: {e}"))
        return None, None
    
##############################
# Sync loop
##############################
def periodic_sync(user, host, ssid, interval_sec=5):
    """
    every interval:
      - run compare remotely and fetch both JSONs in ONE ssh
      - write them locally for the dashboard
    """
    while True:
        cmp_payload, meta_payload = batch_compare_and_pull(user, host, ssid)
        if cmp_payload and meta_payload:
            write_json(Local_Paths.OUTPUT, cmp_payload)
            write_json(Local_Paths.META, meta_payload)
            
            curr = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[SYNC {curr}] Updated comparison_output.json and meta.json")
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

def run_remote_controller(name):
    """
    Runs the named controller on Sully via the SSH control master.
    Returns (ok: bool, message: str).
    """
    normalized = name if name.endswith(".py") else f"{name}.py"

    if (not ready_locally(normalized) and normalized not in SpecialControllers.ALLOWED and name not in SpecialControllers.ALLOWED):
        return (False, f"Blocked or unknown controller: {normalized}")

    if not ensure_master(Jetson.USER_SULLY, Jetson.HOST_SULLY, persist="5m"):
        return (False, "SSH control master not available")

    cp = control_path(Jetson.USER_SULLY, Jetson.HOST_SULLY)
    remote_cmd = f"cd {shlex.quote(Remote_Paths.CONTROLLERS)} && python3 {shlex.quote(normalized)}"
    print(Colors.yellow(f"\n[SSH] Running remote controller: {normalized}\n"))

    r = run([
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-S", cp, f"{Jetson.USER_SULLY}@{Jetson.HOST_SULLY}",
        remote_cmd
    ])
    if r.returncode != 0:
        return (False, f"Remote run failed: {r.stderr.strip() or r.stdout.strip()}")
    return (True, r.stdout.strip() or "Started.")

def stop_remote_controller(name):
    """
    Stops the named controller on Sully via pkill.
    Returns (ok: bool, message: str).
    """
    normalized = name if name.endswith(".py") else f"{name}.py"

    if not ensure_master(Jetson.USER_SULLY, Jetson.HOST_SULLY, persist="5m"):
        return (False, "SSH control master not available")

    cp = control_path(Jetson.USER_SULLY, Jetson.HOST_SULLY)
    remote_cmd = f"pkill -f {shlex.quote(normalized)}"
    print(Colors.yellow(f"\n[SSH] Stopping remote controller: {normalized}\n"))

    r = run([
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-S", cp, f"{Jetson.USER_SULLY}@{Jetson.HOST_SULLY}",
        remote_cmd
    ])
    if r.returncode != 0:
        return (False, f"Remote stop failed: {r.stderr.strip() or r.stdout.strip()}")
    return (True, "Stopped.")