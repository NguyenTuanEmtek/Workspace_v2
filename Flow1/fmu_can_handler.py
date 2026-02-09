# can_handler.py
import numpy as np
import time
import os
import csv
import can
import json
from datetime import datetime
from fmpy import read_model_description, extract
from fmpy.fmi2 import FMU2Slave
import asyncio
from kuksa_client.grpc import Datapoint
from kuksa_client.grpc.aio import VSSClient

# Import the converter
from can_vss_converter import CANtoVSSConverter

class CANHandler:
    def __init__(self, auto_fmu_path, lamp_fmu_path, 
                 can_interface='virtual', channel=0, bitrate=500000,
                 kuksa_host="localhost", kuksa_port=55555,
                 enable_vss_converter=True):
        """
        Initialize CAN Handler
        
        Args:
            auto_fmu_path: Path to autoLamp FMU
            lamp_fmu_path: Path to lampController FMU
            can_interface: CAN interface type ('virtual', 'socketcan', etc.)
            channel: CAN channel
            bitrate: CAN bus bitrate
            kuksa_host: Kuksa server host
            kuksa_port: Kuksa server port
        """
        self.AUTO_FMU = auto_fmu_path
        self.LAMP_FMU = lamp_fmu_path
        self.can_interface = can_interface
        self.channel = channel
        self.bitrate = bitrate
        self.kuksa_host = kuksa_host
        self.kuksa_port = kuksa_port
        self.enable_vss_converter = enable_vss_converter
        
        # Initialize attributes
        self.bus = None
        self.auto_fmu = None
        self.lamp_fmu = None
        self.md_auto = None
        self.md_lamp = None
        self.rx_buffer = []
        self.simulation_time = 0.0
        
        # Initialize VSS converter
        if enable_vss_converter:
            self.vss_converter = CANtoVSSConverter(
                kuksa_host=kuksa_host,
                kuksa_port=kuksa_port
            )
        else:
            self.vss_converter = None
        
        # Initialize CAN bus
        self.init_can_bus()
        
        # Load FMUs
        self.load_fmus()
        
    def init_can_bus(self):
        """Initialize virtual CAN bus"""
        self.bus = can.interface.Bus(
            interface=self.can_interface,
            channel=self.channel,
            bitrate=self.bitrate,
            receive_own_messages=True
        )
        print(f"Virtual CAN bus initialized on interface {self.can_interface}, channel {self.channel}")
        
    def fmu_to_can_messages(self, headlamp: bool, power: float):
        """
        Convert FMU outputs to CAN messages
        
        Args:
            headlamp: Boolean state of headlamp
            power: Power value
            
        Returns:
            List of CAN messages
        """
        messages = []
        
        # Headlamp message (CAN ID 0x100)
        headlamp_data = bytearray(8)
        headlamp_data[0] = 1 if headlamp else 0
        msg_headlamp = can.Message(
            arbitration_id=0x100,
            data=headlamp_data,
            is_extended_id=False
        )
        messages.append(msg_headlamp)
        
        # Power message (CAN ID 0x101)
        power_data = bytearray(8)
        power_int = int(power * 1)  # scale if needed
        power_data[0] = power_int & 0xFF
        power_data[1] = (power_int >> 8) & 0xFF
        msg_power = can.Message(
            arbitration_id=0x101,
            data=power_data,
            is_extended_id=False
        )
        messages.append(msg_power)
        
        return messages
    
    def send_can_messages(self, messages):
        """Send multiple CAN messages to bus"""
        for msg in messages:
            try:
                self.bus.send(msg)
                # print(f"Sent CAN ID=0x{msg.arbitration_id:X} DATA={msg.data.hex()}")
            except can.CanError as e:
                print("CAN send failed:", e)
    
    def load_fmus(self):
        """Load and instantiate both FMUs"""
        print("\nLoading FMUs...")
        
        # Load auto FMU
        self.md_auto = read_model_description(self.AUTO_FMU)
        unzipdir_auto = extract(self.AUTO_FMU)
        self.auto_fmu = FMU2Slave(
            guid=self.md_auto.guid,
            unzipDirectory=unzipdir_auto,
            modelIdentifier=self.md_auto.coSimulation.modelIdentifier,
            instanceName="autoLamp_instance"
        )
        
        # Load lamp FMU
        self.md_lamp = read_model_description(self.LAMP_FMU)
        unzipdir_lamp = extract(self.LAMP_FMU)
        self.lamp_fmu = FMU2Slave(
            guid=self.md_lamp.guid,
            unzipDirectory=unzipdir_lamp,
            modelIdentifier=self.md_lamp.coSimulation.modelIdentifier,
            instanceName="lampController_instance"
        )
        
        # Instantiate FMUs
        self.auto_fmu.instantiate()
        self.lamp_fmu.instantiate()
        
        # Setup experiment
        self.auto_fmu.setupExperiment(startTime=0)
        self.lamp_fmu.setupExperiment(startTime=0)
        
        self.auto_fmu.enterInitializationMode()
        self.lamp_fmu.enterInitializationMode()
        
        self.auto_fmu.exitInitializationMode()
        self.lamp_fmu.exitInitializationMode()
        
        print("FMUs loaded and initialized successfully")
    
    async def connect_vss_converter(self):
        """Connect VSS converter to Kuksa"""
        if self.vss_converter:
            return await self.vss_converter.connect_to_kuksa()
        return False
    
    async def disconnect_vss_converter(self):
        """Disconnect VSS converter from Kuksa"""
        if self.vss_converter:
            await self.vss_converter.disconnect_from_kuksa()
    
    def on_msg_received(self, msg):
        """Callback for received CAN messages with VSS conversion"""
        if msg:
            self.rx_buffer.append(msg)
            
            # If VSS converter is enabled, process the message
            # if self.vss_converter:
            #     # print("processing receive msg")
            #     asyncio.create_task(self._process_received_message(msg))

    async def _process_received_message(self, msg):
        """Process received CAN message with VSS converter"""
        try:
            await self.vss_converter.process_and_send_can_message(msg)
        except Exception as e:
            print(f"Error processing CAN message: {e}")
    
    def load_vss_mappings(self, json_file: str):
        """Load VSS mappings from JSON file"""
        if self.vss_converter:
            self.vss_converter.load_mappings_from_json(json_file)
        else:
            print("VSS converter is not enabled")
    
    def add_vss_mapping(self, can_id: int, signal_name: str, vss_path: str):
        """Add CAN to VSS mapping"""
        if self.vss_converter:
            self.vss_converter.add_vss_mapping(can_id, signal_name, vss_path)
        else:
            print("VSS converter is not enabled")
    
    def get_vss_statistics(self):
        """Get VSS converter statistics"""
        if self.vss_converter:
            return self.vss_converter.get_statistics()
        return {}
    
    def print_vss_statistics(self):
        """Print VSS converter statistics"""
        if self.vss_converter:
            self.vss_converter.print_statistics()
    
    async def send_to_kuksa(self, ambient, threshold, hysteresis, is_high_beam, power):
        """
        Send data to Kuksa server
        
        Args:
            ambient: Ambient light value
            threshold: Threshold value
            hysteresis: Hysteresis value
            is_high_beam: High beam state
            power: Power value
        """
        async with VSSClient(host=self.kuksa_host, port=self.kuksa_port) as client:
            data_to_send = {
                "Vehicle.Body.Lights.AmbientLight": Datapoint(value=ambient),
                "Vehicle.Body.Lighting.Threshold": Datapoint(value=threshold),
                "Vehicle.Body.Lighting.Hysteresis": Datapoint(value=hysteresis),
                "Vehicle.Body.Lights.IsHighBeamOn": Datapoint(value=is_high_beam),
                "Vehicle.Body.Lighting.Power": Datapoint(value=power)
            }
            await client.set_current_values(data_to_send)
    
    def co_sim_step(self, t, dt=0.05):
        """
        Execute one co-simulation step
        
        Args:
            t: Current simulation time
            dt: Time step
            
        Returns:
            Tuple (ambient, headlamp, power, can_messages)
        """
        # Generate test ambient signal
        ambient = 250 + 100 * np.sin(t)
        
        # Set input to autoLamp FMU
        self.auto_fmu.setReal([0], [ambient])  # ambient_light
        
        # Step autoLamp FMU
        self.auto_fmu.doStep(t, dt)
        
        # Get output from autoLamp FMU
        headlamp = self.auto_fmu.getBoolean([0])[0]  # headlamp
        
        # Set input to lampController FMU
        self.lamp_fmu.setBoolean([0], [headlamp])
        
        # Step lampController FMU
        self.lamp_fmu.doStep(t, dt)
        
        # Get output from lampController FMU
        power = self.lamp_fmu.getReal([1])[0]  # lamp_power
        
        # Convert to CAN messages
        can_msgs = self.fmu_to_can_messages(headlamp, power)
        
        return ambient, headlamp, power, can_msgs
    
    def run_simulation(self, T_END=10.0, dt=0.05, print_progress=True):
        """
        Run co-simulation and CAN transmission
        
        Args:
            T_END: Total simulation time
            dt: Time step
            print_progress: Whether to print progress to console
        """
        t = 0.0
        
        if print_progress:
            print(f"\nStarting simulation for {T_END} seconds with dt={dt}")
            print("-" * 50)
            print(f"{'Time':>6} | {'Ambient':>8} | {'Headlamp':>8} | {'Power':>7}")
            print("-" * 50)
        
        try:
            while t < T_END:
                # Execute co-simulation step
                ambient, headlamp, power, can_msgs = self.co_sim_step(t, dt)
                
                # Send CAN messages
                self.send_can_messages(can_msgs)
                
                # Try to receive CAN messages (non-blocking)
                try:
                    received_msg = self.bus.recv(timeout=0.001)
                    self.on_msg_received(received_msg)
                except can.CanError:
                    pass
                
                # Print progress
                if print_progress:
                    print(f"{t:6.2f} | {ambient:8.2f} | {'ON' if headlamp else 'OFF':^8} | {power:7.1f}")
                
                t += dt
                
        finally:
            if print_progress:
                self.print_received_messages()
                # if self.vss_converter:
                #     self.print_vss_statistics()
    
    # def _process_received_messages(self):
    #     """Process received CAN messages (non-blocking)"""
    #     try:
    #         # Try to receive all available messages
    #         while True:
    #             received_msg = self.bus.recv(timeout=0.001)
    #             if received_msg:
    #                 self.on_msg_received(received_msg)
    #             else:
    #                 break
    #     except can.CanError:
    #         pass

    def print_received_messages(self):
        """Print all received CAN messages"""
        if self.rx_buffer:
            print("\nReceived CAN messages:")
            print("-" * 50)
            print(f"{'ID':>5} | {'DLC':>2} | {'Data':>10}")
            print("-" * 50)
            for msg in self.rx_buffer:
                # print(f"ID: 0x{msg.arbitration_id:03X} DL: {msg.dlc} bytes "
                #       f"DATA: {' '.join(f'{b:02X}' for b in msg.data)}")
                print(f"0x{msg.arbitration_id:03X} | {msg.dlc:>3} | "
                      f"{' '.join(f'{b:02X}' for b in msg.data)}")
        else:
            print("\nNo CAN messages received")
    
    def get_can_data(self, can_id=None):
        """
        Get received CAN data
        
        Args:
            can_id: Filter by CAN ID (hex or decimal)
            
        Returns:
            List of CAN messages (filtered if can_id provided)
        """
        if can_id is not None:
            if isinstance(can_id, str):
                can_id = int(can_id, 16)
            return [msg for msg in self.rx_buffer if msg.arbitration_id == can_id]
        return self.rx_buffer
    
    def get_simulation_data(self):
        """
        Get current simulation data from FMUs
        
        Returns:
            Dictionary with simulation data
        """
        return {
            'ambient': self.auto_fmu.getReal([0])[0] if self.auto_fmu else None,
            'headlamp': self.auto_fmu.getBoolean([0])[0] if self.auto_fmu else None,
            'power': self.lamp_fmu.getReal([1])[0] if self.lamp_fmu else None
        }
    
    async def shutdown(self):
        """Cleanup resources"""
        print("Shutting down CAN bus and VSS converter...")
        
        # Disconnect VSS converter
        if self.vss_converter:
            await self.disconnect_vss_converter()
        
        # Shutdown CAN bus
        if self.bus:
            self.bus.shutdown()
        
        # Terminate FMUs
        if self.auto_fmu:
            self.auto_fmu.terminate()
            self.auto_fmu.freeInstance()
        if self.lamp_fmu:
            self.lamp_fmu.terminate()
            self.lamp_fmu.freeInstance()
        
        print("CAN handler shutdown complete")

    # async def run_with_kuksa(self, T_END=10.0, dt=0.05):
    #     """
    #     Run simulation with Kuksa integration
        
    #     Args:
    #         T_END: Total simulation time
    #         dt: Time step
    #     """
    #     t = 0.0
        
    #     print(f"\nStarting simulation with Kuksa integration for {T_END} seconds")
    #     print("-" * 60)
    #     print(f"{'Time':>6} | {'Ambient':>8} | {'Headlamp':>8} | {'Power':>7} | Kuksa")
    #     print("-" * 60)
        
    #     try:
    #         while t < T_END:
    #             # Execute co-simulation step
    #             ambient, headlamp, power, can_msgs = self.co_sim_step(t, dt)
                
    #             # Send CAN messages
    #             self.send_can_messages(can_msgs)
                
    #             # Send to Kuksa
    #             try:
    #                 await self.send_to_kuksa(ambient, 300.0, 50.0, headlamp, power)
    #                 kuksa_status = "✓"
    #             except Exception as e:
    #                 kuksa_status = f"✗ ({str(e)[:20]})"
                
    #             # Receive CAN messages
    #             try:
    #                 received_msg = self.bus.recv(timeout=0.001)
    #                 self.on_msg_received(received_msg)
    #             except can.CanError:
    #                 pass
                
    #             # Print progress
    #             print(f"{t:6.2f} | {ambient:8.2f} | {'ON' if headlamp else 'OFF':^8} | "
    #                   f"{power:7.1f} | {kuksa_status}")
                
    #             t += dt
                
    #     finally:
    #         self.print_received_messages()

    async def data_to_Kuksa(self):
        try:
            async with VSSClient(host=self.kuksa_host, port=self.kuksa_port) as client:
                for msg in self.rx_buffer:
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
        except Exception as e:
            print(f"Lỗi kết nối: {e}")

# Factory function for backward compatibility
def create_can_handler(auto_fmu_path, lamp_fmu_path, **kwargs):
    """Factory function to create CANHandler instance"""
    return CANHandler(auto_fmu_path, lamp_fmu_path, **kwargs)