import os
import logging
import copy
import re
import sys
import glob
import time
import asyncio
import struct
import fcntl
import threading
from settings import SettingsManager
import decky

# ==========================================
# SECTION: LOGGER CONFIGURATION
# ==========================================
try:
    LOG_LOCATION = "/tmp/LegionControl.log"
    logging.basicConfig(
        level = logging.INFO,
        filename = LOG_LOCATION,
        format="[%(asctime)s | %(filename)s:%(lineno)s:%(funcName)s] %(levelname)s: %(message)s",
        filemode = 'w',
        force = True)
except Exception as e:
    logging.error(f"exception|{e}")

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

# ==========================================
# SECTION: SYSTEM PATHS & CONSTANTS
# ==========================================
CONSERVATION_FILE = "/sys/bus/platform/drivers/ideapad_acpi/VPC2004:00/conservation_mode"
RGB_BASE_PATH = "/sys/class/leds/go:rgb:joystick_rings"

LEVEL_NAMES  = ["off", "low", "medium", "high"]
RUMBLE_MODES = ["fps", "racing", "standard", "spg", "rpg"]
DEFAULT_APP = "0"

PKEY_LEVEL  = "level"
PKEY_MODE   = "mode"
PKEY_TP_INT = "touchpadIntensity"
PKEY_TP_EN  = "touchpadEnabled"

DEFAULT_PROFILE = {
    PKEY_LEVEL:  2,
    PKEY_MODE:   2, # standard mode
    PKEY_TP_INT: 1,
    PKEY_TP_EN:  True,
}

settings = SettingsManager(
    name="settings",
    settings_directory=decky.DECKY_PLUGIN_SETTINGS_DIR,
)

_settings_lock = threading.RLock()
_SIGNATURE_ATTR = "rumble_intensity"

_device_path: str | None = None
_apply_lock = threading.Lock()
_ff_busy = False

# Force-feedback ioctl constants
_EVIOCGBIT_FF = 0x80204535
_EVIOCSFF     = 0x40304580
_EVIOCRMFF    = 0x40044581
_EV_FF        = 0x15
_FF_RUMBLE    = 0x50

# ==========================================
# SECTION: HARDWARE DETECTION & ATTRIBUTES
# ==========================================
def _discover() -> str | None:
    """Discover input device path based on signature attribute."""
    for pattern in [f"/sys/bus/hid/drivers/*/*/{_SIGNATURE_ATTR}"]:
        for match in glob.glob(pattern):
            return os.path.dirname(match)
    return None

def _get_device_path() -> str | None:
    """Get cached or newly discovered hardware device path."""
    global _device_path
    if _device_path is not None and os.path.exists(os.path.join(_device_path, _SIGNATURE_ATTR)):
        return _device_path
    _device_path = _discover()
    return _device_path

def _read_enum(sys_path: str, rel_path: str, fallback: list[str]) -> list[str]:
    """Read available enumeration options from sysfs attribute index."""
    try:
        with open(os.path.join(sys_path, rel_path + '_index')) as f:
            values = f.read().split()
        if values:
            return values
    except OSError:
        pass
    return list(fallback)

def _write_attr(sys_path: str, rel_path: str, value: str) -> bool:
    """Write value to specified sysfs path."""
    path = os.path.join(sys_path, rel_path)
    try:
        with open(path, 'w') as f:
            f.write(value + '\n')
        return True
    except OSError as exc:
        decky.logger.error(f"[lego-control] write {path}: {exc}")
        return False

async def _offload(fn, *args):
    """Run blocking synchronous functions in a separate thread pool executor."""
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)

# ==========================================
# SECTION: SETTINGS APPLICATION (HARDWARE)
# ==========================================
def _apply_settings(values: dict) -> bool:
    """Apply vibration and controller settings directly to the hardware."""
    with _apply_lock:
        p = _get_device_path()
        if p is None:
            return False

        intensities = _read_enum(p, 'rumble_intensity', LEVEL_NAMES)
        lvl_idx = max(0, min(len(intensities) - 1, int(values.get(PKEY_LEVEL, 2))))

        modes = _read_enum(p, 'left_handle/rumble_mode', RUMBLE_MODES)
        mode_idx = max(0, min(len(modes) - 1, int(values.get(PKEY_MODE, 2))))
        mode_str = modes[mode_idx]

        tp_intensities = _read_enum(p, 'touchpad/vibration_intensity', LEVEL_NAMES)
        tp_lvl_idx = max(0, min(len(tp_intensities) - 1, int(values.get(PKEY_TP_INT, 1))))

        res1 = _write_attr(p, 'rumble_intensity', intensities[lvl_idx])
        _write_attr(p, 'left_handle/rumble_mode', mode_str)
        _write_attr(p, 'right_handle/rumble_mode', mode_str)
        res2 = _write_attr(p, 'touchpad/vibration_intensity', tp_intensities[tp_lvl_idx])
        res3 = _write_attr(p, 'touchpad/vibration_enabled', "true" if values.get(PKEY_TP_EN, True) else "false")

        return res1 and res2 and res3

# ==========================================
# SECTION: STORAGE & PROFILE MANAGEMENT
# ==========================================
def _load_profiles() -> dict:
    """Load configuration profiles from persistent storage."""
    with _settings_lock:
        settings.read()
        profiles = settings.getSetting("game_profiles", {}) or {}
        if not isinstance(profiles, dict):
            profiles = {}
    if DEFAULT_APP not in profiles:
        profiles[DEFAULT_APP] = {"overwrite": False, "settings": dict(DEFAULT_PROFILE)}
    return profiles

def _save_profiles(profiles: dict) -> None:
    """Save configuration profiles to persistent storage."""
    with _settings_lock:
        settings.setSetting("game_profiles", profiles)
        settings.commit()

def _active_values() -> dict:
    """Retrieve currently active profile settings dictionary."""
    profiles = _load_profiles()
    raw = profiles.get(DEFAULT_APP, {}).get("settings", {})
    return {
        PKEY_LEVEL: int(raw.get(PKEY_LEVEL, DEFAULT_PROFILE[PKEY_LEVEL])),
        PKEY_MODE: int(raw.get(PKEY_MODE, DEFAULT_PROFILE[PKEY_MODE])),
        PKEY_TP_INT: int(raw.get(PKEY_TP_INT, DEFAULT_PROFILE[PKEY_TP_INT])),
        PKEY_TP_EN: bool(raw.get(PKEY_TP_EN, DEFAULT_PROFILE[PKEY_TP_EN])),
    }

def _update_active(field: str, value) -> dict:
    """Update a specific field in the active profile and save it."""
    profiles = _load_profiles()
    entry = profiles.setdefault(DEFAULT_APP, {"overwrite": False, "settings": dict(DEFAULT_PROFILE)})
    entry["settings"][field] = value
    _save_profiles(profiles)
    return entry["settings"]

# ==========================================
# SECTION: DECKY PLUGIN CLASS
# ==========================================
class Plugin:
    _setup_error: str | None = None

    async def _main(self):
        """Called automatically when the plugin starts up."""
        decky.logger.info("[lego-control] Initialized quietly")

    async def _unload(self):
        """Called automatically when the plugin is unloaded or removed."""
        pass

    async def get_charge_status(self):
        """Get the current battery conservation mode status."""
        try:
            if os.path.exists(CONSERVATION_FILE):
                with open(CONSERVATION_FILE, "r") as f:
                    return f.read().strip() == "1"
        except Exception:
            pass
        return False

    async def set_charge_status(self, enabled: bool):
        """Enable or disable battery conservation mode."""
        val_cons = "1" if enabled else "0"
        try:
            if os.path.exists(CONSERVATION_FILE):
                with open(CONSERVATION_FILE, "w") as f:
                    f.write(val_cons)
                return {"success": True}
        except Exception:
            pass
        return {"success": False}

    async def get_rgb_state(self):
        """Retrieve current RGB lighting state and effect."""
        state = {"enabled": False, "effect": "monocolor"}
        try:
            if os.path.exists(f"{RGB_BASE_PATH}/enabled"):
                with open(f"{RGB_BASE_PATH}/enabled", "r") as f:
                    state["enabled"] = (f.read().strip() == "true")
            if os.path.exists(f"{RGB_BASE_PATH}/effect"):
                with open(f"{RGB_BASE_PATH}/effect", "r") as f:
                    state["effect"] = f.read().strip()
        except Exception:
            pass
        return state

    async def set_rgb_enabled(self, enabled: bool):
        """Turn joystick RGB lighting on or off."""
        val = "true" if enabled else "false"
        try:
            if os.path.exists(f"{RGB_BASE_PATH}/enabled"):
                with open(f"{RGB_BASE_PATH}/enabled", "w") as f:
                    f.write(val)
                return {"success": True}
        except Exception:
            pass
        return {"success": False}

    async def set_rgb_effect(self, effect: str):
        """Set the active RGB lighting effect mode."""
        try:
            if os.path.exists(f"{RGB_BASE_PATH}/mode"):
                with open(f"{RGB_BASE_PATH}/mode", "w") as f:
                    f.write("custom")
            if os.path.exists(f"{RGB_BASE_PATH}/effect"):
                with open(f"{RGB_BASE_PATH}/effect", "w") as f:
                    f.write(effect)
                return {"success": True}
        except Exception:
            pass
        return {"success": False}

    async def get_settings(self) -> dict:
        """Fetch active controller settings for the frontend UI."""
        vals = await _offload(_active_values)
        return {"settings": vals}

    async def set_intensity(self, level: int) -> dict:
        """Set and save controller rumble intensity level."""
        def _do():
            vals = _update_active(PKEY_LEVEL, max(0, min(3, int(level))))
            profiles = _load_profiles()
            profiles[DEFAULT_APP]["settings"] = vals
            _save_profiles(profiles)
            return _apply_settings(vals)
        return {"success": await _offload(_do)}

    async def set_rumble_mode(self, mode: int) -> dict:
        """Set and save controller rumble profile mode."""
        def _do():
            vals = _update_active(PKEY_MODE, max(0, min(4, int(mode))))
            profiles = _load_profiles()
            profiles[DEFAULT_APP]["settings"] = vals
            _save_profiles(profiles)
            return _apply_settings(vals)
        return {"success": await _offload(_do)}

    async def set_touchpad_intensity(self, level: int) -> dict:
        """Set and save touchpad haptic feedback intensity."""
        def _do():
            vals = _update_active(PKEY_TP_INT, max(0, min(3, int(level))))
            profiles = _load_profiles()
            profiles[DEFAULT_APP]["settings"] = vals
            _save_profiles(profiles)
            return _apply_settings(vals)
        return {"success": await _offload(_do)}

    async def set_touchpad_enabled(self, enabled: bool) -> dict:
        """Enable or disable touchpad haptic feedback."""
        def _do():
            vals = _update_active(PKEY_TP_EN, bool(enabled))
            profiles = _load_profiles()
            profiles[DEFAULT_APP]["settings"] = vals
            _save_profiles(profiles)
            return _apply_settings(vals)
        return {"success": await _offload(_do)}

    async def test_vibration(self, duration_ms: int = 500) -> dict:
        """Trigger an instant test rumble vibration pulse on the controller."""
        global _ff_busy
        if _ff_busy:
            return {"success": False, "error": "Busy"}
        _ff_busy = True
        try:
            vals = await _offload(_active_values)
            level = vals[PKEY_LEVEL]
            if level <= 0:
                return {"success": False, "error": "Off"}

            intensity_pct = [0, 33, 66, 100][max(0, min(3, level))]
            duration = max(100, min(2000, int(duration_ms)))
            magnitude = int(0xFFFF * intensity_pct / 100)

            nodes = glob.glob('/dev/input/event*')
            ff_path = None
            for n in nodes:
                try:
                    with open(n, 'rb') as fh:
                        bits = bytearray(32)
                        fcntl.ioctl(fh.fileno(), _EVIOCGBIT_FF, bits)
                        if bool(bits[_FF_RUMBLE // 8] & (1 << (_FF_RUMBLE % 8))):
                            ff_path = n
                            break
                except Exception:
                    continue

            if not ff_path:
                return {"success": False, "error": "No FF device"}

            fd = os.open(ff_path, os.O_RDWR)
            try:
                effect_buf = bytearray(struct.pack('<HhHHHHHxxHH28x', _FF_RUMBLE, -1, 0, 0, 0, duration, 0, magnitude, magnitude))
                fcntl.ioctl(fd, _EVIOCSFF, effect_buf)
                effect_id = struct.unpack_from('<h', effect_buf, 2)[0]
                if effect_id < 0:
                    return {"success": False, "error": "Rejected"}

                t = time.time()
                ev = struct.pack('<qqHHi', int(t), int((t % 1) * 1e6) % 1_000_000, _EV_FF, effect_id, 1)
                os.write(fd, ev)
                await asyncio.sleep(duration / 1000.0)
                ev_off = struct.pack('<qqHHi', int(t), int((t % 1) * 1e6) % 1_000_000, _EV_FF, effect_id, 0)
                os.write(fd, ev_off)
                fcntl.ioctl(fd, _EVIOCRMFF, effect_id)
                return {"success": True}
            finally:
                os.close(fd)
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        finally:
            _ff_busy = False

    async def log_info(self, info):
        """Write custom info message into plugin log file."""
        logging.info(info)
