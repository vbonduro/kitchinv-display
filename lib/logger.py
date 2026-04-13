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

import uos

_LOG_FILE = "/log.txt"
_MAX_BYTES = 8192


class _FileHandler(logging.Handler):  # type: ignore[misc]
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
                f.write(self.format(record) + "\n")  # type: ignore[arg-type]
        except OSError:
            pass


def setup(level: int = logging.INFO) -> None:
    """Configure logging to serial console and /log.txt."""
    logging.basicConfig(level=level)
    logging.root.addHandler(_FileHandler())  # type: ignore[attr-defined]
    # Separator so each boot is easy to find in the log.
    try:
        with open(_LOG_FILE, "a") as f:
            f.write("=== boot ===\n")
    except OSError:
        pass
