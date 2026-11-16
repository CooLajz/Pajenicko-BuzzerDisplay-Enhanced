"""Jas matice v šestnácti hardwarových úrovních."""
from homeassistant.components.number import NumberEntity, NumberMode
from .entity import BuzzerEntity
async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([Brightness(entry.runtime_data,"brightness","Jas")])
class Brightness(BuzzerEntity,NumberEntity):
    _attr_native_min_value=0
    _attr_native_max_value=15
    _attr_native_step=1
    _attr_mode=NumberMode.SLIDER
    _attr_icon="mdi:brightness-6"
    @property
    def native_value(self):
        return self.coordinator.data.get("target_brightness",4)
    async def async_set_native_value(self,value):
        await self.send("/api/settings",{"brightness":int(value)})
