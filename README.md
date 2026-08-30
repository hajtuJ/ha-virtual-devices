# Virtual Devices for Home Assistant

Virtual Devices is a Home Assistant custom integration for composing existing
entities into higher-level virtual devices. The first supported device type is a
Virtual Gate.

> [!IMPORTANT]
> The project is in early MVP development and is not ready to control physical
> hardware. Do not install it on a production gate controller yet.

## Development status

The repository currently contains the integration scaffold and its design
specification. Implementation progress is tracked in
[`docs/docs/IMPLEMENTATION_TRACKER.md`](docs/docs/IMPLEMENTATION_TRACKER.md).

## Requirements

- Home Assistant 2026.8.0 or newer
- HACS installation as a custom integration repository

## Development

Install [uv](https://docs.astral.sh/uv/) and run:

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy custom_components tests
```

The complete product and safety documentation starts in
[`docs/README.md`](docs/README.md).

## Safety

This integration will control physical gates. Startup, reload, restore, migration,
and reconfiguration must never trigger movement. Physical safety systems remain
mandatory and must never be bypassed by software.

## License

[MIT](LICENSE)
