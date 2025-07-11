import warnings
import os
import json
from datetime import datetime


class CurlCffiWarning(UserWarning, RuntimeWarning):
    pass


def config_warnings(on: bool = False):
    if on:
        warnings.simplefilter("default", category=CurlCffiWarning)
    else:
        warnings.simplefilter("ignore", category=CurlCffiWarning)


def is_pro():
    config_file = os.path.expanduser("~/.config/impersonate/config.json")
    if not os.path.exists(config_file):
        return False
    with open(config_file) as f:
        try:
            config = json.load(f)
            return config.get("key") not in [None, ""]
        except json.JSONDecodeError:
            return False


def enable_pro(key: str):
    """Enable the pro version"""
    config_dir = os.path.expanduser("~/.config/impersonate")
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    config_file = os.path.join(config_dir, "config.json")
    if os.path.exists(config_file):
        with open(config_file) as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError:
                config = {}
    else:
        config = {}
    config["key"] = key
    config["update_time"] = datetime.utcnow().isoformat()
    with open(config_file, "w") as f:
        json.dump(config, f, indent=4)
