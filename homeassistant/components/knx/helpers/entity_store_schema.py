"""KNX entity store schema."""
import voluptuous as vol

from homeassistant.components.switch import (
    DEVICE_CLASSES_SCHEMA as SWITCH_DEVICE_CLASSES_SCHEMA,
)
from homeassistant.helpers.entity import ENTITY_CATEGORIES_SCHEMA

from ..schema import ga_list_validator, sync_state_validator

BASE_ENTITY_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Required("device_id"): vol.Maybe(str),
        vol.Required("entity_category"): vol.Maybe(ENTITY_CATEGORIES_SCHEMA),
        vol.Required("sync_state"): sync_state_validator,
    }
)
SWITCH_SCHEMA = BASE_ENTITY_SCHEMA.extend(
    {
        vol.Required("device_class"): vol.Maybe(SWITCH_DEVICE_CLASSES_SCHEMA),
        vol.Required("invert"): bool,
        vol.Required("switch_address"): ga_list_validator,
        vol.Required("switch_state_address"): ga_list_validator,
        vol.Required("respond_to_read"): bool,
    }
)
CREATE_ENTITY_SCHEMA = vol.Any(
    SWITCH_SCHEMA.extend({vol.Required("platform"): "switch"})
)
UPDATE_ENTITY_SCHEMA = vol.Any(
    SWITCH_SCHEMA.extend(
        {
            vol.Required("platform"): "switch",
            vol.Required("unique_id"): str,
        }
    )
)
# TODO: use cv.key_value_schemas
