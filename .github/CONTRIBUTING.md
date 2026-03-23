# Contributing

## AI Contributions
All AI Contributions are banned for Fluxer.py, this is because many people do not understand what AI produces. No matter the size of the change, we will reject any AI contributions.

## Format
Contributions are always welcome, however there are a few rules that should be followed when submitting pull requests:
1. Every change must be **under the `development` branch**, this is done so that the source code always remains in a stable state.
2. Your pull request should have as a **title as a short** description of the changes.
3. The pull request **body should contain a longer description** of the changes, why they are needed and optionally the issue they are solving.
4. As stated above, any contribution featuring **AI generated work will be rejected**.
5. You must follow the [Pull Request Template](https://github.com/akarealemil/fluxer.py/blob/development/.github/PULL_REQUEST_TEMPLATE.md)

## Environment

We use `uv` for dependency management.

```sh
git clone https://github.com/akarealemil/fluxer.py.git
cd fluxer.py
uv sync --dev
```

This will create a `.venv` and install development dependencies.

## Before making a Pull Request
Every Pull Request is automatically checked through a workflow for formatting and type checking before being merged into the development branch, if you want to make sure your PR is not going to fail those checks, you can run these:

- **For format checking**: `uv run ruff format --check`
  - (it should say something like *"30 files already formatted"*)
- **For type checking**: `uv run pyright .`
  - (it should say *"0 errors, 0 warnings, 0 informations"*)

> [!TIP]
> If the format check fails, you can fix it by running `uv run ruff format`
