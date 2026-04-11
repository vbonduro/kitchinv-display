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

### Running

Mount the project directory and run `main.py` directly on the device:

```bash
mpremote mount . run main.py
```

On first boot with no saved config, the Pico will broadcast a `KitchInv-Setup` WiFi network.
Connect to it and navigate to `http://192.168.4.1` to enter WiFi credentials and the KitchInv server URL.
Settings are saved to `config.json` on the device and used on every subsequent boot.

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
