"""Párování a správa obrazovek přes uživatelské rozhraní HA."""
from __future__ import annotations
from copy import deepcopy
from uuid import uuid4
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import BuzzerClient, DeviceError, AuthenticationError, normalize_host
from .const import DOMAIN, EFFECTS, BLINKS

class BuzzerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _host = ""
    _info = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            try:
                self._host = user_input["host"].strip()
                client = BuzzerClient(async_get_clientsession(self.hass), self._host)
                self._info = await client.info()
                await self.async_set_unique_id(self._info["id"])
                self._abort_if_unique_id_configured(updates={"host": self._host})
                return await self.async_step_pair()
            except (DeviceError, ValueError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required("host", default=self._host): str}), errors=errors)

    async def async_step_zeroconf(self, discovery_info):
        self._host = str(discovery_info.host)
        try:
            self._info = await BuzzerClient(async_get_clientsession(self.hass), self._host).info()
        except (DeviceError, ValueError):
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(self._info["id"])
        self._abort_if_unique_id_configured(updates={"host": self._host})
        self.context["title_placeholders"] = {"name": self._info["name"]}
        return await self.async_step_pair()

    async def async_step_pair(self, user_input=None):
        errors = {}
        if user_input:
            try:
                client = BuzzerClient(async_get_clientsession(self.hass), self._host)
                info = await client.info()
                if info["id"] != self._info["id"]:
                    return self.async_abort(reason="wrong_device")
                result = await client.request("POST", "/api/pair", {"code": user_input["code"]})
                token = result.get("token")
                if not isinstance(token, str) or len(token) != 32:
                    raise DeviceError("Neplatný klíč.")
                data = {"host": self._host, "token": token, "device_id": info["id"]}
                if self.source == "reauth":
                    return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=data)
                return self.async_create_entry(title=f"Pajenicko BuzzerDisplay Enhanced {info['id'][-6:]}", data=data)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except (DeviceError, ValueError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="pair", data_schema=vol.Schema({vol.Required("code"): str}), errors=errors)

    async def async_step_reauth(self, entry_data):
        self._host = entry_data["host"]
        self._info = {"id": entry_data["device_id"]}
        return await self.async_step_pair()

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input:
            try:
                client = BuzzerClient(async_get_clientsession(self.hass), user_input["host"], entry.data["token"])
                info = await client.info()
                if info["id"] != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                await client.request("GET", "/api/state")
                return self.async_update_reload_and_abort(entry, data_updates={"host": user_input["host"]})
            except (DeviceError, ValueError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="reconfigure", data_schema=vol.Schema({vol.Required("host", default=entry.data["host"]): str}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BuzzerOptionsFlow()

class BuzzerOptionsFlow(config_entries.OptionsFlow):
    _editing = None

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["add_page", "edit_page", "remove_page"])

    def _pages(self):
        return deepcopy(self.config_entry.options.get("pages", []))

    async def async_step_add_page(self, user_input=None):
        if len(self._pages()) >= 8:
            return self.async_abort(reason="too_many_pages")
        self._editing = None
        return await self.async_step_page(user_input)

    async def async_step_edit_page(self, user_input=None):
        pages = self._pages()
        if not pages:
            return await self.async_step_add_page()
        if user_input:
            self._editing = user_input["page"]
            return await self.async_step_page()
        return self.async_show_form(step_id="edit_page", data_schema=self._selection(pages))

    def _selection(self, pages):
        return vol.Schema({vol.Required("page"): selector.SelectSelector(selector.SelectSelectorConfig(
            options=[{"value":p["id"], "label":p.get("text") or p.get("entity_id") or p["id"]} for p in pages]))})

    async def async_step_remove_page(self, user_input=None):
        pages = self._pages()
        if not pages:
            return self.async_abort(reason="no_pages")
        if user_input:
            return self.async_create_entry(title="", data={"pages":[p for p in pages if p["id"] != user_input["page"]]})
        return self.async_show_form(step_id="remove_page", data_schema=self._selection(pages))

    async def async_step_page(self, user_input=None):
        pages = self._pages()
        current = next((p for p in pages if p["id"] == self._editing), {})
        errors = {}
        if user_input:
            if not user_input.get("entity_id") and not user_input.get("text", "").strip():
                errors["base"] = "empty_page"
            elif len(user_input.get("text", "").encode()) > 200:
                errors["base"] = "text_too_long"
            else:
                value = dict(user_input, id=self._editing or uuid4().hex[:12])
                if self._editing:
                    pages = [value if p["id"] == self._editing else p for p in pages]
                else:
                    pages.append(value)
                return self.async_create_entry(title="", data={"pages": pages})
        schema = {
            vol.Optional("text", default=current.get("text", "")): str,
            vol.Optional("entity_id", **({"default":current["entity_id"]} if current.get("entity_id") else {})): selector.EntitySelector(),
            vol.Required("decimals", default=current.get("decimals", 1)): vol.All(vol.Coerce(int), vol.Range(min=0,max=3)),
            vol.Required("show_unit", default=current.get("show_unit", True)): bool,
            vol.Required("hold_seconds", default=current.get("hold_seconds", 5)): vol.All(vol.Coerce(int), vol.Range(min=1,max=300)),
            vol.Required("speed", default=current.get("speed", 20)): vol.All(vol.Coerce(int), vol.Range(min=0,max=80)),
            vol.Required("scroll_right", default=current.get("scroll_right", False)): bool,
            vol.Required("enter", default=current.get("enter", "none")): selector.SelectSelector(selector.SelectSelectorConfig(options=EFFECTS, translation_key="effect")),
            vol.Required("exit", default=current.get("exit", "none")): selector.SelectSelector(selector.SelectSelectorConfig(options=EFFECTS, translation_key="effect")),
            vol.Required("transition_ms", default=current.get("transition_ms",600)): vol.All(vol.Coerce(int),vol.Range(min=100,max=5000)),
            vol.Required("blink", default=current.get("blink", "none")): selector.SelectSelector(selector.SelectSelectorConfig(options=BLINKS,translation_key="blink")),
            vol.Required("blink_ms", default=current.get("blink_ms",1000)): vol.All(vol.Coerce(int),vol.Range(min=200,max=10000)),
            vol.Required("invert", default=current.get("invert", False)): bool,
        }
        return self.async_show_form(step_id="page",data_schema=vol.Schema(schema), errors=errors)
