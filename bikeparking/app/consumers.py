import json
from channels.generic.websocket import WebsocketConsumer

class SlotDetectionConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()
        self.send(text_data=json.dumps({
            "message": "Connected to slot detection stream"
        }))

    def send_detected_slot(self, slot_label):
        """Send new detected slot to frontend"""
        self.send(text_data=json.dumps({
            "detected_slot": slot_label
        }))
