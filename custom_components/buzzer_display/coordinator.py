"""Sledování hodnot, obnova spojení a sdílený přenos pixelů."""
from __future__ import annotations
import asyncio
from datetime import timedelta
import logging
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from .api import DeviceError, AuthenticationError
from .const import DOMAIN
from .formatting import format_page

_LOGGER = logging.getLogger(__name__)

class BuzzerCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client, info):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=30), config_entry=entry)
        self.entry = entry
        self.client = client
        self.info = info
        self.send_lock = asyncio.Lock()
        self.listeners = set()
        self.frame_task = None
        self.pending_update = None

    async def _async_update_data(self):
        try:
            await self.publish()
            return await self.client.request("GET", "/api/state")
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except DeviceError as err:
            raise UpdateFailed(str(err)) from err

    async def publish(self):
        async with self.send_lock:
            pages = []
            for config in self.entry.options.get("pages", []):
                state = self.hass.states.get(config.get("entity_id", ""))
                pages.append(format_page(config, state.state if state else None, state.attributes if state else {}))
            if not pages:
                pages = [format_page({"id":"setup", "text":"Nastavte obrazovky v Home Assistantu"},None,{})]
            await self.client.request("PUT", "/api/playlist", {"pages": pages, "ttl_ms": 90000})

    def watch_states(self):
        ids = [p["entity_id"] for p in self.entry.options.get("pages",[]) if p.get("entity_id")]
        def changed(event):
            if self.pending_update:
                self.pending_update()
            self.pending_update = async_call_later(self.hass, .2, update)
        async def update(_):
            self.pending_update = None
            await self.async_request_refresh()
        if ids:
            self.entry.async_on_unload(async_track_state_change_event(self.hass, ids, changed))

    def subscribe(self, listener):
        self.listeners.add(listener)
        if self.frame_task is None:
            self.frame_task = self.hass.async_create_background_task(self._frames(), "Pajenicko BuzzerDisplay Enhanced: obraz")
        def remove():
            self.listeners.discard(listener)
            if not self.listeners and self.frame_task:
                self.frame_task.cancel()
                self.frame_task = None
        return remove

    async def _frames(self):
        delay = 1
        while self.listeners:
            try:
                async for frame in self.client.frames():
                    delay = 1
                    for listener in tuple(self.listeners):
                        listener({"available": True, **frame})
            except DeviceError:
                _LOGGER.debug("Přenos obrazu se znovu připojí")
            for listener in tuple(self.listeners):
                listener({"available": False})
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def command(self, path, data):
        await self.client.request("POST", path, data)
        await asyncio.sleep(.05)
        await self.async_request_refresh()

    async def shutdown(self):
        if self.pending_update:
            self.pending_update()
            self.pending_update = None
        self.listeners.clear()
        if self.frame_task:
            self.frame_task.cancel()
            try:
                await self.frame_task
            except asyncio.CancelledError:
                pass
            self.frame_task = None
