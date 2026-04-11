SRC = main.py lib/

install:
	@while IFS= read -r pkg; do mpremote mip install $$pkg; done < requirements.txt

DEVICE ?= /dev/ttyACM0

run:
	pkill -x mpremote 2>/dev/null || true
	mpremote connect $(DEVICE) mount . run main.py

check:
	uv run ruff check $(SRC)
	uv run mypy $(SRC)

fix:
	uv run ruff format $(SRC)
	uv run ruff check --fix $(SRC)
