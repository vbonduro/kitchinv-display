SRC = main.py lib/

install:
	@while IFS= read -r pkg; do mpremote mip install $$pkg; done < requirements.txt

check:
	uv run ruff check $(SRC)
	uv run mypy $(SRC)

fix:
	uv run ruff format $(SRC)
	uv run ruff check --fix $(SRC)
