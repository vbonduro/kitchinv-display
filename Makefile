SRC = main.py lib/

install:
	@while IFS= read -r pkg; do mpremote mip install $$pkg; done < requirements.txt

DEVICE ?= /dev/ttyACM0

run:
	pkill -x mpremote 2>/dev/null || true
	mpremote connect $(DEVICE) mount . run main.py

# Copy all source files to Pico flash so deep-sleep wakes work without USB mount.
# After deploy, the device runs standalone — use 'make run' for live-mount testing.
deploy:
	pkill -x mpremote 2>/dev/null || true
	mpremote connect $(DEVICE) cp main.py :main.py
	mpremote connect $(DEVICE) mkdir :lib 2>/dev/null || true
	for f in lib/*.py; do mpremote connect $(DEVICE) cp $$f :$$f; done

check:
	uv run ruff check $(SRC)
	uv run mypy $(SRC)

fix:
	uv run ruff format $(SRC)
	uv run ruff check --fix $(SRC)
