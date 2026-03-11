# services/tests/

Smoke tests that validate service structure, entrypoints, and dependency files. Run as part of the CI/CD pipeline before building Docker images.

## Files

| File            | Purpose                                          |
| --------------- | ------------------------------------------------ |
| `test_smoke.py` | Parametrized pytest suite for service validation |

## Test Cases

```python
# Validates each service has its main entrypoint file
@pytest.mark.parametrize("module_path", [
    "gateway.main", "quant-api.main", "finetune-api.main",
    "eval-api.main", "data-engine.api"
])
def test_service_has_entrypoint(module_path): ...

# Validates shared library exists with key modules
def test_shared_package_exists(): ...

# Validates every deployable service has requirements.txt
def test_requirements_files(): ...
```

## Usage

```bash
pytest services/tests/ -v --tb=short
```

## Relationship to CI/CD

These tests run in the `lint-and-test` job of `.github/workflows/ci-cd.yaml` — the build-push jobs depend on them passing.
