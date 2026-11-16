"""Návrat k běžným obrazovkám."""
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from .api import DeviceError
from .entity import BuzzerEntity
async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([Clear(entry.runtime_data,"clear","Ukončit oznámení")])
class Clear(BuzzerEntity,ButtonEntity):
    _attr_icon="mdi:message-off-outline"
    async def async_press(self):
        try:await self.coordinator.client.request("DELETE","/api/notification")
        except DeviceError as err:raise HomeAssistantError(str(err)) from err
