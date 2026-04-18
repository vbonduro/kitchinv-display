"""
Feature flag loader.

Reads features.ini from the device filesystem and merges with in-code
defaults.  Missing keys fall back to their defaults so the file only
needs to contain overrides.

Feature flags
-------------
  sleep_mode = deep | light   (default: deep)
      deep  — machine.deepsleep(); USB drops, maximum battery life.
      light — time.sleep_ms() + machine.reset(); USB stays alive,
              mpremote can connect between cycles.
  ota_check = true | false   (default: false)
      true  — check GitHub Releases for firmware updates on each boot.
      false — skip OTA check (dev default).

The features.ini file is written to the device by the build system:
  make deploy      → features/prod.ini  (deep sleep)
  make deploy-dev  → features/dev.ini   (light sleep)
  make run         → features/dev.ini   (via exec before mount)
"""

_FEATURES_FILE = "/features.ini"

_DEFAULTS: dict = {
    "sleep_mode": "deep",
    "ota_check": "false",
}

_cache: dict | None = None


def _parse(text: str) -> dict:
    """Parse a simple INI file into a flat key/value dict."""
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def load() -> dict:
    """Return the feature flag dict, reading features.ini at most once."""
    global _cache
    if _cache is not None:
        return _cache
    flags = dict(_DEFAULTS)
    try:
        with open(_FEATURES_FILE) as f:
            flags.update(_parse(f.read()))
    except OSError:
        pass
    _cache = flags
    return _cache


def get(key: str) -> str:
    """Return the value of a single feature flag."""
    return load()[key]
