"""MQTT wrapper around paho-mqtt v2.

Usage:
    broker = MQTTBroker()
    broker.connect()
    broker.subscribe("agents/customer_service/inbox", handler)
    broker.publish("gateway/outbox", {"user_id": "...", "content": "..."})
    broker.loop_forever()
"""

import json
import os
import threading
from typing import Callable

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "mosquitto.mqtt.svc.cluster.local")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))


class MQTTBroker:
    def __init__(self, client_id: str = ""):
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            client_id=client_id,
        )
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._handlers: dict[str, Callable] = {}
        self._connected = threading.Event()

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    def connect(self):
        self._client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

    def subscribe(self, topic: str, handler: Callable):
        self._handlers[topic] = handler
        if self._connected.is_set():
            self._client.subscribe(topic)

    def publish(self, topic: str, payload: dict):
        self._client.publish(topic, json.dumps(payload, ensure_ascii=False))

    def loop_forever(self):
        self._client.loop_forever(retry_first_connection=True)

    def loop_start(self):
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[MQTT] Connected to {MQTT_HOST}:{MQTT_PORT}")
            self._connected.set()
            for topic in self._handlers:
                client.subscribe(topic)
                print(f"[MQTT] Subscribed: {topic}")
        else:
            print(f"[MQTT] Connect failed rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected.clear()
        if rc != 0:
            print(f"[MQTT] Unexpected disconnect rc={rc}, reconnecting...")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            payload = {"raw": msg.payload.decode()}

        handler = self._handlers.get(topic) or self._match_wildcard(topic)
        if handler:
            try:
                handler(payload)
            except Exception as e:
                print(f"[MQTT] Handler error on {topic}: {e}")

    def _match_wildcard(self, topic: str):
        for pattern, handler in self._handlers.items():
            if pattern.endswith("/#"):
                prefix = pattern[:-2]
                if topic.startswith(prefix + "/") or topic == prefix:
                    return handler
        return None
