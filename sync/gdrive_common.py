"""Shared by gdrive-status and gdrive-setup: config file, legacy migration, requirement checks.

Standard library only. The config is plain KEY=value lines so the bash scripts can read it
without sourcing it:  ~/.config/gdrive-sync/config
"""
import os
import re
import shutil
import subprocess

KEYS = ["REMOTE", "REMOTE_PATH", "LOCAL", "MODE", "VERSION", "CREATED_REMOTE", "LEGACY"]
MODES = ("twoway", "upload", "download")
RCLONE_MIN = (1, 66)
SERVICE = "gdrive-sync.service"


def _env(env):
    return os.environ if env is None else env


def paths(env=None):
    env = _env(env)
    home = env.get("HOME") or os.path.expanduser("~")
    cfg_home = env.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    state = env.get("GDRIVE_STATE") or os.path.join(home, ".local/state/gdrive-sync")
    share = os.path.join(home, ".local/share/gdrive-sync")
    unit_dir = os.path.join(cfg_home, "systemd/user")
    return {
        "home": home,
        "config": os.path.join(cfg_home, "gdrive-sync", "config"),
        "filters": os.path.join(cfg_home, "gdrive-sync", "filters.txt"),
        "state": state,
        "setupJson": os.path.join(state, "setup.json"),
        "share": share,
        "bin": os.path.join(share, "bin"),
        "conflicts": os.path.join(share, "conflicts"),
        "unitDir": unit_dir,
        "unit": os.path.join(unit_dir, env.get("GDRIVE_SERVICE") or SERVICE),
        "localBin": os.path.join(home, ".local/bin"),
    }


def atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def read_config(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    out = {}
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key in KEYS:
            out[key] = value
    return out if "REMOTE" in out and "LOCAL" in out else {}


def write_config(path, values):
    values = dict(values, VERSION="1")
    lines = []
    for key in KEYS:
        if key in values and values[key] is not None:
            value = str(values[key])
            if "\n" in value or "\r" in value:
                raise ValueError(f"{key} contains a line break")
            lines.append(f"{key}={value}\n")
    atomic_write(path, "".join(lines))


def split_remote(spec):
    """'gdrive:A/B' -> ('gdrive:', 'A/B')."""
    name, sep, rest = spec.partition(":")
    return (name + ":", rest.strip("/")) if sep else (spec, "")


def effective(env=None):
    """Settings in use (config + GDRIVE_* overrides), or None when not configured."""
    env = _env(env)
    cfg = read_config(paths(env)["config"])
    if not cfg:
        return None
    remote, remote_path = cfg["REMOTE"], cfg.get("REMOTE_PATH", "").strip("/")
    if env.get("GDRIVE_REMOTE"):
        remote, remote_path = split_remote(env["GDRIVE_REMOTE"])
    mode = env.get("GDRIVE_MODE") or cfg.get("MODE")
    return {
        "remote": remote,
        "remotePath": remote_path,
        "target": remote + remote_path,
        "local": (env.get("GDRIVE_LOCAL") or cfg["LOCAL"]).rstrip("/") or "/",
        "mode": mode if mode in MODES else "twoway",
        "createdRemote": cfg.get("CREATED_REMOTE") == "1",
        "legacy": cfg.get("LEGACY") == "1",
    }


def detect_legacy(env=None):
    """A 0.1.0 install (service unit + bisync baseline, no config) is already in sync."""
    env = _env(env)
    p = paths(env)
    if os.path.exists(p["config"]):
        return None
    if not (os.path.isfile(p["unit"]) and os.path.exists(os.path.join(p["state"], "initialized"))):
        return None
    remote, remote_path = split_remote(env.get("GDRIVE_REMOTE") or "gdrive:")
    local = env.get("GDRIVE_LOCAL") or os.path.join(p["home"], "GoogleDrive")
    return {"REMOTE": remote, "REMOTE_PATH": remote_path, "LOCAL": local.rstrip("/"),
            "MODE": "twoway", "LEGACY": "1"}


def migrate_if_legacy(env=None):
    """Writes the config for a legacy install. Never syncs. True if it wrote one."""
    values = detect_legacy(env)
    if not values:
        return False
    write_config(paths(env)["config"], values)
    return True


# ---------- requirements ----------

def which(name, env=None):
    return shutil.which(name, path=_env(env).get("PATH"))


def rclone_bin(env=None):
    return _env(env).get("GDRIVE_RCLONE") or "rclone"


def rclone_version(env=None):
    exe = which(rclone_bin(env), env)
    if not exe:
        return None
    try:
        p = subprocess.run([exe, "version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"rclone v(\d+)\.(\d+)(?:\.(\d+))?", p.stdout)
    return ".".join(g for g in m.groups() if g is not None) if m else None


def _version_ok(version):
    if not version:
        return False
    major, minor = (int(x) for x in version.split(".")[:2])
    return (major, minor) >= RCLONE_MIN


PKG_MANAGERS = [  # (binary, name, install command prefix)
    ("pacman", "pacman", "sudo pacman -S --needed"),
    ("apt-get", "apt", "sudo apt install"),
    ("dnf", "dnf", "sudo dnf install"),
    ("zypper", "zypper", "sudo zypper install"),
]
RCLONE_SCRIPT = "sudo -v && curl https://rclone.org/install.sh | sudo bash"


def checks(env=None):
    env = _env(env)
    version = rclone_version(env)
    rclone_ok = _version_ok(version)
    inotify = bool(which("inotifywait", env))
    pkg = next(((name, cmd) for exe, name, cmd in PKG_MANAGERS if which(exe, env)), (None, None))
    commands = []
    packages = []
    if not rclone_ok:
        # Debian/Ubuntu ship rclone versions older than 1.66; use the official installer there.
        if pkg[0] in ("pacman", "dnf", "zypper"):
            packages.append("rclone")
        else:
            commands.append(RCLONE_SCRIPT)
    if not inotify:
        packages.append("inotify-tools")
    if packages and pkg[1]:
        commands.insert(0, f"{pkg[1]} {' '.join(packages)}")
    return {
        "rclone": version is not None,
        "rcloneVersion": version,
        "rcloneOk": rclone_ok,
        "python": True,
        "systemd": bool(which("systemctl", env) and which("systemd-run", env)),
        "inotify": inotify,
        "pkgManager": pkg[0],
        "installCommand": " && ".join(commands) or None,
    }
