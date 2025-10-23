import os, socket, json, time, datetime
from config import Remote_Paths, Colors
from util.utils import run, write_json, write_dashboard_info
from config import Local_Paths

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
def batch_compare_and_pull(user, host):
    """
    runs compare on Jetson, then prints both JSONs with markers.
    single SSH, single round-trip.
    """
    if not ssh_reachable(host):
        print(Colors.red("[SSH] SSH not reachable"))
        return None, None

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
        write_dashboard_info(user, host)
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
def periodic_sync(user, host, interval_sec=5):
    """
    every interval:
      - run compare remotely and fetch both JSONs in ONE ssh
      - write them locally for the dashboard
    """
    while True:
        cmp_payload, meta_payload = batch_compare_and_pull(user, host)
        if cmp_payload and meta_payload:
            write_json(Local_Paths.OUTPUT, cmp_payload)
            write_json(Local_Paths.META, meta_payload)
            
            curr = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(Colors.green(f"[SYNC {curr}] Updated comparison_output.json and meta.json"))
        else:
            print(Colors.red(f"[SYNC {curr}] Update failed"))

        time.sleep(interval_sec)