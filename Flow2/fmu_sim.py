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
from can.interfaces.udp_multicast import UdpMulticastBus

# Đường dẫn FMU
AUTO_FMU = r"C:\Users\LOQ\Workspace\06_Emtek\01_Workspace\Test_vECU\autoLamp.fmu"
LAMP_FMU = r"C:\Users\LOQ\Workspace\06_Emtek\01_Workspace\Test_vECU\lampController.fmu"

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

# FMU initialization
def load_fmus():
        """Load and instantiate both FMUs"""
        print("\nLoading FMUs...")
        # Load auto FMU
        md_auto = read_model_description(AUTO_FMU)
        unzipdir_auto = extract(AUTO_FMU)
        auto_fmu = FMU2Slave(
            guid=md_auto.guid,
            unzipDirectory=unzipdir_auto,
            modelIdentifier=md_auto.coSimulation.modelIdentifier,
            instanceName="autoLamp_instance"
        )
        # Load lamp FMU
        md_lamp = read_model_description(LAMP_FMU)
        unzipdir_lamp = extract(LAMP_FMU)
        lamp_fmu = FMU2Slave(
            guid=md_lamp.guid,
            unzipDirectory=unzipdir_lamp,
            modelIdentifier=md_lamp.coSimulation.modelIdentifier,
            instanceName="lampController_instance"
        )
        # Instantiate FMUs
        auto_fmu.instantiate()
        lamp_fmu.instantiate()
        # Setup experiment
        auto_fmu.setupExperiment(startTime=0)
        lamp_fmu.setupExperiment(startTime=0)
        auto_fmu.enterInitializationMode()
        lamp_fmu.enterInitializationMode()
        auto_fmu.exitInitializationMode()
        lamp_fmu.exitInitializationMode()
        
        print("FMUs loaded and initialized successfully")

        return auto_fmu, lamp_fmu

# FMU to CAN message conversion
def fmu_to_can_messages(headlamp: bool, power: float):
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

# CAN Tx function
def send_can_messages(bus, messages):
        """Send multiple CAN messages to bus"""
        for msg in messages:
            try:
                bus.send(msg)
                # print(f"Sent CAN ID=0x{msg.arbitration_id:X} DATA={msg.data.hex()}")
            except can.CanError as e:
                print("CAN send failed:", e)

def co_sim_step(t, auto_fmu, lamp_fmu, dt=0.05):
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
        auto_fmu.setReal([0], [ambient])  # ambient_light
        
        # Step autoLamp FMU
        auto_fmu.doStep(t, dt)
        
        # Get output from autoLamp FMU
        headlamp = auto_fmu.getBoolean([0])[0]  # headlamp
        
        # Set input to lampController FMU
        lamp_fmu.setBoolean([0], [headlamp])
        
        # Step lampController FMU
        lamp_fmu.doStep(t, dt)
        
        # Get output from lampController FMU
        power = lamp_fmu.getReal([1])[0]  # lamp_power
        
        # Convert to CAN messages
        can_msgs = fmu_to_can_messages(headlamp, power)
        
        return ambient, headlamp, power, can_msgs
    
def run_simulation(bus, T_END=10.0, dt=0.05, print_progress=True):
        """
        Run co-simulation and CAN transmission
        
        Args:
            T_END: Total simulation time
            dt: Time step
            print_progress: Whether to print progress to console
        """
        t = 0.0
        auto_fmu, lamp_fmu = load_fmus()
        if print_progress:
            print(f"\nStarting simulation for {T_END} seconds with dt={dt}")
            print("-" * 50)
            print(f"{'Time':>6} | {'Ambient':>8} | {'Headlamp':>8} | {'Power':>7}")
            print("-" * 50)
        
        try:
            while t < T_END:
                # Execute co-simulation step
                ambient, headlamp, power, can_msgs = co_sim_step(t, auto_fmu, lamp_fmu, dt)
                
                # Send CAN messages
                send_can_messages(bus, can_msgs)
                
                # Try to receive CAN messages (non-blocking)
                # try:
                #     received_msg = self.bus.recv(timeout=0.001)
                #     self.on_msg_received(received_msg)
                # except can.CanError:
                #     pass
                
                # Print progress
                if print_progress:
                    print(f"{t:6.2f} | {ambient:8.2f} | {'ON' if headlamp else 'OFF':^8} | {power:7.1f}")
                
                t += dt
                
        finally:
            # if print_progress:
            #     self.print_received_messages()
                # if self.vss_converter:
                #     self.print_vss_statistics()
            print ("Message sent")
            bus.shutdown()

async def main():
    
    vCan0 = init_can_bus(False)
    run_simulation(vCan0,T_END=10.0, dt=0.05)

# Run the async main function
asyncio.run(main())