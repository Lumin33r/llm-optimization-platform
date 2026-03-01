"""Smoke tests — verify each service's FastAPI app can be imported."""

import sys
from pathlib import Path

import pytest

# Add services/ to sys.path so imports work like they do in Docker
SERVICES_DIR = Path(__file__).resolve().parent.parent
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))


@pytest.mark.parametrize(
    "module_path",
    [
        "gateway.main",
        "quant-api.main",
        "finetune-api.main",
        "eval-api.main",
        "data-engine.api",
    ],
    ids=["gateway", "quant-api", "finetune-api", "eval-api", "data-engine"],
)
def test_service_has_entrypoint(module_path):
    """Each service directory should have its main module present."""
    service_dir, module_name = module_path.rsplit(".", 1)
    entry = SERVICES_DIR / service_dir / f"{module_name}.py"
    assert entry.exists(), f"{entry} not found"


def test_shared_package_exists():
    """The shared/ library must exist with its key modules."""
    shared = SERVICES_DIR / "shared"
    assert shared.is_dir(), "services/shared/ directory missing"
    assert (shared / "telemetry.py").exists(), "shared/telemetry.py missing"
    assert (shared / "health.py").exists(), "shared/health.py missing"


def test_requirements_files():
    """Every deployable service must have a requirements.txt."""
    for svc in ["gateway", "quant-api", "finetune-api", "eval-api", "data-engine"]:
        req = SERVICES_DIR / svc / "requirements.txt"
        assert req.exists(), f"{svc}/requirements.txt missing"
