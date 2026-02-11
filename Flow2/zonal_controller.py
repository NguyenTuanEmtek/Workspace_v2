import asyncio
import json
import can
from can.interfaces.udp_multicast import UdpMulticastBus
from kuksa_client.grpc import Datapoint
from kuksa_client.grpc.aio import VSSClient

rx_buffer = []

# Can bus initialization
def init_can_bus(_vCanBus: bool):
        if _vCanBus:
            """Initialize virtual CAN bus"""
            bus = can.interface.Bus(
                interface='virtual',
                channel=0,
                bitrate=500000,
                receive_own_messages=True
            )
            print(f"Virtual CAN bus initialized")
        else:
            # Tạo bus multicast
            bus = can.interface.Bus(
                channel=UdpMulticastBus.DEFAULT_GROUP_IPv6,
                interface='udp_multicast')
            print(f"UDP Multicast bus initialized")
        
        return bus

#Basic Rx function
def Receive_can_msg(bus):
    print("Listening CAN bus...")
    # try:
    #     received_msg = bus.recv(timeout=3)
    #     # on_msg_received(received_msg)
    #     print(f"0x{received_msg.arbitration_id:03X} | {received_msg.dlc:>3} | "
    #                   f"{' '.join(f'{b:02X}' for b in received_msg.data)}")
    # except can.CanError:
    #     pass
    while True:
        rx_msg = bus.recv(timeout=3.0)
        if rx_msg:
            # print_received_messages()
            # print(f"0x{rx_msg.arbitration_id:03X} | {rx_msg.dlc:>3} | "
            #           f"{' '.join(f'{b:02X}' for b in rx_msg.data)}")
            on_msg_received(rx_msg)

# Polling mode 
def can_listener(bus):
    print("Starting Notifier (Press Ctrl+C to stop)...")
    print("\nReceived CAN messages:")
    print("-" * 50)
    print(f"{'ID':>5} | {'DLC':>2} | {'Data':>10}")
    print("-" * 50)

    # Khởi tạo Notifier. 
    # [on_msg_received] là danh sách các hàm/listener sẽ được gọi.
    notifier = can.Notifier(bus, [on_msg_received])
    
    return notifier

def on_msg_received(msg):
    if msg:
        rx_buffer.append(msg)
        print(f"0x{msg.arbitration_id:03X} | {msg.dlc:>3} | "
                      f"{' '.join(f'{b:02X}' for b in msg.data)}")

def print_received_messages():
    """Print all received CAN messages"""
    if rx_buffer:
        print("\nReceived CAN messages:")
        print("-" * 50)
        print(f"{'ID':>5} | {'DLC':>2} | {'Data':>10}")
        print("-" * 50)
        for msg in rx_buffer:
                # print(f"ID: 0x{msg.arbitration_id:03X} DL: {msg.dlc} bytes "
                #       f"DATA: {' '.join(f'{b:02X}' for b in msg.data)}")
            print(f"0x{msg.arbitration_id:03X} | {msg.dlc:>3} | "
                      f"{' '.join(f'{b:02X}' for b in msg.data)}")
    else:
        print("\nNo CAN messages received")

async def data_to_Kuksa():
        try:
            async with VSSClient(host="localhost", port=55555) as client:
                for msg in rx_buffer:
                    can_id_hex = hex(msg.arbitration_id)
                    if can_id_hex == "0x100":
                        value = "true" if msg.data[0] else "false"
                        print(f"CAN ID 0x100 -> Vehicle.Body.Lights.IsHighBeamOn = {value}")
                        await client.set_current_values({
                            "Vehicle.Body.Lights.IsHighBeamOn": Datapoint(value=value)})
                        await asyncio.sleep(0.1)
                    elif can_id_hex == "0x101":
                        # Power value (2 bytes, little-endian)
                        if len(msg.data) >= 2:
                            power_value = (msg.data[1] << 8) | msg.data[0]
                            print(f"CAN ID 0x101 -> Vehicle.Body.Lighting.Power = {power_value}")
                            
                            # Send to Kuksa
                            await client.set_current_values({
                                "Vehicle.Body.Lighting.Power": Datapoint(value=power_value)
                            })
                            await asyncio.sleep(0.1)
                rx_buffer.clear()
        except Exception as e:
            print(f"Lỗi kết nối: {e}")

async def main():
    vCan0 = init_can_bus(False)
    try:
        notifier = can_listener(vCan0)
        while True:
            await data_to_Kuksa()
    except KeyboardInterrupt:
        print("Stopped by user")
        notifier.stop()
        vCan0.shutdown()

# Run the async main function
asyncio.run(main())

# if __name__ == "__main__":
#     vCan0 = init_can_bus(False)
#     try:
#         Receive_can_msg(vCan0)
        
#     except KeyboardInterrupt:
#         print("Stopped")
#         vCan0.shutdown()