PYTHON := python
.PHONY: test scan-sample

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py"

scan-sample:
	$(PYTHON) jmapq.py tests/fixtures/foo.java
