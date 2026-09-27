# Releasing PyRealtime

1. Update `__version__`, `project.version`, and `CHANGELOG.md` to the same SemVer value.
2. Run `python -m pytest`, `python -m build`, and `python -m twine check dist/*`.
3. Merge to `main`, create an annotated `vX.Y.Z` tag, and push it.
4. The Release workflow builds signed-by-CI artifacts and attaches them to a GitHub release.
5. To publish `pyrealtime-ai` to PyPI, configure that project as a trusted publisher for this repository/environment, set the repository variable `PYPI_PUBLISH_ENABLED=true`, and push the tag.

The package is named `pyrealtime-ai` because the older `PyRealtime` name is already registered on PyPI. The import path intentionally remains `pyrealtime`.
