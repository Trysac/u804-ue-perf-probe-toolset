# Stack

## Used

| Tool | Why |
|---|---|
| Python >= 3.10 | Lowest version that supports the modern typing syntax used in the code (for example `int | float` in `isinstance`). |
| Python standard library | The only runtime dependency. Modules used include csv, json, math, threading, dataclasses, pathlib, random and contextlib. |
| hypothesis (dev only, >=6.100,<7) | Property tests with `derandomize=True`. |
| pytest and pytest-cov | Test runner and coverage. |
| uv | Environment and build management. |
| hatchling | Build backend. |
| ruff | Lint and format. |
| mypy | Static type checking. |
| gitleaks | Secret scanning. |

## Discarded

| Tool | Why not |
|---|---|
| Poetry | uv covers the same needs with standard dependency groups. |
| black, isort and flake8 | ruff covers them in one tool. |
| tox and nox | The local check script is enough for the single supported environment. |
| Shell scripts for gates | Not portable to Windows. |
