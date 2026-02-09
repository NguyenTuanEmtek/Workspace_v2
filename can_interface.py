import can
from collections import deque
import threading

class CanInterface:
    def __init__(self, channel=0, bitrate=500000, rx_buffer_size=1000):
        self.bus = can.interface.Bus(
            interface="virtual",
            channel=channel,
            bitrate=bitrate,
            receive_own_messages=True
        )

        self.rx_buffer = deque(maxlen=rx_buffer_size)
        self.lock = threading.Lock()

        self.listener = can.Listener()
        self.listener.on_message_received = self._on_msg_received
        self.notifier = can.Notifier(self.bus, [self.listener])

        print("Virtual CAN bus initialized")

    def _on_msg_received(self, msg):
        with self.lock:
            self.rx_buffer.append(msg)

    # ---------- TX ----------
    def send(self, msg: can.Message):
        try:
            self.bus.send(msg)
        except can.CanError as e:
            print("CAN send failed:", e)

    def send_multiple(self, messages):
        for msg in messages:
            self.send(msg)

    # ---------- RX ----------
    def get_latest(self, can_id):
        """Get latest message of specific CAN ID"""
        with self.lock:
            for msg in reversed(self.rx_buffer):
                if msg.arbitration_id == can_id:
                    return msg
        return None

    def get_all(self):
        """Get snapshot of RX buffer"""
        with self.lock:
            return list(self.rx_buffer)

    def shutdown(self):
        self.notifier.stop()
        self.bus.shutdown()
