"""
File logging handler for MicroPython.

Adds a FileHandler to the root logger so every logging.info/warning/error
call is written to /log.txt on flash in addition to the serial console.

Log rotation: when the file exceeds _MAX_BYTES the oldest half is dropped,
keeping the most recent entries without unbounded flash growth.

Usage
-----
    from lib import logger
    logger.setup()          # call once instead of logging.basicConfig()

Reading logs
------------
    make log                # print /log.txt over serial
    make clear-log          # delete /log.txt
"""

import logging
import time

import uos

_LOG_FILE = "/log.txt"
_MAX_BYTES = 8192


class _FileHandler(logging.Handler):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))

    def emit(self, record: object) -> None:  # type: ignore[override]
        try:
            if uos.stat(_LOG_FILE)[6] > _MAX_BYTES:
                with open(_LOG_FILE) as f:
                    content = f.read()
                with open(_LOG_FILE, "w") as f:
                    f.write(content[len(content) // 2 :])
        except OSError:
            pass
        try:
            with open(_LOG_FILE, "a") as f:
                t = time.localtime(record.ct)  # type: ignore[attr-defined]
                ts = "%04d-%02d-%02d %02d:%02d:%02d" % (t[0], t[1], t[2], t[3], t[4], t[5])
                f.write("%s %s\n" % (ts, self.format(record)))  # type: ignore[arg-type]
        except OSError:
            pass


def _boot_reason() -> str:
    """Human-readable reset cause for the boot separator."""
    import machine  # type: ignore[import]

    cause = machine.reset_cause()
    if cause == getattr(machine, "PWRON_RESET", 1):
        return "power-on"
    if cause == getattr(machine, "DEEPSLEEP_RESET", 7):
        return "wake-from-sleep"
    if cause == getattr(machine, "WDT_RESET", 4):
        return "watchdog"
    return "reset (%d)" % cause


def setup(level: int = logging.INFO) -> None:
    """Configure logging to serial console and /log.txt."""
    logging.basicConfig(level=level)
    logging.getLogger().addHandler(_FileHandler())
    # Separator so each boot is easy to find in the log.
    try:
        with open(_LOG_FILE, "a") as f:
            f.write("=== boot: %s ===\n" % _boot_reason())
    except OSError:
        pass
