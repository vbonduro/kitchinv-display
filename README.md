# kitchinv-display
Display kitchen and pantry inventory on an e-ink display.

## Hardware

- Raspberry Pi Pico 2 W

## Development

### First-time device setup

Download the latest MicroPython firmware from https://micropython.org/download/RPI_PICO2_W/.

Hold BOOTSEL, plug in the Pico 2 W via USB, then copy the `.uf2` file to the mounted drive.

Add yourself to the `dialout` group so you can access the serial port without `sudo`:

```bash
sudo usermod -aG dialout $USER
```

### Prerequisites

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and [mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html):

```bash
pip install --user mpremote
```

Install dev tooling (mypy, ruff, stubs):

```bash
uv sync --group dev
```

Install MicroPython dependencies onto the device:

```bash
make install
```

### Deploying

There are two deploy targets depending on context:

| Target | Sleep mode | Use when |
|---|---|---|
| `make deploy-dev` | Light (USB stays alive) | Daily dev work |
| `make deploy` | Deep (lowest power) | Standalone / production |

`make run` is an alias for `make deploy-dev`.

Both targets copy all source files to device flash, write the appropriate `features.ini`, and reset the device. The device runs autonomously after reset — no host connection required.

```bash
make run        # deploy with dev settings and reset
make deploy     # deploy with prod settings and reset
```

### First boot / WiFi setup

On first boot with no saved config, the Pico broadcasts a `KitchInv-Setup` WiFi network.
Connect to it and open `http://192.168.4.1` in a browser to enter WiFi credentials and the KitchInv server URL.
Settings are saved to flash and used on every subsequent boot.

To wipe WiFi/server config and re-enter setup mode:

```bash
make reset-config
```

### Viewing logs

All log output is written to `/log.txt` on device flash in addition to the serial console.
Each boot appends a `=== boot ===` separator so cycles are easy to tell apart.
The file rotates automatically when it exceeds 8 KB (oldest half is dropped).

```bash
make log        # print /log.txt from device flash
make clear-log  # delete /log.txt
```

### Feature flags

Runtime behaviour is controlled by `features.ini` on device flash.
The deploy targets write the appropriate file automatically — you don't normally need to edit this manually.

| Flag | Values | Default |
|---|---|---|
| `sleep_mode` | `deep` / `light` | `deep` |

- **deep** — `machine.deepsleep()`; lowest power, resets USB on wake (prod)
- **light** — `time.sleep_ms()` + `machine.reset()`; USB stays alive, easier to connect after a cycle (dev)

The source files for each build are in `features/`:

```
features/dev.ini   → sleep_mode = light
features/prod.ini  → sleep_mode = deep
```

## Code quality

### Check (lint + types)

```bash
make check
```

Runs `ruff check` followed by `mypy` across `main.py` and `lib/`. Exits non-zero on any error.

### Fix (format + auto-fix)

```bash
make fix
```

Runs `ruff format` and `ruff check --fix` to reformat code and resolve auto-fixable issues (import sorting, style, etc.).
