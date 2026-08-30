# Repository Bootstrap Checklist

The implementation agent should create and validate the actual versions of these files:

```text
.gitignore
LICENSE
README.md
AGENTS.md
hacs.json
pyproject.toml

custom_components/
└── virtual_devices/
    ├── __init__.py
    ├── manifest.json
    ├── const.py
    ├── config_flow.py
    ├── strings.json
    └── translations/
        ├── en.json
        └── pl.json

tests/
└── ...

.github/
└── workflows/
    ├── test.yml
    └── validate.yml
```

## Suggested repository slug

```text
ha-virtual-devices
```

or:

```text
home-assistant-virtual-devices
```

Prefer the second if discoverability is more important than brevity.

## Integration domain

```text
virtual_devices
```

Do not change the domain after public releases unless absolutely necessary.

## HACS category

The project should be structured as a HACS custom integration.

Verify current `hacs.json` requirements before committing.

## Versioning

Use semantic versioning.

Suggested early versions:

```text
0.1.0
0.2.0
...
1.0.0
```

Do not use `1.0.0` until configuration migration and state restore behavior are stable.

## CI

At minimum validate:

```text
Python syntax
pytest
lint
HACS validation
Home Assistant integration structure
```

Add dependency caching only after the workflow is correct.
