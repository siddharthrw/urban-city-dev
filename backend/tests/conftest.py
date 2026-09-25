"""Tests use a throwaway DATA_DIR, never the real one. Must run before core.config is imported."""
import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="citydata_test_")
