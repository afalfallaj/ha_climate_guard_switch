"""Global test fixtures — sys.modules stubs for the `homeassistant` package.

We stub `homeassistant` instead of depending on the heavy, HA-core-version-pinned
`pytest-homeassistant-custom-component` package (same approach as `smart_garage_door`).
Only the pieces this integration actually imports are provided, as real minimal
classes where behavior (attribute access, inheritance, generics) matters and
MagicMock otherwise.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import pathlib
import sys
from typing import Any, Generic, TypeVar
from unittest.mock import AsyncMock, MagicMock

# Make the repo root importable so tests can `import custom_components.climate_guard_switch...`
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# homeassistant.core
# ---------------------------------------------------------------------------


class _State:
    """Minimal stand-in for homeassistant.core.State."""

    def __init__(self, state: str, attributes: dict[str, Any] | None = None) -> None:
        self.state = state
        self.attributes = attributes or {}


class _StateMachine:
    """Minimal stand-in for homeassistant.core.StateMachine."""

    def __init__(self) -> None:
        self._states: dict[str, _State] = {}

    def get(self, entity_id: str) -> _State | None:
        return self._states.get(entity_id)

    def set(self, entity_id: str, state: str, attributes: dict[str, Any] | None = None) -> None:
        self._states[entity_id] = _State(state, attributes)


class _HomeAssistant:
    """Minimal stand-in for homeassistant.core.HomeAssistant."""

    def __init__(self) -> None:
        self.states = _StateMachine()
        self.services = MagicMock()
        self.services.async_call = AsyncMock()
        self.config_entries = MagicMock()
        self._tasks: list[asyncio.Task] = []

    def async_create_task(self, coro):
        task = asyncio.ensure_future(coro)
        self._tasks.append(task)
        return task


_ha_core = MagicMock()
_ha_core.HomeAssistant = _HomeAssistant
_ha_core.State = _State
_ha_core.Event = MagicMock
_ha_core.callback = lambda f: f  # passthrough decorator

# ---------------------------------------------------------------------------
# homeassistant.const
# ---------------------------------------------------------------------------

_ha_const = MagicMock()
_ha_const.ATTR_ENTITY_ID = "entity_id"
_ha_const.SERVICE_TURN_OFF = "turn_off"
_ha_const.SERVICE_TURN_ON = "turn_on"
_ha_const.STATE_ON = "on"
_ha_const.Platform = MagicMock()

# ---------------------------------------------------------------------------
# homeassistant.components.climate
# ---------------------------------------------------------------------------

_ha_components_climate = MagicMock()
_ha_components_climate.ATTR_TEMPERATURE = "temperature"

# ---------------------------------------------------------------------------
# homeassistant.helpers.event — coordinator.py schedules via these, but tests
# call the coordinator's internal methods directly rather than relying on real
# timers, so plain no-op-returning mocks are enough.
# ---------------------------------------------------------------------------

_ha_event = MagicMock()
_ha_event.async_track_state_change_event = MagicMock(return_value=MagicMock())
_ha_event.async_track_time_interval = MagicMock(return_value=MagicMock())

# ---------------------------------------------------------------------------
# homeassistant.helpers.config_validation / selector — only imported, never
# exercised by the tests (which pass already-parsed user_input dicts and never
# render/validate the voluptuous schema), so MagicMock is enough.
# ---------------------------------------------------------------------------

_ha_cv = MagicMock()
_ha_selector = MagicMock()

# ---------------------------------------------------------------------------
# homeassistant.helpers.update_coordinator — a real minimal DataUpdateCoordinator
# so ClimateGuardCoordinator's inheritance (incl. `DataUpdateCoordinator[dict]`
# generic subscription) and `async_set_updated_data` behave like the real thing.
# ---------------------------------------------------------------------------

_T = TypeVar("_T")


class _DataUpdateCoordinator(Generic[_T]):
    """Minimal stand-in for homeassistant.helpers.update_coordinator.DataUpdateCoordinator."""

    def __init__(
        self,
        hass,
        logger,
        *,
        config_entry=None,
        name=None,
        update_interval=None,
        **kwargs,
    ) -> None:
        self.hass = hass
        self.logger = logger
        self.config_entry = config_entry
        self.name = name
        self.update_interval = update_interval
        self.data: _T | None = None
        self._listeners: list[Any] = []

    def async_set_updated_data(self, data: _T) -> None:
        self.data = data
        self.async_update_listeners()

    def async_update_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()

    def async_add_listener(self, update_callback, context: Any = None):
        self._listeners.append(update_callback)

        def _remove() -> None:
            self._listeners.remove(update_callback)

        return _remove


_ha_update_coordinator = MagicMock()
_ha_update_coordinator.DataUpdateCoordinator = _DataUpdateCoordinator

# ---------------------------------------------------------------------------
# homeassistant.config_entries — just enough of ConfigEntry/ConfigFlow/
# OptionsFlow(WithReload) for our config_flow.py and coordinator.py to subclass
# and exercise, without depending on the real flow-manager machinery.
# ---------------------------------------------------------------------------


class AbortFlow(Exception):
    """Minimal stand-in for homeassistant.data_entry_flow.AbortFlow."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _ConfigEntry:
    """Minimal stand-in for homeassistant.config_entries.ConfigEntry."""

    def __init__(
        self,
        data=None,
        options=None,
        entry_id="test_entry",
        title="Test",
        unique_id=None,
        version=1,
    ) -> None:
        self.data = data or {}
        self.options = options or {}
        self.entry_id = entry_id
        self.title = title
        self.unique_id = unique_id
        self.version = version
        self.runtime_data = None
        self.update_listeners: list[Any] = []

    def add_update_listener(self, listener):
        self.update_listeners.append(listener)
        return lambda: self.update_listeners.remove(listener)

    def async_on_unload(self, _unsub) -> None:
        return None


class _ConfigEntriesRegistry:
    """Minimal stand-in for hass.config_entries — just enough for unique_id
    duplicate-detection and the async_update_entry migration helper."""

    def __init__(self) -> None:
        self._entries: list[_ConfigEntry] = []

    def async_entry_for_domain_unique_id(self, _domain, unique_id):
        for entry in self._entries:
            if entry.unique_id == unique_id:
                return entry
        return None

    def async_update_entry(self, entry, *, unique_id=None, version=None, **_kwargs) -> bool:
        changed = False
        if unique_id is not None and entry.unique_id != unique_id:
            entry.unique_id = unique_id
            changed = True
        if version is not None and entry.version != version:
            entry.version = version
            changed = True
        return changed


class _FlowHandlerBase:
    """Shared bits of homeassistant.config_entries.ConfigFlow/OptionsFlow."""

    def async_show_form(self, *, step_id, data_schema=None, errors=None):
        return {"type": "form", "step_id": step_id, "data_schema": data_schema, "errors": errors or {}}

    def async_create_entry(self, *, title=None, data=None):
        entry = _ConfigEntry(data=data, title=title, unique_id=getattr(self, "_unique_id", None))
        if getattr(self, "hass", None) is not None:
            self.hass.config_entries._entries.append(entry)
        return {"type": "create_entry", "title": title, "data": data}

    def async_abort(self, *, reason):
        return {"type": "abort", "reason": reason}


class _ConfigFlow(_FlowHandlerBase):
    """Minimal stand-in for homeassistant.config_entries.ConfigFlow."""

    def __init_subclass__(cls, *, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.domain = domain

    def __init__(self) -> None:
        self.hass = _HomeAssistant()
        self.hass.config_entries = _ConfigEntriesRegistry()
        self.context: dict[str, Any] = {}
        self._unique_id: str | None = None

    async def async_set_unique_id(self, unique_id, *, raise_on_progress: bool = True):
        self._unique_id = unique_id
        self.context["unique_id"] = unique_id
        return None

    def _abort_if_unique_id_configured(self) -> None:
        if self._unique_id is None:
            return
        existing = self.hass.config_entries.async_entry_for_domain_unique_id(
            getattr(self, "domain", None), self._unique_id
        )
        if existing is not None and existing is not getattr(self, "_reconfigure_entry", None):
            raise AbortFlow("already_configured")

    def _get_reconfigure_entry(self) -> _ConfigEntry:
        return self._reconfigure_entry

    def async_update_reload_and_abort(self, entry, *, title=None, data_updates=None, **_kwargs):
        if data_updates is not None:
            entry.data = {**entry.data, **data_updates}
        if title is not None:
            entry.title = title
        return {"type": "abort", "reason": "reconfigure_successful"}


class _OptionsFlow(_FlowHandlerBase):
    """Minimal stand-in for homeassistant.config_entries.OptionsFlow."""

    config_entry: _ConfigEntry


class _OptionsFlowWithReload(_OptionsFlow):
    """Minimal stand-in for homeassistant.config_entries.OptionsFlowWithReload."""

    automatic_reload = True


_ha_config_entries = MagicMock()
_ha_config_entries.ConfigEntry = _ConfigEntry
_ha_config_entries.ConfigFlow = _ConfigFlow
_ha_config_entries.OptionsFlow = _OptionsFlow
_ha_config_entries.OptionsFlowWithReload = _OptionsFlowWithReload
_ha_config_entries.ConfigFlowResult = dict

_ha_data_entry_flow = MagicMock()
_ha_data_entry_flow.AbortFlow = AbortFlow

# ---------------------------------------------------------------------------
# homeassistant.util.dt — real now() so cooldown/run-limit math works
# ---------------------------------------------------------------------------

_ha_util_dt = MagicMock()
_ha_util_dt.now = lambda: _dt.datetime.now(_dt.timezone.utc)
_ha_util_dt.parse_datetime = _dt.datetime.fromisoformat

_ha_util = MagicMock()
_ha_util.dt = _ha_util_dt

# ---------------------------------------------------------------------------
# Assemble sys.modules
# ---------------------------------------------------------------------------

_ha_helpers = MagicMock()
_ha_helpers.event = _ha_event
_ha_helpers.config_validation = _ha_cv
_ha_helpers.selector = _ha_selector
_ha_helpers.update_coordinator = _ha_update_coordinator

_ha_top = MagicMock()
_ha_top.config_entries = _ha_config_entries  # `from homeassistant import config_entries`

_ha_components = MagicMock()
_ha_components.climate = _ha_components_climate

sys.modules.update(
    {
        "homeassistant": _ha_top,
        "homeassistant.core": _ha_core,
        "homeassistant.const": _ha_const,
        "homeassistant.config_entries": _ha_config_entries,
        "homeassistant.data_entry_flow": _ha_data_entry_flow,
        "homeassistant.helpers": _ha_helpers,
        "homeassistant.helpers.event": _ha_event,
        "homeassistant.helpers.config_validation": _ha_cv,
        "homeassistant.helpers.selector": _ha_selector,
        "homeassistant.helpers.update_coordinator": _ha_update_coordinator,
        "homeassistant.components": _ha_components,
        "homeassistant.components.climate": _ha_components_climate,
        "homeassistant.util": _ha_util,
        "homeassistant.util.dt": _ha_util_dt,
    }
)
