┌────────────────────────────────────────────────────────────┐
│                    vECU (FMU simulation)                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  FMU Simulator (fmu_sim.py)                          │  │
│  │  • Load autoLamp.fmu (win64)                         │  │
│  │  • Simulate ambient light → headLamp logic           │  │
│  │  • Encode to CAN frame                               │  │
│  │  • Send CAN message via UDP bus (udp_multicastbus)   │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                  │
└─────────────────────────┼──────────────────────────────────┘
                          ▼ IPv6 LAN
┌─────────────────────────┼──────────────────────────────────┐
│                    Zonal Controller                        │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │  Zonal Controller (zonal_controller.py)              │  │
│  │  • Listen to incoming CAN message                    │  │
│  │  • Decode CAN to VSS signals                         │  │
│  │  • Send VSS signal to Kuksa data broker              │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘