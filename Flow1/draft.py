# zonal_controller.py
import asyncio
import json
from fmu_can_handler import CANHandler

# Đường dẫn FMU
AUTO_FMU = r"C:\Users\LOQ\Workspace\06_Emtek\02_Craft\vECU\FMUSDK\fmu20\fmu\cs\win64\autoLamp.fmu"
LAMP_FMU = r"C:\Users\LOQ\Workspace\06_Emtek\02_Craft\vECU\FMUSDK\fmu20\fmu\cs\win64\lampController.fmu"
MAPPINGS_FILE = "mappings.json"

async def main():
    # Tạo CANHandler với VSS converter
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
        
        # Thêm mapping tùy chỉnh (tùy chọn)
        can_handler.add_vss_mapping(
            can_id=0x103,
            signal_name="LightIntensity",
            vss_path="Vehicle.Body.Lighting.Intensity"
        )
        
        # Chạy mô phỏng với VSS conversion
        print("\nStarting simulation with VSS conversion...")
        can_handler.run_simulation(T_END=10.0, dt=0.05)
        
        # Hiển thị thống kê
        print("\n=== Simulation Results ===")
        
        # Dữ liệu CAN
        can_messages = can_handler.get_can_data()
        print(f"Total CAN messages: {len(can_messages)}")
        
        # Thống kê VSS
        vss_stats = can_handler.get_vss_statistics()
        if vss_stats:
            print(f"\nVSS Conversion Statistics:")
            for key, value in vss_stats.items():
                print(f"  {key}: {value}")
        
        # Lấy dữ liệu mô phỏng
        sim_data = can_handler.get_simulation_data()
        print(f"\nFinal simulation data:")
        print(f"  Ambient light: {sim_data['ambient']}")
        print(f"  Headlamp state: {sim_data['headlamp']}")
        print(f"  Power output: {sim_data['power']}")
        
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user")
    finally:
        # Dọn dẹp
        can_handler.shutdown()

async def test_can_to_vss_conversion():
    """Test CAN to VSS conversion directly"""
    from can_vss_converter import CANtoVSSConverter
    import can
    
    # Tạo converter
    converter = CANtoVSSConverter(kuksa_host="127.0.0.1", kuksa_port=55555)
    
    # Kết nối tới Kuksa
    await converter.connect_to_kuksa()
    
    try:
        # Tạo CAN message giả lập
        test_messages = [
            # Headlamp ON
            can.Message(
                arbitration_id=0x100,
                data=bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
                is_extended_id=False
            ),
            # Power = 75W
            can.Message(
                arbitration_id=0x101,
                data=bytes([0x4B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # 0x4B = 75
                is_extended_id=False
            ),
            # Ambient light = 500 lux
            can.Message(
                arbitration_id=0x102,
                data=bytes([0xF4, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # 0x01F4 = 500
                is_extended_id=False
            )
        ]
        
        print("\nTesting CAN to VSS conversion...")
        for msg in test_messages:
            print(f"\nProcessing CAN ID: 0x{msg.arbitration_id:03X}")
            print(f"Data: {' '.join(f'{b:02X}' for b in msg.data)}")
            
            # Chuyển đổi
            vss_signals = converter.convert_can_message(msg)
            
            if vss_signals:
                print("Converted VSS signals:")
                for vss_path, value in vss_signals.items():
                    print(f"  {vss_path}: {value}")
                
                # Gửi lên Kuksa
                await converter.send_vss_signals(vss_signals)
                print("  Sent to Kuksa ✓")
            else:
                print("  No VSS mapping found for this message")
        
        # Hiển thị thống kê
        converter.print_statistics()
        
    finally:
        await converter.disconnect_from_kuksa()

if __name__ == "__main__":
    # Chạy main simulation
    asyncio.run(main())
    
    # Hoặc test riêng conversion
    # asyncio.run(test_can_to_vss_conversion())