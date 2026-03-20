---
title: "Python project bootstrap: setuptools build backend and src-layout path resolution"
date: "2026-03-19"
category: "build-errors"
tags: ["setuptools", "pyproject.toml", "pathlib", "pip", "python-packaging", "src-layout"]
problem_type: "configuration_error"
components: ["pyproject.toml", "src/schema_extract/pipeline.py"]
symptoms:
  - "BackendUnavailable: Cannot import 'setuptools.backends.legacy'"
  - "FileNotFoundError on schema/sample files with path escaping the repo root"
---

# Python Project Bootstrap: Build Backend and Path Resolution

Two bugs surfaced during initial project setup of a src-layout Python project. Both are silent traps — the code looks plausible but fails immediately on first run.

---

## Bug 1: setuptools build backend unavailable

### Problem

`pip install -e .` fails on a fresh venv:

```
pip._vendor.pyproject_hooks._impl.BackendUnavailable: Cannot import 'setuptools.backends.legacy'
```

### Root Cause

`setuptools.backends.legacy:build` is a path introduced in newer setuptools. But `pip install` bootstraps using its own *bundled* copy of setuptools, which predates this path. The real setuptools never gets a chance to install — the build fails before anything else runs.

### Solution

```toml
# pyproject.toml

# Before (broken)
build-backend = "setuptools.backends.legacy:build"

# After (correct)
build-backend = "setuptools.build_meta"
```

`setuptools.build_meta` has been stable since setuptools 40.8.0 (2019). Use it for all new projects. There is no scenario where `setuptools.backends.legacy` is preferable.

---

## Bug 2: Off-by-one in `__file__`-relative path resolution

### Problem

The pipeline demo fails with:

```
FileNotFoundError: [Errno 2] No such file or directory: '/Users/.../projects/samples/job_postings/sample_01.txt'
```

The path resolves to a directory *above* the repo root.

### Root Cause

`src/schema_extract/pipeline.py` is 3 directory levels deep. The code used 4 `.parent` calls:

```
pipeline.py → schema_extract/ → src/ → repo_root/ → parent_of_repo  ← wrong
```

### Solution

```python
# src/schema_extract/pipeline.py

# Before (broken — 4 hops exits the repo)
_REPO_ROOT = Path(__file__).parent.parent.parent.parent

# After (correct — 3 hops: schema_extract → src → repo root)
_REPO_ROOT = Path(__file__).parent.parent.parent
```

**Mental model:** count the number of directory separators between `__file__` and the target directory. `src/schema_extract/pipeline.py` has 2 separators → 3 `.parent` calls to reach the root containing `src/`.

---

## Prevention

### Checklist for new Python projects (src layout)

- [ ] `pyproject.toml` uses `build-backend = "setuptools.build_meta"` — verify before first `pip install`
- [ ] For any module computing `_REPO_ROOT` from `__file__`, count directory depth explicitly and print it once to confirm: `print(_REPO_ROOT)` should show the repo root, not its parent
- [ ] Run `pip install -e ".[dev]"` as the very first setup step — catches both issues immediately

### CI guard for path resolution

```python
# tests/test_paths.py
def test_repo_root_is_correct():
    from schema_extract.pipeline import _REPO_ROOT
    assert _REPO_ROOT.exists()
    assert (_REPO_ROOT / "pyproject.toml").exists()
    assert (_REPO_ROOT / "schemas").is_dir()
    assert (_REPO_ROOT / "samples").is_dir()
```

### CI guard for build backend

```bash
grep -q 'build-backend = "setuptools.build_meta"' pyproject.toml || (echo "Wrong build backend" && exit 1)
```
