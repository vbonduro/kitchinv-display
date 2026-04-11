import json
import logging

_CONFIG_FILE = "config.json"


class Settings:
    """WiFi and application settings.

    Mirrors a dataclass — MicroPython has no dataclasses module.
    """

    def __init__(self, wifi: dict, kitchinv_url: str):
        self.wifi = wifi  # {"ssid": str, "password": str}
        self.kitchinv_url = kitchinv_url

    def __repr__(self):
        # Omit password from repr
        return "Settings(wifi={!r}, kitchinv_url={!r})".format(
            {"ssid": self.wifi.get("ssid")}, self.kitchinv_url
        )

    def _to_dict(self):
        return {"wifi": self.wifi, "kitchinv_url": self.kitchinv_url}

    @classmethod
    def _from_dict(cls, d):
        return cls(wifi=d["wifi"], kitchinv_url=d["kitchinv_url"])


def load():
    """Load settings from config.json. Returns None if missing or malformed."""
    try:
        with open(_CONFIG_FILE, "r") as f:
            return Settings._from_dict(json.load(f))
    except OSError:
        logging.info("No config file found.")
        return None
    except (KeyError, ValueError) as e:
        logging.warning("Malformed config: %s", e)
        return None


def save(settings):
    """Persist settings to config.json."""
    with open(_CONFIG_FILE, "w") as f:
        json.dump(settings._to_dict(), f)
    logging.info("Settings saved.")
