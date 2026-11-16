"""Diagnostika připojení."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.entity import EntityCategory
from .entity import BuzzerEntity

async def async_setup_entry(hass,entry,async_add_entities):
    async_add_entities([BuzzerSensor(entry.runtime_data,"rssi","Síla signálu","dBm",SensorDeviceClass.SIGNAL_STRENGTH),
                        BuzzerSensor(entry.runtime_data,"uptime","Doba běhu","s",SensorDeviceClass.DURATION)])

class BuzzerSensor(BuzzerEntity,SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self,coordinator,key,name,unit,device_class):
        super().__init__(coordinator,key,name)
        self.key=key;self._attr_native_unit_of_measurement=unit;self._attr_device_class=device_class
    @property
    def native_value(self):
        return self.coordinator.data.get(self.key)
