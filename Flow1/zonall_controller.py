# zonal_controller.py
import asyncio
import json
import can
from fmu_can_handler import CANHandler

rx_buffer=[]
# Đường dẫn FMU
AUTO_FMU = r"C:\Users\LOQ\Workspace\06_Emtek\01_Workspace\Test_vECU\autoLamp.fmu"
LAMP_FMU = r"C:\Users\LOQ\Workspace\06_Emtek\01_Workspace\Test_vECU\lampController.fmu"
MAPPINGS_FILE = "mappings.json"

bus = can.interface.Bus(bustype='virtual', channel=0, receive_own_messages=True)

def Receive_can_msg():
    try:
        received_msg = bus.recv(timeout=0.001)
        on_msg_received(received_msg)
    except can.CanError:
        pass

def on_msg_received(msg):
    if msg:
        rx_buffer.append(msg)

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

async def main():
    # Tạo instance của CANHandler
    can_handler = CANHandler(
        auto_fmu_path=AUTO_FMU,
        lamp_fmu_path=LAMP_FMU,
        can_interface='virtual',
        channel=0,
        bitrate=500000,
        kuksa_host="127.0.0.1",
        kuksa_port=55555,
        enable_vss_converter=True
    )
    
    try:
        # Kết nối VSS converter tới Kuksa
        print("Connecting VSS converter to Kuksa...")
        connected = await can_handler.connect_vss_converter()
        if not connected:
            print("Failed to connect to Kuksa. Continuing without VSS conversion.")
        
        # Load mappings từ file JSON (tùy chọn)
        try:
            can_handler.load_vss_mappings(MAPPINGS_FILE)
        except FileNotFoundError:
            print(f"Mappings file {MAPPINGS_FILE} not found. Using default mappings.")
        
        # Hoặc chạy mô phỏng không có Kuksa
        can_handler.run_simulation(T_END=10.0, dt=0.05)
        
        # Lấy dữ liệu CAN đã nhận
        # can_messages = can_handler.get_can_data()
        # print(f"\nTotal CAN messages received: {len(can_messages)}")
        
        # Lọc theo CAN ID cụ thể
        # headlamp_messages = can_handler.get_can_data(0x100)
        # power_messages = can_handler.get_can_data(0x101)
        # print(f"Headlamp messages (ID 0x100): {len(headlamp_messages)}")
        # print(f"Power messages (ID 0x101): {len(power_messages)}")

        Receive_can_msg()
        # gửi dữ data đến broker
        await can_handler.data_to_Kuksa()
        
        # Lấy dữ liệu mô phỏng hiện tại
        # sim_data = can_handler.get_simulation_data()
        # print(f"\nCurrent simulation data:")
        # print(f"  Ambient light: {sim_data['ambient']}")
        # print(f"  Headlamp state: {sim_data['headlamp']}")
        # print(f"  Power output: {sim_data['power']}")
        
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user")
    finally:
        # Dọn dẹp tài nguyên
        await can_handler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())