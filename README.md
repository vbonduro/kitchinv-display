# kitchinv-display
Display kitchen and pantry inventory on an e-ink display.

# Development

## First Setup

Download latest firmware release from https://micropython.org/download/RPI_PICO2_W/.

Attach PICO2 W USB to your computer. Mount it and copy the FW over.

Add yourself to the dialout group.

## Pre-requisites

Install `mpremote`.

```bash
pip install --user mpremote`
```

## Quick Development

Mount the directory and run main.py:

```bash
mpremote mount . run main.py
```