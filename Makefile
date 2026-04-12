SRC = main.py lib/

install:
	@while IFS= read -r pkg; do mpremote mip install $$pkg; done < requirements.txt

DEVICE ?= /dev/ttyACM0

# Run from host filesystem (no deploy needed). Injects dev feature flags
# before mounting so light sleep is active and USB stays up between cycles.
run:
	pkill -x mpremote 2>/dev/null || true
	mpremote connect $(DEVICE) exec "open('features.ini','w').write(open('features/dev.ini').read())" mount . run main.py

_deploy_files:
	mpremote connect $(DEVICE) cp main.py :main.py
	mpremote connect $(DEVICE) mkdir :lib 2>/dev/null || true
	for f in lib/*.py; do mpremote connect $(DEVICE) cp $$f :$$f; done

# Copy all source files to Pico flash for standalone operation.
deploy: _deploy_files
	mpremote connect $(DEVICE) cp features/prod.ini :features.ini
	mpremote connect $(DEVICE) reset

# Deploy with dev feature flags — light sleep keeps USB alive between cycles.
deploy-dev: _deploy_files
	mpremote connect $(DEVICE) cp features/dev.ini :features.ini
	mpremote connect $(DEVICE) reset

# Remove saved WiFi/server config so the device boots into captive-portal mode.
reset-config:
	pkill -x mpremote 2>/dev/null || true
	mpremote connect $(DEVICE) reset
	mpremote connect $(DEVICE) rm :config.json 2>/dev/null || true
	mpremote connect $(DEVICE) rm :cycle_state.bin 2>/dev/null || true
	mpremote connect $(DEVICE) reset

check:
	uv run ruff check $(SRC)
	uv run mypy $(SRC)

fix:
	uv run ruff format $(SRC)
	uv run ruff check --fix $(SRC)
