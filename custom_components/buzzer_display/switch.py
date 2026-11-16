"""Napájení obrazu a montážní orientace."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory
from .entity import BuzzerEntity
async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([BuzzerSwitch(entry.runtime_data,"enabled","Displej"),BuzzerSwitch(entry.runtime_data,"rotation","Otočení o 180°")])
class BuzzerSwitch(BuzzerEntity,SwitchEntity):
    def __init__(self,coordinator,key,name):
        super().__init__(coordinator,key,name);self.key=key
        if key=="rotation":self._attr_entity_category=EntityCategory.CONFIG
    @property
    def is_on(self):
        return self.coordinator.data.get(self.key,True)
    async def async_turn_on(self,**kwargs):
        await self.send("/api/settings",{self.key:True})
    async def async_turn_off(self,**kwargs):
        await self.send("/api/settings",{self.key:False})
