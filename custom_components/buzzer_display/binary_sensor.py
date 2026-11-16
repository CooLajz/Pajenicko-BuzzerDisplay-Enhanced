"""Rozlišení starých údajů od aktuálních."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.entity import EntityCategory
from .entity import BuzzerEntity
async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([StaleSensor(entry.runtime_data,"stale","Zastaralé údaje")])
class StaleSensor(BuzzerEntity,BinarySensorEntity):
    _attr_device_class=BinarySensorDeviceClass.PROBLEM
    _attr_entity_category=EntityCategory.DIAGNOSTIC
    @property
    def is_on(self):
        return self.coordinator.data.get("stale",False)
