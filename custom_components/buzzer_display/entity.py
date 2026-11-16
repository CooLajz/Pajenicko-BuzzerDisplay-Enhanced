"""Společný popis fyzického zařízení."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .api import DeviceError

class BuzzerEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN,coordinator.entry.unique_id)},name=coordinator.entry.title,
            manufacturer="Pájeníčko / CooLajz",model="Pajenicko BuzzerDisplay Enhanced 32 × 8",
            sw_version=coordinator.info["version"],configuration_url=coordinator.client.base)

    async def send(self, path, data):
        try:
            await self.coordinator.command(path,data)
        except DeviceError as err:
            raise HomeAssistantError(str(err)) from err
