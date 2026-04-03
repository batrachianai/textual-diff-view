.PHONY: test

test:
	uv run pytest tests/

.PHONY: update-snapshots

update-snapshots:
	uv run pytest tests/ --snapshot-update
