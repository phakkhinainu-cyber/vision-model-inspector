import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("VMI_DATA_DIR", tempfile.mkdtemp(prefix="vmi-test-data-"))
os.environ.setdefault("YOLO_OFFLINE", "True")
os.environ.setdefault("YOLO_AUTOINSTALL", "False")

MODELS_DIR = os.environ.get("VMI_TEST_MODELS", os.path.join(ROOT, "test_assets", "models"))
ASSETS_DIR = os.path.join(ROOT, "test_assets")


def model_path(name):
    return os.path.join(MODELS_DIR, name)

import logging  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
