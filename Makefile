SRC = main.py lib/

VERSION ?= 0.1.0
DEVICE  ?= /dev/ttyACM1

install:
	@while IFS= read -r pkg; do mpremote mip install $$pkg; done < requirements.txt

run: deploy-dev

_stamp_version:
	@printf 'VERSION = "%s"\nBUILD_TS = "%s"\n' \
		"$(VERSION)" \
		"$$(date -u +%Y-%m-%dT%H:%M:%SZ)" > version.py

_deploy_files: _stamp_version
	pkill -x mpremote 2>/dev/null || true
	mpremote connect $(DEVICE) cp main.py :main.py
	mpremote connect $(DEVICE) cp version.py :version.py
	mpremote connect $(DEVICE) mkdir :lib 2>/dev/null || true
	for f in lib/*.py; do mpremote connect $(DEVICE) cp $$f :$$f; done
	mpremote connect $(DEVICE) mkdir :lib/states 2>/dev/null || true
	for f in lib/states/*.py; do mpremote connect $(DEVICE) cp $$f :$$f; done

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
	mpremote connect $(DEVICE) reset; sleep 2
	mpremote connect $(DEVICE) rm :config.json 2>/dev/null || true
	mpremote connect $(DEVICE) rm :cycle_state.bin 2>/dev/null || true
	rm -f config.json
	mpremote connect $(DEVICE) reset

# NOTE: This reboots the device as a side effect.
# mpremote must interrupt the running script (via Ctrl+C) to access the
# filesystem, so a reset is issued afterwards to restart cleanly rather
# than leaving the device stuck at the REPL.
log:
	mpremote connect $(DEVICE) exec "import uos; print(open('/log.txt').read() if 'log.txt' in [f[0] for f in uos.ilistdir('/')] else '(no log file yet)')" reset

clear-log:
	mpremote connect $(DEVICE) rm :log.txt

check:
	uv run ruff check $(SRC)
	uv run mypy $(SRC)

fix:
	uv run ruff format $(SRC)
	uv run ruff check --fix $(SRC)
