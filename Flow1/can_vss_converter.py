# can_vss_converter.py
import asyncio
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import can
from kuksa_client.grpc import Datapoint
from kuksa_client.grpc.aio import VSSClient

class CANSignalType(Enum):
    """Type of CAN signal"""
    BOOLEAN = "boolean"
    UINT8 = "uint8"
    UINT16 = "uint16"
    UINT32 = "uint32"
    INT8 = "int8"
    INT16 = "int16"
    INT32 = "int32"
    FLOAT = "float"

@dataclass
class CANSignalDefinition:
    """Definition of a CAN signal"""
    name: str
    start_bit: int
    bit_length: int
    signal_type: CANSignalType
    scale: float = 1.0
    offset: float = 0.0
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    unit: str = ""
    description: str = ""

@dataclass
class CANMessageDefinition:
    """Definition of a CAN message"""
    can_id: int
    name: str
    dlc: int
    signals: Dict[str, CANSignalDefinition]
    cycle_time: int = 0  # in ms
    description: str = ""

class CANtoVSSConverter:
    """
    Class to convert CAN messages to VSS signals and send to Kuksa
    """
    
    def __init__(self, kuksa_host: str = "127.0.0.1", kuksa_port: int = 55555):
        """
        Initialize CAN to VSS converter
        
        Args:
            kuksa_host: Kuksa server host
            kuksa_port: Kuksa server port
        """
        self.kuksa_host = kuksa_host
        self.kuksa_port = kuksa_port
        self.vss_client = None
        
        # CAN ID to message definition mapping
        self.message_definitions: Dict[int, CANMessageDefinition] = {}
        
        # CAN ID to VSS path mapping
        self.can_to_vss_mapping: Dict[int, Dict[str, str]] = {}
        
        # Initialize with default mappings
        self._initialize_default_mappings()
        
        # Statistics
        self.stats = {
            "messages_received": 0,
            "messages_converted": 0,
            "signals_sent": 0,
            "errors": 0
        }
    
    def _initialize_default_mappings(self):
        """Initialize default CAN to VSS mappings"""
        
        # Example: Headlamp control (CAN ID 0x100)
        headlamp_signal = CANSignalDefinition(
            name="HeadlampStatus",
            start_bit=0,
            bit_length=8,
            signal_type=CANSignalType.UINT8
        )
        
        headlamp_msg = CANMessageDefinition(
            can_id=0x100,
            name="HeadlampControl",
            dlc=8,
            signals={"HeadlampStatus": headlamp_signal},
            description="Headlamp control message"
        )
        
        self.message_definitions[0x100] = headlamp_msg
        
        # Map CAN signal to VSS path
        self.can_to_vss_mapping[0x100] = {
            "HeadlampStatus": "Vehicle.Body.Lights.IsHighBeamOn"
        }
        
        # Example: Power status (CAN ID 0x101)
        power_signal = CANSignalDefinition(
            name="LampPower",
            start_bit=0,
            bit_length=16,
            signal_type=CANSignalType.UINT16,
            scale=1.0,
            offset=0.0,
            unit="W"
        )
        
        power_msg = CANMessageDefinition(
            can_id=0x101,
            name="LampPowerStatus",
            dlc=8,
            signals={"LampPower": power_signal},
            description="Lamp power status"
        )
        
        self.message_definitions[0x101] = power_msg
        
        # Map CAN signal to VSS path
        self.can_to_vss_mapping[0x101] = {
            "LampPower": "Vehicle.Body.Lighting.Power"
        }
        
        # Add more default mappings as needed
        # Example: Ambient light sensor (CAN ID 0x102)
        ambient_signal = CANSignalDefinition(
            name="AmbientLight",
            start_bit=0,
            bit_length=16,
            signal_type=CANSignalType.UINT16,
            scale=1.0,
            offset=0.0,
            unit="lux"
        )
        
        ambient_msg = CANMessageDefinition(
            can_id=0x102,
            name="AmbientLightSensor",
            dlc=8,
            signals={"AmbientLight": ambient_signal}
        )
        
        self.message_definitions[0x102] = ambient_msg
        self.can_to_vss_mapping[0x102] = {
            "AmbientLight": "Vehicle.Body.Lights.AmbientLight"
        }
    
    def add_message_definition(self, msg_def: CANMessageDefinition):
        """Add a new CAN message definition"""
        self.message_definitions[msg_def.can_id] = msg_def
    
    def add_vss_mapping(self, can_id: int, signal_name: str, vss_path: str):
        """Add a new CAN to VSS mapping"""
        if can_id not in self.can_to_vss_mapping:
            self.can_to_vss_mapping[can_id] = {}
        self.can_to_vss_mapping[can_id][signal_name] = vss_path
    
    def load_mappings_from_json(self, json_file: str):
        """
        Load CAN to VSS mappings from JSON file
        
        JSON format:
        {
            "mappings": [
                {
                    "can_id": "0x100",
                    "signals": [
                        {
                            "name": "HeadlampStatus",
                            "vss_path": "Vehicle.Body.Lights.IsHeadLampOn"
                        }
                    ]
                }
            ],
            "message_definitions": [
                {
                    "can_id": "0x100",
                    "name": "HeadlampControl",
                    "dlc": 8,
                    "signals": [
                        {
                            "name": "HeadlampStatus",
                            "start_bit": 0,
                            "bit_length": 8,
                            "type": "uint8"
                        }
                    ]
                }
            ]
        }
        """
        try:
            with open(json_file, 'r') as f:
                config = json.load(f)
            
            # Load message definitions
            if "message_definitions" in config:
                for msg_def in config["message_definitions"]:
                    can_id = int(msg_def["can_id"], 16) if isinstance(msg_def["can_id"], str) else msg_def["can_id"]
                    
                    signals = {}
                    for sig_def in msg_def["signals"]:
                        signal = CANSignalDefinition(
                            name=sig_def["name"],
                            start_bit=sig_def["start_bit"],
                            bit_length=sig_def["bit_length"],
                            signal_type=CANSignalType(sig_def["type"])
                        )
                        signals[sig_def["name"]] = signal
                    
                    message_def = CANMessageDefinition(
                        can_id=can_id,
                        name=msg_def["name"],
                        dlc=msg_def["dlc"],
                        signals=signals,
                        description=msg_def.get("description", "")
                    )
                    
                    self.message_definitions[can_id] = message_def
            
            # Load VSS mappings
            if "mappings" in config:
                for mapping in config["mappings"]:
                    can_id = int(mapping["can_id"], 16) if isinstance(mapping["can_id"], str) else mapping["can_id"]
                    
                    if can_id not in self.can_to_vss_mapping:
                        self.can_to_vss_mapping[can_id] = {}
                    
                    for signal in mapping["signals"]:
                        self.can_to_vss_mapping[can_id][signal["name"]] = signal["vss_path"]
            
            print(f"Loaded mappings from {json_file}")
            
        except Exception as e:
            print(f"Error loading mappings from JSON: {e}")
    
    def extract_signal_from_data(self, data: bytes, signal_def: CANSignalDefinition) -> Any:
        """
        Extract signal value from CAN data bytes
        
        Args:
            data: CAN message data bytes
            signal_def: Signal definition
            
        Returns:
            Extracted signal value
        """
        try:
            # Calculate byte position and bit mask
            start_byte = signal_def.start_bit // 8
            start_bit_in_byte = signal_def.start_bit % 8
            
            # Extract relevant bytes
            num_bytes = (signal_def.bit_length + 7) // 8
            relevant_bytes = data[start_byte:start_byte + num_bytes]
            
            if not relevant_bytes:
                return None
            
            # Convert to integer (little-endian)
            value = 0
            for i, byte in enumerate(relevant_bytes):
                value |= byte << (i * 8)
            
            # Apply bit mask for bits within byte
            if start_bit_in_byte > 0 or signal_def.bit_length < (num_bytes * 8):
                bit_mask = (1 << signal_def.bit_length) - 1
                value = (value >> start_bit_in_byte) & bit_mask
            
            # Convert based on signal type
            if signal_def.signal_type == CANSignalType.BOOLEAN:
                return bool(value)
            elif signal_def.signal_type in [CANSignalType.UINT8, CANSignalType.UINT16, CANSignalType.UINT32]:
                # Apply scale and offset
                result = (value * signal_def.scale) + signal_def.offset
                # Apply min/max bounds if defined
                if signal_def.min_val is not None:
                    result = max(result, signal_def.min_val)
                if signal_def.max_val is not None:
                    result = min(result, signal_def.max_val)
                return result
            elif signal_def.signal_type in [CANSignalType.INT8, CANSignalType.INT16, CANSignalType.INT32]:
                # Handle signed values
                # Check if value is negative (most significant bit of the extracted bits)
                if value & (1 << (signal_def.bit_length - 1)):
                    # Two's complement conversion
                    value = value - (1 << signal_def.bit_length)
                
                result = (value * signal_def.scale) + signal_def.offset
                # Apply min/max bounds if defined
                if signal_def.min_val is not None:
                    result = max(result, signal_def.min_val)
                if signal_def.max_val is not None:
                    result = min(result, signal_def.max_val)
                return result
            elif signal_def.signal_type == CANSignalType.FLOAT:
                # For simplicity, treat as scaled integer
                # In real implementation, you might need proper float decoding
                result = (value * signal_def.scale) + signal_def.offset
                if signal_def.min_val is not None:
                    result = max(result, signal_def.min_val)
                if signal_def.max_val is not None:
                    result = min(result, signal_def.max_val)
                return float(result)
            
            return value
            
        except Exception as e:
            print(f"Error extracting signal: {e}")
            return None
    
    def convert_can_message(self, can_msg: can.Message) -> Dict[str, Any]:
        """
        Convert CAN message to VSS signals
        
        Args:
            can_msg: CAN message object
            
        Returns:
            Dictionary mapping VSS paths to values
        """
        vss_signals = {}
        
        try:
            self.stats["messages_received"] += 1
            
            can_id = can_msg.arbitration_id
            
            # Check if we have definition for this CAN ID
            if can_id not in self.message_definitions:
                return vss_signals
            
            msg_def = self.message_definitions[can_id]
            
            # Check if we have VSS mapping for this CAN ID
            if can_id not in self.can_to_vss_mapping:
                return vss_signals
            
            # Extract each signal from the message
            for signal_name, signal_def in msg_def.signals.items():
                # Extract signal value
                value = self.extract_signal_from_data(can_msg.data, signal_def)
                
                if value is not None:
                    # Get VSS path for this signal
                    if signal_name in self.can_to_vss_mapping[can_id]:
                        vss_path = self.can_to_vss_mapping[can_id][signal_name]
                        vss_signals[vss_path] = value
            
            if vss_signals:
                self.stats["messages_converted"] += 1
                self.stats["signals_sent"] += len(vss_signals)
            
        except Exception as e:
            self.stats["errors"] += 1
            print(f"Error converting CAN message: {e}")
        
        return vss_signals
    
    async def connect_to_kuksa(self):
        """Establish connection to Kuksa server"""
        try:
            self.vss_client = VSSClient(host=self.kuksa_host, port=self.kuksa_port)
            await self.vss_client.__aenter__()
            print(f"Connected to Kuksa server at {self.kuksa_host}:{self.kuksa_port}")
            return True
        except Exception as e:
            print(f"Failed to connect to Kuksa: {e}")
            return False
    
    async def disconnect_from_kuksa(self):
        """Disconnect from Kuksa server"""
        try:
            if self.vss_client:
                await self.vss_client.__aexit__(None, None, None)
                print("Disconnected from Kuksa server")
        except Exception as e:
            print(f"Error disconnecting from Kuksa: {e}")
    
    async def send_vss_signals(self, vss_signals: Dict[str, Any]):
        """
        Send VSS signals to Kuksa server
        
        Args:
            vss_signals: Dictionary mapping VSS paths to values
        """
        if not vss_signals or not self.vss_client:
            return
        
        try:
            # Prepare data for Kuksa
            data_to_send = {}
            for vss_path, value in vss_signals.items():
                data_to_send[vss_path] = Datapoint(value=value)
            
            # Send to Kuksa
            await self.vss_client.set_current_values(data_to_send)
            
            # Optional: Print what was sent
            # for vss_path, value in vss_signals.items():
            #     print(f"Sent to Kuksa: {vss_path} = {value}")
                
        except Exception as e:
            self.stats["errors"] += 1
            print(f"Error sending VSS signals to Kuksa: {e}")
    
    async def process_and_send_can_message(self, can_msg: can.Message):
        """
        Process CAN message and send converted signals to Kuksa
        
        Args:
            can_msg: CAN message to process
        """
        # Convert CAN message to VSS signals
        vss_signals = self.convert_can_message(can_msg)
        
        # Send to Kuksa if we have signals
        if vss_signals:
            await self.send_vss_signals(vss_signals)
    
    def get_statistics(self) -> Dict[str, int]:
        """Get conversion statistics"""
        return self.stats.copy()
    
    def print_statistics(self):
        """Print conversion statistics"""
        stats = self.get_statistics()
        print("\n=== CAN to VSS Converter Statistics ===")
        print(f"Messages received: {stats['messages_received']}")
        print(f"Messages converted: {stats['messages_converted']}")
        print(f"Signals sent: {stats['signals_sent']}")
        print(f"Errors: {stats['errors']}")
        print("=======================================\n")