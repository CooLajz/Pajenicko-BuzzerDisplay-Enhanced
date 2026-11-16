"""Pajenicko BuzzerDisplay Enhanced: vlastní lokální firmware, integrace a karta."""
from __future__ import annotations
from pathlib import Path
import voluptuous as vol
from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import entity_registry as er, device_registry as dr
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from .api import BuzzerClient, DeviceError
from .coordinator import BuzzerCoordinator
from .const import DOMAIN, VERSION, PLATFORMS, EFFECTS, BLINKS

async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {})
    await hass.http.async_register_static_paths([StaticPathConfig(
        f"/{DOMAIN}/buzzer-display-card.js", str(Path(__file__).parent / "frontend/buzzer-display-card.js"), False)])
    frontend.add_extra_js_url(hass, f"/{DOMAIN}/buzzer-display-card.js?v={VERSION}")
    websocket_api.async_register_command(hass, subscribe_frame)

    async def show_message(call):
        registry = dr.async_get(hass)
        device = registry.async_get(call.data["device_id"])
        if not device:
            raise HomeAssistantError("Zařízení nebylo nalezeno.")
        targets = [hass.data[DOMAIN][entry_id] for entry_id in device.config_entries if entry_id in hass.data[DOMAIN]]
        if not targets:
            raise HomeAssistantError("Vybrané zařízení není Pajenicko BuzzerDisplay Enhanced.")
        payload = {k:v for k,v in call.data.items() if k != "device_id"}
        payload["duration_ms"] = payload.pop("duration", 10) * 1000
        if len(payload["text"].encode()) > 384:
            raise HomeAssistantError("Text může mít nejvýše 384 bajtů UTF-8.")
        for coordinator in targets:
            try:
                await coordinator.command("/api/notification",payload)
            except DeviceError as err:
                raise HomeAssistantError(str(err)) from err

    hass.services.async_register(DOMAIN, "show_message", show_message, schema=vol.Schema({
        vol.Required("device_id"): str, vol.Required("text"): str,
        vol.Optional("duration", default=10): vol.All(vol.Coerce(int),vol.Range(min=1,max=300)),
        vol.Optional("speed", default=20): vol.All(vol.Coerce(int),vol.Range(min=0,max=80)),
        vol.Optional("enter",default="none"):vol.In(EFFECTS),vol.Optional("exit",default="none"):vol.In(EFFECTS),
        vol.Optional("blink",default="none"):vol.In(BLINKS),vol.Optional("invert",default=False):bool,
        vol.Optional("scroll_right",default=False):bool,
        vol.Optional("blink_ms",default=1000):vol.All(vol.Coerce(int),vol.Range(min=200,max=10000)),
        vol.Optional("transition_ms",default=600):vol.All(vol.Coerce(int),vol.Range(min=100,max=5000)),
    }))
    return True

async def async_setup_entry(hass, entry):
    client = BuzzerClient(async_get_clientsession(hass), entry.data["host"], entry.data["token"])
    try:
        info = await client.info()
        if info["id"] != entry.unique_id:
            raise DeviceError("Na této adrese odpovídá jiné zařízení.")
    except DeviceError as err:
        raise ConfigEntryNotReady(str(err)) from err
    coordinator = BuzzerCoordinator(hass, entry, client, info)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    coordinator.watch_states()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.shutdown()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True
    return False

@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe",vol.Required("entity_id"): str})
@websocket_api.async_response
async def subscribe_frame(hass, connection, msg):
    entity = er.async_get(hass).async_get(msg["entity_id"])
    if not entity or entity.platform != DOMAIN or not connection.user.permissions.check_entity(msg["entity_id"], POLICY_READ):
        connection.send_error(msg["id"], "not_found", "Entita není dostupná.")
        return
    coordinator = hass.data[DOMAIN].get(entity.config_entry_id)
    if not coordinator:
        connection.send_error(msg["id"], "not_ready", "Displej není dostupný.")
        return
    @callback
    def update(frame):
        connection.send_event(msg["id"],frame)
    connection.subscriptions[msg["id"]] = coordinator.subscribe(update)
    connection.send_result(msg["id"])
