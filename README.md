# github-api-lite

[![PyPI version](https://img.shields.io/pypi/v/trysac-github-api-lite)](https://pypi.org/project/trysac-github-api-lite/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-github-api-lite)](LICENSE)
[![CI](https://github.com/Trysac/u154-github-api-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u154-github-api-lite/actions/workflows/ci.yml)

Minimal GitHub REST client over an injected transport: Link header pagination, primary and secondary rate limit handling and same-origin page links

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-github-api-lite
# or
uv add trysac-github-api-lite
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import github_api_lite

# normalize() trims surrounding whitespace and lower-cases the text.
print(github_api_lite.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    github_api_lite.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
