"""KNX Websocket API."""
from __future__ import annotations

from typing import TYPE_CHECKING, Final

import knx_frontend as knx_panel
import voluptuous as vol
from xknxproject.exceptions import XknxProjectException

from homeassistant.components import panel_custom, websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.util.uuid import random_uuid_hex

from .const import DOMAIN
from .storage.config_store import ConfigStoreException
from .storage.entity_store_schema import (
    CREATE_ENTITY_BASE_SCHEMA,
    ENTITY_STORE_DATA_SCHEMA,
    UPDATE_ENTITY_BASE_SCHEMA,
)
from .telegrams import TelegramDict

if TYPE_CHECKING:
    from . import KNXModule


URL_BASE: Final = "/knx_static"


async def register_panel(hass: HomeAssistant) -> None:
    """Register the KNX Panel and Websocket API."""
    websocket_api.async_register_command(hass, ws_info)
    websocket_api.async_register_command(hass, ws_project_file_process)
    websocket_api.async_register_command(hass, ws_project_file_remove)
    websocket_api.async_register_command(hass, ws_group_monitor_info)
    websocket_api.async_register_command(hass, ws_subscribe_telegram)
    websocket_api.async_register_command(hass, ws_get_knx_project)
    websocket_api.async_register_command(hass, ws_create_entity)
    websocket_api.async_register_command(hass, ws_update_entity)
    websocket_api.async_register_command(hass, ws_delete_entity)
    websocket_api.async_register_command(hass, ws_get_entity_config)
    websocket_api.async_register_command(hass, ws_get_entity_entries)
    websocket_api.async_register_command(hass, ws_create_device)

    if DOMAIN not in hass.data.get("frontend_panels", {}):
        hass.http.register_static_path(
            URL_BASE,
            path=knx_panel.locate_dir(),
            cache_headers=knx_panel.is_prod_build,
        )
        await panel_custom.async_register_panel(
            hass=hass,
            frontend_url_path=DOMAIN,
            webcomponent_name=knx_panel.webcomponent_name,
            sidebar_title=DOMAIN.upper(),
            sidebar_icon="mdi:bus-electric",
            module_url=f"{URL_BASE}/{knx_panel.entrypoint_js}",
            embed_iframe=True,
            require_admin=True,
        )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "knx/info",
    }
)
@callback
def ws_info(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Handle get info command."""
    knx: KNXModule = hass.data[DOMAIN]

    _project_info = None
    if project_info := knx.project.info:
        _project_info = {
            "name": project_info["name"],
            "last_modified": project_info["last_modified"],
            "tool_version": project_info["tool_version"],
            "xknxproject_version": project_info["xknxproject_version"],
        }

    connection.send_result(
        msg["id"],
        {
            "version": knx.xknx.version,
            "connected": knx.xknx.connection_manager.connected.is_set(),
            "current_address": str(knx.xknx.current_address),
            "project": _project_info,
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "knx/get_knx_project",
    }
)
@websocket_api.async_response
async def ws_get_knx_project(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Handle get KNX project."""
    knx: KNXModule = hass.data[DOMAIN]
    knxproject = await knx.project.get_knxproject()
    connection.send_result(
        msg["id"],
        {
            "project_loaded": knx.project.loaded,
            "knxproject": knxproject,
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "knx/project_file_process",
        vol.Required("file_id"): str,
        vol.Required("password"): str,
    }
)
@websocket_api.async_response
async def ws_project_file_process(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Handle get info command."""
    knx: KNXModule = hass.data[DOMAIN]
    try:
        await knx.project.process_project_file(
            file_id=msg["file_id"],
            password=msg["password"],
        )
    except (ValueError, XknxProjectException) as err:
        # ValueError could raise from file_upload integration
        connection.send_error(
            msg["id"], websocket_api.const.ERR_HOME_ASSISTANT_ERROR, str(err)
        )
        return

    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "knx/project_file_remove",
    }
)
@websocket_api.async_response
async def ws_project_file_remove(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Handle get info command."""
    knx: KNXModule = hass.data[DOMAIN]
    await knx.project.remove_project_file()
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "knx/group_monitor_info",
    }
)
@callback
def ws_group_monitor_info(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Handle get info command of group monitor."""
    knx: KNXModule = hass.data[DOMAIN]
    recent_telegrams = [*knx.telegrams.recent_telegrams]
    connection.send_result(
        msg["id"],
        {
            "project_loaded": knx.project.loaded,
            "recent_telegrams": recent_telegrams,
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "knx/subscribe_telegrams",
    }
)
@callback
def ws_subscribe_telegram(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Subscribe to incoming and outgoing KNX telegrams."""
    knx: KNXModule = hass.data[DOMAIN]

    @callback
    def forward_telegram(telegram: TelegramDict) -> None:
        """Forward telegram to websocket subscription."""
        connection.send_event(
            msg["id"],
            telegram,
        )

    connection.subscriptions[msg["id"]] = knx.telegrams.async_listen_telegram(
        action=forward_telegram,
        name="KNX GroupMonitor subscription",
    )
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    vol.All(
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): "knx/create_entity",
                **CREATE_ENTITY_BASE_SCHEMA,
            }
        ),
        ENTITY_STORE_DATA_SCHEMA,
    )
)
@websocket_api.async_response
async def ws_create_entity(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Create entity in entity store and load it."""
    knx: KNXModule = hass.data[DOMAIN]
    try:
        await knx.config_store.create_entitiy(msg["platform"], msg["data"])
    except ConfigStoreException as err:
        connection.send_error(
            msg["id"], websocket_api.const.ERR_HOME_ASSISTANT_ERROR, str(err)
        )
        return
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    vol.All(
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): "knx/update_entity",
                **UPDATE_ENTITY_BASE_SCHEMA,
            }
        ),
        ENTITY_STORE_DATA_SCHEMA,
    )
)
@websocket_api.async_response
async def ws_update_entity(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Update entity in entity store and reload it."""
    knx: KNXModule = hass.data[DOMAIN]
    try:
        await knx.config_store.update_entity(
            msg["platform"], msg["unique_id"], msg["data"]
        )
    except ConfigStoreException as err:
        connection.send_error(
            msg["id"], websocket_api.const.ERR_HOME_ASSISTANT_ERROR, str(err)
        )
        return
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "knx/delete_entity",
        vol.Required("entity_id"): str,
    }
)
@websocket_api.async_response
async def ws_delete_entity(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Delete entity from entity store and remove it."""
    knx: KNXModule = hass.data[DOMAIN]
    try:
        await knx.config_store.delete_entity(msg["entity_id"])
    except ConfigStoreException as err:
        connection.send_error(
            msg["id"], websocket_api.const.ERR_HOME_ASSISTANT_ERROR, str(err)
        )
        return
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "knx/get_entity_entries",
    }
)
@callback
def ws_get_entity_entries(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Get entities configured from entity store."""
    knx: KNXModule = hass.data[DOMAIN]
    entity_entries = [
        entry.extended_dict for entry in knx.config_store.get_entity_entries()
    ]
    connection.send_result(msg["id"], entity_entries)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "knx/get_entity_config",
        vol.Required("entity_id"): str,
    }
)
@callback
def ws_get_entity_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Get entity configuration from entity store."""
    knx: KNXModule = hass.data[DOMAIN]
    try:
        config = knx.config_store.get_entity_config(msg["entity_id"])
    except KeyError:
        connection.send_error(
            msg["id"], websocket_api.const.ERR_HOME_ASSISTANT_ERROR, "Entity not found."
        )
        return
    connection.send_result(msg["id"], config)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "knx/create_device",
        vol.Required("name"): str,
        vol.Optional("area_id"): str,
    }
)
@callback
def ws_create_device(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Create a new KNX device."""
    knx: KNXModule = hass.data[DOMAIN]
    identifier = f"knx_vdev_{random_uuid_hex()}"
    device_registry = dr.async_get(hass)
    _device = device_registry.async_get_or_create(
        config_entry_id=knx.entry.entry_id,
        manufacturer="KNX",
        name=msg["name"],
        identifiers={(DOMAIN, identifier)},
    )
    device_registry.async_update_device(
        _device.id,
        area_id=msg.get("area_id") or UNDEFINED,
        configuration_url=f"homeassistant://knx/entities/view?device_id={_device.id}",
    )
    connection.send_result(msg["id"], _device.dict_repr)
