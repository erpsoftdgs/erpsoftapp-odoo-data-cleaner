PYTHON ?= python3

.PHONY: test-engine

test-engine:
	$(PYTHON) -m unittest discover -s engine/tests -v
