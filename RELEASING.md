# Releasing PyRealtime

1. Update `__version__`, `project.version`, and `CHANGELOG.md` to the same SemVer value.
2. Run `python -m pytest`, `python -m build`, and `python -m twine check dist/*`.
3. Create a clean virtual environment, install the built wheel with supported extras, and run `tests/consumer_check.py` using that interpreter.
4. Merge to `main`, wait for the full Python and clean-consumer matrices, create an annotated `vX.Y.Z` tag, and push it.
5. The Release workflow builds validated artifacts and attaches them to a GitHub release. Verify both wheel and source archive names and checksums after completion.
6. To publish `pyrealtime-ai` to PyPI, first configure that exact project as a trusted publisher for this repository/environment, set `PYPI_PUBLISH_ENABLED=true`, and push the tag.
7. Verify publication with `pip index versions pyrealtime-ai` and a clean installation. If verification fails, documentation must continue to identify PyPI as pending.

The package is named `pyrealtime-ai` because the older `PyRealtime` name is already registered on PyPI. The import path intentionally remains `pyrealtime`.
