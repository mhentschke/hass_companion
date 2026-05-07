"""MQTT discovery cleanup — removes stale entities on startup.

When clean_start is enabled, subscribes to all discovery topics for the device,
collects existing config topics, then publishes empty retained messages to remove
ghost entities before creating new ones.
"""

import logging
import time

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

DISCOVERY_PREFIX = "homeassistant"
COLLECTION_TIMEOUT = 3.0  # seconds to wait for retained messages


def clean_discovery(client: mqtt.Client, device_id: str) -> int:
    """Remove all existing discovery messages for a device.

    Subscribes to homeassistant/+/{device_id}/+/config to find all entity
    config topics, then publishes empty retained messages to each.

    Args:
        client: Connected paho MQTT client with loop_start() active.
        device_id: The device identifier used in topic paths (cleaned/slugified).

    Returns:
        Number of discovery topics cleaned.
    """
    from ha_mqtt_discoverable import clean_string

    cleaned_device_id = clean_string(device_id)
    # HA discovery topics follow: {prefix}/{component}/{device_name}/{entity}/config
    # We need to match all components and entities for our device
    pattern = f"{DISCOVERY_PREFIX}/+/{cleaned_device_id}/+/config"

    collected_topics: list[str] = []

    def on_message(cl, userdata, message):
        # Only collect non-empty retained config messages
        if message.payload and message.retain:
            collected_topics.append(message.topic)

    # Temporarily register message handler
    client.message_callback_add(pattern, on_message)
    client.subscribe(pattern, qos=1)

    # Wait for retained messages to arrive
    time.sleep(COLLECTION_TIMEOUT)

    # Unsubscribe and remove callback
    client.unsubscribe(pattern)
    client.message_callback_remove(pattern)

    if not collected_topics:
        logger.info("No existing discovery topics found for device '%s'", device_id)
        return 0

    # Publish empty retained messages to remove each entity
    for topic in collected_topics:
        client.publish(topic, "", retain=True)

    # Give broker time to process
    time.sleep(0.5)

    logger.info(
        "Cleaned %d discovery topics for device '%s'",
        len(collected_topics),
        device_id,
    )
    return len(collected_topics)
