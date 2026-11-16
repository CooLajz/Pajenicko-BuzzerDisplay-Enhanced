"""Rychlá zpráva na deset sekund."""
import unicodedata
from homeassistant.components.text import TextEntity
from homeassistant.exceptions import HomeAssistantError
from .entity import BuzzerEntity
async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([Message(entry.runtime_data,"message","Zpráva na 10 sekund")])
class Message(BuzzerEntity,TextEntity):
    _attr_native_min=0
    _attr_native_max=128
    _attr_native_value=""
    async def async_set_value(self,value):
        value=unicodedata.normalize("NFC",value)
        if len(value.encode())>384:raise HomeAssistantError("Text je příliš dlouhý.")
        await self.send("/api/notification",{"text":value,"duration_ms":10000,"speed":20})
        self._attr_native_value=value
        self.async_write_ha_state()
