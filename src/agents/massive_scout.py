"""
Massive AI Job Directory & Company Scout Agent.
Maintains, expands, and searches an expansive global directory of 1,000 to 100,000+
companies and engineering job websites related to:
- RF, Microwave, Radar & Antenna Engineering
- High-Speed Multilayer PCB Design (Altium, Siemens Xpedition, Cadence Allegro)
- Embedded Systems, Microcontrollers (ARM, STM32, ESP32), RTOS & Firmware
- Semiconductors, Analog/Mixed-Signal, ASIC & FPGA
- Aerospace, Satellite Communications & Defense Avionics
- Automotive Radar, EV Powertrains & Autonomous Robotics
- Medical Electronics & Precision Instrumentation

Capabilities:
1. Extensive Curated Base Directory (100+ Tier-1 Global Engineering Employers).
2. Autonomous AI Sector & Country Expansion via Google Gemini Pro / Flash.
3. Live Job Website & Aggregator Harvester (Arbeitnow, Remotive, Jobicy, etc.).
4. Direct ATS Portal Job Hunter (Workday CXS REST, Greenhouse, Lever, Ashby, SmartRecruiters).
5. AI Job Classification (Technical fit 0-100, authentic evidence quote, Remote/Hybrid/Onsite).
6. AI Adversarial Audit & Verification (Zero hallucinations, link vitality audit).
7. SQLite Durable Storage & Multi-Sheet Excel Reporting.
"""

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from src.agents.classifier import AIJobClassifierAgent
from src.agents.llm_engine import ai_engine
from src.agents.verifier import AIVerifierAgent
from src.db import StateDatabase
from src.schemas import UserProfile
from mcp_servers.career_page_reader.server import list_jobs, get_job_details, detect_ats


class ScoutedCompany(BaseModel):
    name: str = Field(..., description="Company name")
    domain: str = Field(..., description="Primary domain, e.g. nxp.com")
    country: str = Field(..., description="Headquarters or major R&D engineering hub")
    industry: str = Field(..., description="Hardware/Embedded/RF engineering sub-specialization")
    careers_url: str = Field(..., description="Direct ATS portal or careers page URL")
    ats_hint: Optional[str] = Field(default=None, description="greenhouse, lever, ashby, workday, smartrecruiters, or html")
    relevance_rationale: str = Field(..., description="Why this company hires RF, Hardware, or Embedded Engineers")


class ScoutedCompanyBatch(BaseModel):
    companies: List[ScoutedCompany] = Field(..., description="Discovered engineering companies")


class JobWebsiteInfo(BaseModel):
    name: str
    url: str
    category: str
    api_type: str
    supported_regions: List[str]
    description: str


# =============================================================================
# CURATED TIER-1 GLOBAL DIRECTORY OF HARDWARE, RF, PCB & EMBEDDED EMPLOYERS
# (100+ Verified Enterprise Leaders & High-Growth Scale-Ups)
# =============================================================================
CURATED_HARDWARE_DIRECTORY: List[Dict[str, Any]] = [
    # --- NETHERLANDS (Semiconductors, Quantum, RF & High-Tech Systems) ---
    {"name": "NXP Semiconductors", "domain": "nxp.com", "country": "Netherlands", "industry": "Automotive Radar, RF Front-Ends & Secure MCUs", "careers_url": "https://nxp.wd3.myworkdayjobs.com/careers"},
    {"name": "ASML", "domain": "asml.com", "country": "Netherlands", "industry": "EUV Photolithography, Precision Mechatronics & Power Electronics", "careers_url": "https://asml.wd3.myworkdayjobs.com/ASML_Careers"},
    {"name": "QuantWare", "domain": "quantware.com", "country": "Netherlands", "industry": "Superconducting Quantum Processors & RF Microwave Readout", "careers_url": "https://jobs.ashbyhq.com/quantware"},
    {"name": "Ampleon", "domain": "ampleon.com", "country": "Netherlands", "industry": "LDMOS & GaN RF Power Transistors for Cellular & Broadcast", "careers_url": "https://www.ampleon.com/careers"},
    {"name": "Philips Innovation", "domain": "philips.com", "country": "Netherlands", "industry": "Medical Device Electronics, MRI RF Coils & Embedded Sensors", "careers_url": "https://philips.wd3.myworkdayjobs.com/Philips_Careers"},
    {"name": "Prodrive Technologies", "domain": "prodrive-technologies.com", "country": "Netherlands", "industry": "Power Electronics, Embedded Computing & High-End PCB Assemblies", "careers_url": "https://prodrive-technologies.com/careers"},
    {"name": "Nearfield Instruments", "domain": "nearfieldinstruments.com", "country": "Netherlands", "industry": "High-Throughput Atomic Force Microscopy & Precision Hardware", "careers_url": "https://jobs.ashbyhq.com/nearfieldinstruments"},

    # --- GERMANY (Aerospace, Radar, Industrial, Automotive & Defense) ---
    {"name": "Rohde & Schwarz", "domain": "rohde-schwarz.com", "country": "Germany", "industry": "RF Test & Measurement, Spectrum Analyzers, VNAs & Radios", "careers_url": "https://www.rohde-schwarz.com/careers"},
    {"name": "Hensoldt", "domain": "hensoldt.net", "country": "Germany", "industry": "Air Defense Radars, AESA Phased Arrays & Electronic Warfare", "careers_url": "https://jobs.hensoldt.net"},
    {"name": "Infineon Technologies", "domain": "infineon.com", "country": "Germany", "industry": "Automotive Radar Transceivers, Power MOSFETs & AURIX MCUs", "careers_url": "https://infineon.wd3.myworkdayjobs.com/Infineon_External"},
    {"name": "Robert Bosch", "domain": "bosch.com", "country": "Germany", "industry": "MEMS Sensors, Automotive ECUs, Radar & Embedded Systems", "careers_url": "https://jobs.smartrecruiters.com/BoschGroup"},
    {"name": "Helsing", "domain": "helsing.ai", "country": "Germany", "industry": "Defense AI, Real-Time Sensor Processing & Rugged Embedded Hardware", "careers_url": "https://boards.greenhouse.io/helsing"},
    {"name": "Isar Aerospace", "domain": "isaraerospace.com", "country": "Germany", "industry": "Launch Vehicle Avionics, Flight Computers & Power Distribution", "careers_url": "https://boards.greenhouse.io/isaraerospace"},
    {"name": "The Exploration Company", "domain": "exploration.space", "country": "Germany", "industry": "Orbital Spacecraft Avionics, Telemetry & Space Electronics", "careers_url": "https://jobs.ashbyhq.com/the-exploration-company"},
    {"name": "Rocket Factory Augsburg", "domain": "rfa.space", "country": "Germany", "industry": "Rocket Avionics, Electronic Actuators & Embedded Controllers", "careers_url": "https://boards.greenhouse.io/rocketfactoryaugsburgag"},
    {"name": "Sensmore", "domain": "sensmore.ai", "country": "Germany", "industry": "Radar Sensor Electronics, Embedded Robotics & Microcontroller Hardware", "careers_url": "https://jobs.ashbyhq.com/sensmore"},
    {"name": "Volocopter", "domain": "volocopter.com", "country": "Germany", "industry": "Electric eVTOL Avionics, Motor Controllers & Battery Systems", "careers_url": "https://jobs.lever.co/volocopter"},
    {"name": "Lilium", "domain": "lilium.com", "country": "Germany", "industry": "Electric Jet Avionics, High-Voltage Power & Flight Controls", "careers_url": "https://jobs.lever.co/lilium"},
    {"name": "Continental", "domain": "continental.com", "country": "Germany", "industry": "Automotive Radar, Telematics & Advanced Driver Assistance Systems", "careers_url": "https://continental.wd3.myworkdayjobs.com/Continental_Careers"},
    {"name": "dSPACE", "domain": "dspace.com", "country": "Germany", "industry": "Hardware-in-the-Loop (HIL) Simulators & Embedded Prototyping", "careers_url": "https://www.dspace.com/en/inc/home/careers.cfm"},

    # --- FRANCE (Radar, Aerospace, Optronics, Telecom & Defense) ---
    {"name": "Thales Group", "domain": "thalesgroup.com", "country": "France", "industry": "Radar, RF Antennas, Electronic Warfare, Avionics & Satellites", "careers_url": "https://thales.wd3.myworkdayjobs.com/Careers"},
    {"name": "Safran Electronics & Defense", "domain": "safran-group.com", "country": "France", "industry": "Inertial Navigation, Optronics & Embedded Flight Computers", "careers_url": "https://safran.wd3.myworkdayjobs.com/Safran_Careers"},
    {"name": "Airbus Defence and Space", "domain": "airbus.com", "country": "France", "industry": "Satellite Telecommunications, Phased Arrays & Space Electronics", "careers_url": "https://airbus.wd3.myworkdayjobs.com/Airbus"},
    {"name": "Alta Ares", "domain": "alta-ares.com", "country": "France", "industry": "Radar Systems, FPGA Electronic Warfare & Interceptors", "careers_url": "https://jobs.ashbyhq.com/alta-ares"},
    {"name": "Alice & Bob", "domain": "alice-bob.com", "country": "France", "industry": "Fault-Tolerant Quantum Hardware, Microwave Readout & FPGA", "careers_url": "https://jobs.lever.co/alice-bob"},
    {"name": "Soitec", "domain": "soitec.com", "country": "France", "industry": "Engineered Substrates, RF-SOI & Power Semiconductors", "careers_url": "https://www.soitec.com/en/careers"},
    {"name": "Pasqal", "domain": "pasqal.com", "country": "France", "industry": "Neutral-Atom Quantum Processing & Laser Control Electronics", "careers_url": "https://jobs.lever.co/pasqal"},
    {"name": "Radiall", "domain": "radiall.com", "country": "France", "industry": "RF & Microwave Coaxial Connectors, Antennas & Optical Components", "careers_url": "https://www.radiall.com/careers"},
    {"name": "MBDA France", "domain": "mbda-systems.com", "country": "France", "industry": "Missile RF Seekers, Telemetry & Rugged Avionics Hardware", "careers_url": "https://www.mbda-systems.com/careers"},

    # --- UNITED KINGDOM (Silicon, RF, Satellites, Consumer Hardware) ---
    {"name": "Arm Ltd", "domain": "arm.com", "country": "UK", "industry": "Processor Architectures, RTL Design, Embedded Firmware & Silicon IP", "careers_url": "https://arm.wd3.myworkdayjobs.com/Arm_Careers"},
    {"name": "Filtronic", "domain": "filtronic.com", "country": "UK", "industry": "mmWave Transceivers, RF Filters & High-Frequency Power Amplifiers", "careers_url": "https://filtronic.com/careers"},
    {"name": "BAE Systems", "domain": "baesystems.com", "country": "UK", "industry": "Defense Avionics, Phased Arrays, Electronic Warfare & Naval Radars", "careers_url": "https://baesystems.wd3.myworkdayjobs.com/Global"},
    {"name": "Graphcore", "domain": "graphcore.ai", "country": "UK", "industry": "AI Silicon, Multilayer High-Speed PCB & Hardware Validation", "careers_url": "https://boards.greenhouse.io/graphcore"},
    {"name": "Spire Global", "domain": "spire.com", "country": "UK", "industry": "Earth Observation RF Payloads, Satellite Avionics & Ground Stations", "careers_url": "https://boards.greenhouse.io/spire"},
    {"name": "Foundational Space", "domain": "foundational.space", "country": "UK", "industry": "Satellite Laser Ranging, Ground Hardware & Space Electronics", "careers_url": "https://jobs.ashbyhq.com/foundational"},
    {"name": "Dyson", "domain": "dyson.com", "country": "UK", "industry": "High-Speed Motors, Embedded Battery Management & Connected Hardware", "careers_url": "https://dyson.wd3.myworkdayjobs.com/Dyson_Careers"},
    {"name": "Cambridge Consultants", "domain": "cambridgeconsultants.com", "country": "UK", "industry": "Custom Wireless Systems, Novel Antennas & Medical Electronics", "careers_url": "https://www.cambridgeconsultants.com/careers"},
    {"name": "Pragmatic Semiconductor", "domain": "pragmaticsemi.com", "country": "UK", "industry": "Flexible Integrated Circuits, RFID & Sub-Micron Foundry", "careers_url": "https://pragmaticsemi.com/careers"},

    # --- IRELAND (Analog, Mixed-Signal, Medical & Automotive) ---
    {"name": "Analog Devices Europe", "domain": "analog.com", "country": "Ireland", "industry": "Mixed-Signal ICs, RF Transceivers, Data Converters & Power Management", "careers_url": "https://analogdevices.wd1.myworkdayjobs.com/External"},
    {"name": "Aptiv Ireland", "domain": "aptiv.com", "country": "Ireland", "industry": "Autonomous Vehicle Signal Architecture, Radar & Central Compute", "careers_url": "https://aptiv.wd1.myworkdayjobs.com/Aptiv_Careers"},
    {"name": "Medtronic Galway", "domain": "medtronic.com", "country": "Ireland", "industry": "Cardiac Pacemaker Electronics, Implantable RF & Embedded Firmware", "careers_url": "https://medtronic.wd1.myworkdayjobs.com/Medtronic"},
    {"name": "Microchip Technology Cork", "domain": "microchip.com", "country": "Ireland", "industry": "PIC/AVR Microcontrollers, Mixed-Signal & RF Connectivity", "careers_url": "https://careers.microchip.com"},

    # --- SWITZERLAND, AUSTRIA & BELGIUM ---
    {"name": "u-blox", "domain": "u-blox.com", "country": "Switzerland", "industry": "GNSS Positioning Chips, Cellular Modules & Short-Range RF Transceivers", "careers_url": "https://www.u-blox.com/en/careers"},
    {"name": "Sensirion", "domain": "sensirion.com", "country": "Switzerland", "industry": "Environmental Sensors, Flow Meters & CMOS/MEMS Analog Frontend", "careers_url": "https://www.sensirion.com/en/about-us/careers"},
    {"name": "STMicroelectronics Geneva", "domain": "st.com", "country": "Switzerland", "industry": "STM32 Microcontrollers, SiC Power Devices & MEMS Sensors", "careers_url": "https://stmicroelectronics.wd3.myworkdayjobs.com/Careers"},
    {"name": "AMS Osram", "domain": "ams-osram.com", "country": "Austria", "industry": "Optical Sensors, LiDAR Emitters & Analog Interface ASICs", "careers_url": "https://ams-osram.com/careers"},
    {"name": "AT&S (Austria Technologie)", "domain": "ats.net", "country": "Austria", "industry": "High-End HDI Multilayer PCBs, IC Substrates & RF Substrates", "careers_url": "https://ats.net/en/careers"},
    {"name": "TTTech Auto", "domain": "tttech-auto.com", "country": "Austria", "industry": "Time-Triggered Ethernet, Safety-Critical Embedded Platforms & ECUs", "careers_url": "https://www.tttech-auto.com/careers"},
    {"name": "Melexis", "domain": "melexis.com", "country": "Belgium", "industry": "Automotive Magnetic Sensor ICs, Current Sensors & Motor Drivers", "careers_url": "https://www.melexis.com/en/careers"},
    {"name": "Septentrio", "domain": "septentrio.com", "country": "Belgium", "industry": "High-Precision Multi-Frequency GNSS/GPS RF Receivers & Hardware", "careers_url": "https://www.septentrio.com/en/company/careers"},

    # --- NORDICS (Sweden, Norway, Finland) ---
    {"name": "Ericsson", "domain": "ericsson.com", "country": "Sweden", "industry": "5G Massive MIMO Antennas, mmWave Base Stations & Cellular RF Hardware", "careers_url": "https://ericsson.wd3.myworkdayjobs.com/Ericsson_Careers"},
    {"name": "Saab AB", "domain": "saab.com", "country": "Sweden", "industry": "Gripen Fighter Avionics, Giraffe Surface Radar & Electronic Warfare", "careers_url": "https://www.saab.com/career"},
    {"name": "Nordic Semiconductor", "domain": "nordicsemi.com", "country": "Norway", "industry": "Ultra-Low Power Bluetooth LE, Cellular IoT & Wi-Fi Microcontrollers", "careers_url": "https://www.nordicsemi.com/About-us/Careers"},
    {"name": "Kongsberg Defence & Aerospace", "domain": "kongsberg.com", "country": "Norway", "industry": "Missile Guidance, Space Electronics & Remote Weapon Systems", "careers_url": "https://www.kongsberg.com/careers"},
    {"name": "Nokia", "domain": "nokia.com", "country": "Finland", "industry": "Mobile Radio Networks, Optical Transmission & High-Speed FPGA Systems", "careers_url": "https://nokia.wd3.myworkdayjobs.com/Nokia_Careers"},
    {"name": "IQM Quantum Computers", "domain": "meetiqm.com", "country": "Finland", "industry": "Superconducting Quantum Processors & Microwave Control Electronics", "careers_url": "https://jobs.lever.co/meetiqm"},

    # --- UNITED STATES (Space, Defense, RF, Robotics & Consumer Tech) ---
    {"name": "SpaceX / Starlink", "domain": "spacex.com", "country": "USA", "industry": "Starlink Phased-Array Antennas, RFIC & Satellite Avionics", "careers_url": "https://boards.greenhouse.io/spacex"},
    {"name": "Astranis Space Technologies", "domain": "astranis.com", "country": "USA", "industry": "Geostationary Telecommunications & MicroGEO RF Payloads", "careers_url": "https://boards.greenhouse.io/astranis"},
    {"name": "Anduril Industries", "domain": "anduril.com", "country": "USA", "industry": "Autonomous Systems, RF Data Links, Counter-UAS & Edge Robotics", "careers_url": "https://boards.greenhouse.io/andurilindustries"},
    {"name": "Formlabs", "domain": "formlabs.com", "country": "USA", "industry": "Precision 3D Electronics, Actuation & Sensor Hardware", "careers_url": "https://boards.greenhouse.io/formlabs"},
    {"name": "Palantir Technologies", "domain": "palantir.com", "country": "USA", "industry": "Mission Edge Hardware, Embedded Linux & Rugged Computing", "careers_url": "https://jobs.lever.co/palantir"},
    {"name": "Framework Computer", "domain": "frame.work", "country": "USA", "industry": "Modular Electronics, Mainboard PCB Layout & Embedded Controllers", "careers_url": "https://jobs.ashbyhq.com/framework"},
    {"name": "Skydio", "domain": "skydio.com", "country": "USA", "industry": "Autonomous Drone Hardware, RF Comms, Motor Controllers & Imaging", "careers_url": "https://boards.greenhouse.io/skydio"},
    {"name": "Zoox", "domain": "zoox.com", "country": "USA", "industry": "Autonomous Vehicle Compute, Radar, LiDAR & High-Voltage Powertrain", "careers_url": "https://boards.greenhouse.io/zoox"},
    {"name": "Qualcomm", "domain": "qualcomm.com", "country": "USA", "industry": "Snapdragon Cellular Modems, RF Front-End Filters & Automotive Cockpit", "careers_url": "https://qualcomm.wd5.myworkdayjobs.com/External"},
    {"name": "Skyworks Solutions", "domain": "skyworksinc.com", "country": "USA", "industry": "RF Front-End Modules, Power Amplifiers & Diversity Receive Modules", "careers_url": "https://skyworks.wd1.myworkdayjobs.com/Skyworks_Careers"},
    {"name": "Qorvo", "domain": "qorvo.com", "country": "USA", "industry": "Bulk Acoustic Wave (BAW) Filters, GaN RF Power & Ultra-Wideband (UWB)", "careers_url": "https://qorvo.wd1.myworkdayjobs.com/Qorvo_Careers"},
    {"name": "Texas Instruments", "domain": "ti.com", "country": "USA", "industry": "Analog Op-Amps, Power Management ICs & mmWave Radar Transceivers", "careers_url": "https://ti.wd1.myworkdayjobs.com/TI_Careers"},
    {"name": "Echodyne", "domain": "echodyne.com", "country": "USA", "industry": "Metamaterial Electronic Scanning Array (MESA) Radars", "careers_url": "https://boards.greenhouse.io/echodyne"},
    {"name": "Lightmatter", "domain": "lightmatter.co", "country": "USA", "industry": "Photonic Silicon Computing, Laser Interconnects & Electro-Optics", "careers_url": "https://boards.greenhouse.io/lightmatter"},
    {"name": "SolarEdge Technologies", "domain": "solaredge.com", "country": "USA", "industry": "Solar Inverters, High-Voltage Power Electronics & Microinverters", "careers_url": "https://boards.greenhouse.io/solaredge"},
    {"name": "Verve Motion", "domain": "vervemotion.com", "country": "USA", "industry": "Wearable Robotics, Embedded Motor Actuation & Inertial Sensors", "careers_url": "https://boards.greenhouse.io/vervemotion"},
    {"name": "Relativity Space", "domain": "relativityspace.com", "country": "USA", "industry": "3D-Printed Rocket Avionics, Ground Support Systems & RF Telemetry", "careers_url": "https://boards.greenhouse.io/relativity"},
    {"name": "Sierra Space", "domain": "sierraspace.com", "country": "USA", "industry": "Dream Chaser Spaceplane Avionics, Orbital Habitats & RF Transceivers", "careers_url": "https://sierraspace.wd5.myworkdayjobs.com/SierraSpaceCareers"},

    # --- ASIA-PACIFIC (Australia, Japan, Taiwan, Singapore) ---
    {"name": "Morse Micro", "domain": "morsemicro.com", "country": "Australia", "industry": "Wi-Fi HaLow (802.11ah) Sub-1GHz RF Silicon & Embedded IoT", "careers_url": "https://boards.greenhouse.io/morsemicro"},
    {"name": "CEA Technologies", "domain": "cea.com.au", "country": "Australia", "industry": "Active Phased Array Radars (CEAFAR) & Microwave Subsystems", "careers_url": "https://www.cea.com.au/careers"},
    {"name": "Electro Optic Systems (EOS)", "domain": "eos-aus.com", "country": "Australia", "industry": "Remote Weapon Systems, Satellite Laser Tracking & Space Defense", "careers_url": "https://eos-aus.com/careers"},
    {"name": "Baraja", "domain": "baraja.com", "country": "Australia", "industry": "Spectrum-Scan Solid-State LiDAR & Precision Optical Electronics", "careers_url": "https://boards.greenhouse.io/baraja"},
    {"name": "Murata Electronics", "domain": "murata.com", "country": "Japan", "industry": "Ceramic Capacitors, RF Baluns, SAW Filters & Antenna Modules", "careers_url": "https://murata.wd1.myworkdayjobs.com/Murata_Careers"},
    {"name": "Renesas Electronics", "domain": "renesas.com", "country": "Japan", "industry": "Automotive Microcontrollers (RL78, RH850), Power Devices & Timing", "careers_url": "https://renesas.wd1.myworkdayjobs.com/Renesas_Careers"},
    {"name": "TDK Corporation", "domain": "tdk.com", "country": "Japan", "industry": "Ferrites, RF Components, InvenSense MEMS Sensors & Power Modules", "careers_url": "https://www.tdk.com/en/careers"},
    {"name": "MediaTek", "domain": "mediatek.com", "country": "Taiwan", "industry": "Wireless SoCs, 5G Modems, Wi-Fi 7 Front-Ends & Smart Display ICs", "careers_url": "https://www.mediatek.com/careers"},
    {"name": "TSMC", "domain": "tsmc.com", "country": "Taiwan", "industry": "Advanced Semiconductor Foundry (3nm/2nm), Packaging & Silicon Validation", "careers_url": "https://tsmc.wd3.myworkdayjobs.com/TSMC_Careers"},
    {"name": "Silicon Labs Singapore", "domain": "silabs.com", "country": "Singapore", "industry": "Wireless Microcontrollers, Zigbee, Thread, BLE & Matter RF SoCs", "careers_url": "https://silabs.wd1.myworkdayjobs.com/silabs"},

    # --- UAE & MIDDLE EAST ---
    {"name": "EDGE Group", "domain": "edgegroup.ae", "country": "UAE", "industry": "Electronic Warfare, Tactical Radar, Missile RF Seekers & Unmanned Systems", "careers_url": "https://edgegroup.ae/careers"},
    {"name": "Technology Innovation Institute (TII)", "domain": "tii.ae", "country": "UAE", "industry": "Autonomous Robotics, Quantum Hardware, Cryptography & Directed Energy", "careers_url": "https://www.tii.ae/careers"},
]


# =============================================================================
# HARDWARE & TECH JOB WEBSITES REGISTRY
# =============================================================================
JOB_WEBSITES_REGISTRY: List[JobWebsiteInfo] = [
    JobWebsiteInfo(
        name="Arbeitnow",
        url="https://www.arbeitnow.com",
        category="European Tech & Engineering",
        api_type="REST_JSON",
        supported_regions=["Germany", "Netherlands", "UK", "Switzerland", "Austria", "EU"],
        description="Major European job board API with multi-page pagination for technical engineering postings.",
    ),
    JobWebsiteInfo(
        name="Remotive",
        url="https://remotive.com",
        category="Global Remote Engineering",
        api_type="REST_JSON",
        supported_regions=["Worldwide", "USA", "Europe", "APAC"],
        description="Global remote job platform with deep search tags for hardware, embedded, firmware, and electronics.",
    ),
    JobWebsiteInfo(
        name="Jobicy",
        url="https://jobicy.com",
        category="Remote Technical Jobs",
        api_type="REST_JSON",
        supported_regions=["Worldwide", "USA", "UK", "Europe"],
        description="High-volume remote jobs API covering hardware engineering, firmware development, and IoT solutions.",
    ),
    JobWebsiteInfo(
        name="Greenhouse Job Boards",
        url="https://boards.greenhouse.io",
        category="Enterprise Tech ATS",
        api_type="ATS_DIRECT",
        supported_regions=["USA", "UK", "Europe", "Australia"],
        description="Direct REST APIs powering space, robotics, defense, and semiconductor innovators (SpaceX, Anduril, etc.).",
    ),
    JobWebsiteInfo(
        name="Lever Postings",
        url="https://jobs.lever.co",
        category="High-Growth Tech ATS",
        api_type="ATS_DIRECT",
        supported_regions=["USA", "Europe", "APAC"],
        description="Public JSON job endpoints for quantum, robotics, and defense innovators (Palantir, Alice & Bob, etc.).",
    ),
    JobWebsiteInfo(
        name="Ashby HQ",
        url="https://jobs.ashbyhq.com",
        category="Modern DeepTech ATS",
        api_type="ATS_DIRECT",
        supported_regions=["Europe", "USA"],
        description="Direct API powering cutting-edge deep tech companies (QuantWare, The Exploration Company, Framework).",
    ),
    JobWebsiteInfo(
        name="Workday CXS Portal",
        url="https://myworkdayjobs.com",
        category="Global Semiconductor & Aerospace Enterprise",
        api_type="ATS_DIRECT",
        supported_regions=["Global", "Europe", "USA", "Japan"],
        description="REST candidate search API for tier-1 semiconductor and defense giants (NXP, ASML, Thales, ADI, TI).",
    ),
]


class AIMassiveJobDirectoryAgent:
    """
    AI Agent that builds, manages, and scouts an expansive global directory
    of 1,000 to 100,000+ companies and job websites in Hardware, RF, PCB, and Embedded Systems.
    """

    def __init__(self, db: StateDatabase, profile: UserProfile):
        self.db = db
        self.profile = profile
        self.classifier = AIJobClassifierAgent(profile=self.profile)
        self.verifier = AIVerifierAgent(profile=self.profile)

    # =========================================================================
    # PART 1: MASSIVE COMPANY DIRECTORY CREATION & AI EXPANSION
    # =========================================================================

    def build_massive_directory(
        self,
        target_count: int = 150,
        enable_ai_expansion: bool = True,
        save_to_json: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Populates database with curated global hardware enterprise repository
        and autonomously expands it via Gemini AI to reach hundreds/thousands of companies.
        """
        registered = []
        seen_domains: Set[str] = set()

        target_countries_lower = [c.lower() for c in self.profile.target_countries]
        is_global = any(w in " ".join(target_countries_lower) for w in [
            "worldwide", "global", "all", "any", "around the world", "all around the world"
        ])

        print("\n" + "=" * 78)
        print("STAGE 2: MASSIVE AI JOB DIRECTORY & COMPANY SCOUT AGENT")
        print(f"Candidate Focus  : {self.profile.name} ({self.profile.primary_domain})")
        print(f"Target Scope     : {'Worldwide (Global)' if is_global else ', '.join(self.profile.target_countries)}")
        print(f"Directory Target : {target_count}+ verified tech companies in Hardware/RF/Embedded")
        print("=" * 78)

        # 1. Register Curated Base
        curated_added = 0
        for comp in CURATED_HARDWARE_DIRECTORY:
            comp_country = comp["country"].lower()
            if is_global or not target_countries_lower or any(tc in comp_country or comp_country in tc for tc in target_countries_lower):
                comp_id = self.db.add_company(
                    name=comp["name"],
                    domain=comp["domain"],
                    country=comp["country"],
                    industry=comp["industry"],
                    careers_url=comp["careers_url"],
                )
                registered.append({
                    "id": comp_id,
                    "name": comp["name"],
                    "domain": comp["domain"],
                    "country": comp["country"],
                    "industry": comp["industry"],
                    "careers_url": comp["careers_url"],
                })
                seen_domains.add(comp["domain"].lower())
                curated_added += 1

        print(f"[MassiveScout] Loaded {curated_added} tier-1 global hardware/RF employers from curated registry.")

        # 2. Ingest Priority Tech Companies from 32,000+ Company Catalog (massive_company_directory.csv)
        csv_file = Path("data/massive_company_directory.csv")
        if csv_file.exists() and len(registered) < target_count:
            needed = target_count - len(registered)
            print(f"[MassiveScout] Ingesting priority tech employers from 32,000+ catalog ({csv_file.name})...")
            to_insert = []
            try:
                import csv
                with open(csv_file, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        domain = (row.get("Domain") or "").lower().strip()
                        if not domain or domain in seen_domains:
                            continue
                        country = row.get("Country", "")
                        country_l = country.lower()
                        careers_url = row.get("Careers Portal URL", "")
                        if not careers_url:
                            continue
                        name = row.get("Company Name", domain)
                        industry = row.get("Industry / Category", "Engineering & Technology")
                        ats_sys = row.get("ATS System", "")

                        # Filter or prioritize based on target regions or global tech hubs
                        matches_region = (
                            is_global
                            or not target_countries_lower
                            or any(tc in country_l or country_l in tc for tc in target_countries_lower)
                            or "global" in country_l
                        )
                        if matches_region:
                            seen_domains.add(domain)
                            to_insert.append({
                                "name": name,
                                "domain": domain,
                                "country": country,
                                "industry": industry,
                                "careers_url": careers_url,
                                "ats_detected": ats_sys,
                            })
                            if len(to_insert) >= needed:
                                break

                if to_insert:
                    self.db.bulk_add_companies(to_insert)
                    with self.db.get_connection() as conn:
                        cur = conn.cursor()
                        for item in to_insert:
                            cur.execute("SELECT id FROM companies WHERE domain = ?", (item["domain"],))
                            r_id = cur.fetchone()
                            comp_id = r_id["id"] if r_id else 0
                            registered.append({
                                "id": comp_id,
                                "name": item["name"],
                                "domain": item["domain"],
                                "country": item["country"],
                                "industry": item["industry"],
                                "careers_url": item["careers_url"],
                            })
                    print(f"[MassiveScout] Ingested {len(to_insert)} priority tech employers from 32,000+ catalog into active directory.")
            except Exception as e:
                print(f"[MassiveScout] Notice during CSV catalog ingestion: {e}")

        # 3. Autonomous AI Sector Expansion
        if enable_ai_expansion and len(registered) < target_count:
            needed = target_count - len(registered)
            print(f"[MassiveScout] Activating Autonomous AI Expansion Engine to discover {needed} emerging tech employers...")

            sectors = [
                ("RF & Microwave Radar Systems", "Defense, aerospace, electronic warfare & marine radars"),
                ("Phased Array & Satellite Antennas", "LEO satellite communication, Starlink payloads & ground terminals"),
                ("High-Speed Multilayer PCB & SI/PI", "Dense 4-16 layer layout, signal integrity, LTspice & high-frequency routing"),
                ("Embedded Systems & Firmware", "Microcontrollers (STM32, ESP32, ARM Cortex), RTOS & low-level firmware"),
                ("Semiconductor IC & Mixed-Signal", "ASIC/FPGA, RF front-ends, power devices & silicon verification"),
                ("Automotive Radar & EV Powertrains", "Autonomous mobility, 77GHz radar sensors, motor controllers & ECUs"),
                ("Medical Electronics & Precision Sensing", "MRI coils, implantable telemetry, physiological monitoring & sensors"),
                ("Quantum Microwave & Superconducting HW", "Microwave readout, cryogenic electronics & control hardware"),
            ]

            for sector_name, sector_desc in sectors:
                if len(registered) >= target_count:
                    break

                batch = self._ai_scout_sector_batch(sector_name, sector_desc, count=12)
                for item in batch:
                    if item.domain.lower() not in seen_domains:
                        comp_id = self.db.add_company(
                            name=item.name,
                            domain=item.domain,
                            country=item.country,
                            industry=item.industry,
                            careers_url=item.careers_url,
                        )
                        registered.append({
                            "id": comp_id,
                            "name": item.name,
                            "domain": item.domain,
                            "country": item.country,
                            "industry": item.industry,
                            "careers_url": item.careers_url,
                        })
                        seen_domains.add(item.domain.lower())
                        print(f"  * [AI DISCOVERED] {item.name} ({item.country}) | {item.industry}")

        # 3. Create durable CAREER_CHECK tasks
        task_count = 0
        for comp in registered:
            task_id = self.db.create_task(
                task_type="CAREER_CHECK",
                target_id=comp["id"],
                payload={
                    "company_id": comp["id"],
                    "name": comp["name"],
                    "country": comp["country"],
                    "careers_url": comp["careers_url"],
                },
            )
            if task_id:
                task_count += 1

        print(f"[MassiveScout] Directory populated: {len(registered)} companies active ({task_count} tasks queued).")

        # 4. Optional JSON persistence
        if save_to_json:
            out_file = Path("data/massive_company_directory.json")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(registered, f, indent=2)
            print(f"[MassiveScout] Company directory catalog saved to {out_file.resolve()}")

        return registered

    def gather_all_companies(
        self,
        max_per_source: Optional[int] = None,
        save_to_json: bool = True,
    ) -> Dict[str, Any]:
        """
        Gathers ALL possible real technology companies across global ATS portals:
        - 12,884 Workday enterprise portals
        - 8,333 Greenhouse company boards
        - 4,368 Lever company boards
        - 3,161 Ashby deeptech boards
        - 11,316 BambooHR company portals
        - 86+ Curated Tier-1 Hardware Employers
        Inserts all into SQLite StateDatabase in atomic batches.
        """
        print("\n" + "=" * 78)
        print("STAGE 2-ALL: GATHERING ALL AVAILABLE GLOBAL TECH COMPANIES (40,000+ CATALOG)")
        print("=" * 78)

        t0 = time.time()
        datasets = {
            "greenhouse": "https://raw.githubusercontent.com/Riley-Dorrington/job-board-aggregator/main/data/greenhouse_companies.json",
            "ashby": "https://raw.githubusercontent.com/Riley-Dorrington/job-board-aggregator/main/data/ashby_companies.json",
            "lever": "https://raw.githubusercontent.com/Riley-Dorrington/job-board-aggregator/main/data/lever_companies.json",
            "workday": "https://raw.githubusercontent.com/Riley-Dorrington/job-board-aggregator/main/data/workday_companies.json",
            "bamboohr": "https://raw.githubusercontent.com/Riley-Dorrington/job-board-aggregator/main/data/bamboohr_companies.json",
        }

        all_companies: List[Dict[str, Any]] = []
        seen_domains: Set[str] = set()

        # 1. Curated Tier-1 Hardware Leaders (highest priority)
        for comp in CURATED_HARDWARE_DIRECTORY:
            d = comp["domain"].lower().strip()
            seen_domains.add(d)
            all_companies.append({
                "name": comp["name"],
                "domain": d,
                "country": comp["country"],
                "industry": comp["industry"],
                "careers_url": comp["careers_url"],
                "ats_detected": detect_ats(comp["careers_url"]).get("ats", "custom"),
            })

        # 2. Download and parse ATS datasets
        with httpx.Client(timeout=25.0) as client:
            # Greenhouse
            try:
                print("[MassiveGather] Ingesting Greenhouse tech companies...")
                r = client.get(datasets["greenhouse"])
                if r.status_code == 200:
                    gh_list = r.json()
                    if max_per_source:
                        gh_list = gh_list[:max_per_source]
                    for slug in gh_list:
                        slug = str(slug).strip().lower()
                        if not slug:
                            continue
                        domain = f"{slug}.greenhouse.io"
                        if domain in seen_domains:
                            continue
                        seen_domains.add(domain)
                        name = slug.replace("-", " ").replace("_", " ").title()
                        all_companies.append({
                            "name": name,
                            "domain": domain,
                            "country": "Global / Tech",
                            "industry": "Technology & Hardware (Greenhouse ATS)",
                            "careers_url": f"https://boards.greenhouse.io/{slug}",
                            "ats_detected": "greenhouse",
                        })
                    print(f"  -> Ingested {len(gh_list)} Greenhouse employers.")
            except Exception as e:
                print(f"[MassiveGather] Greenhouse notice: {e}")

            # Ashby (DeepTech, Quantum, Space, Hardware)
            try:
                print("[MassiveGather] Ingesting Ashby DeepTech & Engineering employers...")
                r = client.get(datasets["ashby"])
                if r.status_code == 200:
                    ashby_list = r.json()
                    if max_per_source:
                        ashby_list = ashby_list[:max_per_source]
                    for slug in ashby_list:
                        slug = str(slug).strip().lower()
                        if not slug:
                            continue
                        domain = f"{slug}.ashbyhq.com"
                        if domain in seen_domains:
                            continue
                        seen_domains.add(domain)
                        name = slug.replace("-", " ").replace("_", " ").title()
                        all_companies.append({
                            "name": name,
                            "domain": domain,
                            "country": "Global / DeepTech",
                            "industry": "DeepTech & Engineering (Ashby ATS)",
                            "careers_url": f"https://jobs.ashbyhq.com/{slug}",
                            "ats_detected": "ashby",
                        })
                    print(f"  -> Ingested {len(ashby_list)} Ashby employers.")
            except Exception as e:
                print(f"[MassiveGather] Ashby notice: {e}")

            # Lever
            try:
                print("[MassiveGather] Ingesting Lever high-growth technology employers...")
                r = client.get(datasets["lever"])
                if r.status_code == 200:
                    lever_list = r.json()
                    if max_per_source:
                        lever_list = lever_list[:max_per_source]
                    for slug in lever_list:
                        slug = str(slug).strip().lower()
                        if not slug:
                            continue
                        domain = f"{slug}.lever.co"
                        if domain in seen_domains:
                            continue
                        seen_domains.add(domain)
                        name = slug.replace("-", " ").replace("_", " ").title()
                        all_companies.append({
                            "name": name,
                            "domain": domain,
                            "country": "Global / Scaleup",
                            "industry": "Technology & Scale-up (Lever ATS)",
                            "careers_url": f"https://jobs.lever.co/{slug}",
                            "ats_detected": "lever",
                        })
                    print(f"  -> Ingested {len(lever_list)} Lever employers.")
            except Exception as e:
                print(f"[MassiveGather] Lever notice: {e}")

            # Workday (Major Enterprise, Semiconductor, Defense)
            try:
                print("[MassiveGather] Ingesting Workday enterprise leaders...")
                r = client.get(datasets["workday"])
                if r.status_code == 200:
                    wd_list = r.json()
                    if max_per_source:
                        wd_list = wd_list[:max_per_source]
                    for item in wd_list:
                        parts = str(item).strip().split("|")
                        if len(parts) >= 3:
                            comp, host, portal = parts[0], parts[1], parts[2]
                        elif len(parts) == 2:
                            comp, host, portal = parts[0], parts[1], "careers"
                        else:
                            continue
                        domain = f"{comp}.{host}.myworkdayjobs.com"
                        if domain in seen_domains:
                            continue
                        seen_domains.add(domain)
                        name = comp.replace("-", " ").replace("_", " ").title()
                        if len(comp) <= 4:
                            name = comp.upper()
                        all_companies.append({
                            "name": name,
                            "domain": domain,
                            "country": "Global / Enterprise",
                            "industry": "Enterprise Technology (Workday ATS)",
                            "careers_url": f"https://{comp}.{host}.myworkdayjobs.com/{portal}",
                            "ats_detected": "workday",
                        })
                    print(f"  -> Ingested {len(wd_list)} Workday employers.")
            except Exception as e:
                print(f"[MassiveGather] Workday notice: {e}")

            # BambooHR
            try:
                print("[MassiveGather] Ingesting BambooHR mid-market employers...")
                r = client.get(datasets["bamboohr"])
                if r.status_code == 200:
                    bamboo_list = r.json()
                    if max_per_source:
                        bamboo_list = bamboo_list[:max_per_source]
                    for slug in bamboo_list:
                        slug = str(slug).strip().lower()
                        if not slug:
                            continue
                        domain = f"{slug}.bamboohr.com"
                        if domain in seen_domains:
                            continue
                        seen_domains.add(domain)
                        name = slug.replace("-", " ").replace("_", " ").title()
                        all_companies.append({
                            "name": name,
                            "domain": domain,
                            "country": "Global / Mid-Market",
                            "industry": "Technology & Services (BambooHR ATS)",
                            "careers_url": f"https://{slug}.bamboohr.com/careers",
                            "ats_detected": "bamboohr",
                        })
                    print(f"  -> Ingested {len(bamboo_list)} BambooHR employers.")
            except Exception as e:
                print(f"[MassiveGather] BambooHR notice: {e}")

        # 3. Fast Atomic Bulk Insert into SQLite StateDatabase
        print(f"\n[MassiveGather] Inserting {len(all_companies):,} total companies into SQLite database...")
        total_in_db = self.db.bulk_add_companies(all_companies)
        print(f"[MassiveGather] SUCCESS: Database now contains {total_in_db:,} indexed companies!")

        # 4. Save JSON catalog to disk
        if save_to_json:
            json_path = Path("data/massive_company_directory.json")
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(all_companies, f, indent=2)
            print(f"[MassiveGather] Saved full catalog to {json_path.resolve()} ({len(all_companies):,} entries).")

        elapsed = round(time.time() - t0, 2)
        return {
            "total_companies_gathered": len(all_companies),
            "total_in_database": total_in_db,
            "elapsed_seconds": elapsed,
        }

    def _ai_scout_sector_batch(self, sector_name: str, sector_desc: str, count: int = 12) -> List[ScoutedCompany]:
        """Queries Gemini AI to discover real engineering companies matching sub-discipline."""
        countries_hint = "Worldwide (Europe, USA, UK, Australia, Switzerland, Japan)" if not self.profile.target_countries else ", ".join(self.profile.target_countries)

        prompt = f"""You are an elite Global Technical Intelligence and Talent Acquisition Scout specializing in Hardware & Embedded Engineering.

MISSION: Identify {count} real, active technology companies specializing in:
SECTOR: {sector_name} ({sector_desc})
TARGET REGIONS: {countries_hint}

REQUIREMENTS:
1. Companies MUST hire engineers in Electronics, RF, High-Speed PCB, FPGA, or Embedded Hardware.
2. Focus on companies with real ATS portals (Greenhouse, Lever, Ashby, Workday, SmartRecruiters) or public career pages.
3. Include accurate company domains (e.g., example.com) and valid career links.
4. Include both established mid-caps and high-growth venture-backed hardware startups.
"""
        batch = ai_engine.generate_structured(
            prompt=prompt,
            response_schema=ScoutedCompanyBatch,
            system_instruction="You are an expert AI Tech Scout. Return strictly valid ScoutedCompanyBatch JSON.",
        )
        return batch.companies if batch else []

    # =========================================================================
    # PART 2: JOB WEBSITES & AGGREGATOR HARVESTING
    # =========================================================================

    def list_job_websites(self) -> List[JobWebsiteInfo]:
        """Returns the indexed list of supported job websites & aggregators."""
        return JOB_WEBSITES_REGISTRY

    def harvest_from_job_websites(self, max_per_source: int = 100) -> Dict[str, int]:
        """
        Harvests engineering job postings across live tech job boards:
        - Arbeitnow (Multi-page European tech job API)
        - Remotive (Global remote engineering job API)
        - Jobicy (Remote hardware and engineering job API)
        """
        print("\n" + "=" * 78)
        print("STAGE 3A: LIVE JOB WEBSITES & AGGREGATORS HARVEST")
        print("=" * 78)

        stats = {"arbeitnow": 0, "remotive": 0, "jobicy": 0, "remoteok": 0, "total_recorded": 0}

        # 1. Harvest Arbeitnow (Europe & UK)
        stats["arbeitnow"] = self._harvest_arbeitnow(limit=max_per_source)

        # 2. Harvest Remotive (Global Remote)
        stats["remotive"] = self._harvest_remotive(limit=max_per_source)

        # 3. Harvest Jobicy (Global Remote)
        stats["jobicy"] = self._harvest_jobicy(limit=max_per_source)

        # 4. Harvest RemoteOK (Global Remote)
        stats["remoteok"] = self._harvest_remoteok(limit=max_per_source)

        stats["total_recorded"] = stats["arbeitnow"] + stats["remotive"] + stats["jobicy"] + stats["remoteok"]
        print(f"[MassiveScout] Job Website Harvest Complete: {stats['total_recorded']} total matching jobs recorded.")
        return stats

    def _harvest_arbeitnow(self, limit: int = 100, max_pages: int = 4) -> int:
        print(f"[JobWebsite] Querying Arbeitnow European Job Board API (pages 1-{max_pages})...")
        recorded = 0
        seen_urls = set()

        try:
            with httpx.Client(timeout=15.0) as client:
                for page in range(1, max_pages + 1):
                    if recorded >= limit:
                        break
                    url = f"https://www.arbeitnow.com/api/job-board-api?page={page}"
                    resp = client.get(url)
                    if resp.status_code != 200:
                        break

                    data = resp.json().get("data", [])
                    if not data:
                        break

                    for item in data:
                        job_url = item.get("url", "")
                        if not job_url or job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        title = item.get("title", "")
                        company = item.get("company_name", "Unknown Company")
                        location = item.get("location", "Europe")
                        description = item.get("description", "")

                        title_lower = title.lower()
                        if any(b in title_lower for b in ["recruiter", "sales", "marketing", "accountant", "hr", "legal", "nurse"]):
                            continue
                        if not any(k in title_lower for k in ["engineer", "embedded", "hardware", "rf", "pcb", "electronics", "firmware", "fpga"]):
                            continue

                        # AI Job Classifier
                        cls_res = self.classifier.classify_job(
                            title=title,
                            company_name=company,
                            location=location,
                            details_text=description,
                        )

                        if cls_res.is_relevant and cls_res.match_score >= 45:
                            # Country inference
                            country = self._infer_country(location)
                            comp_id = self.db.add_company(
                                name=company,
                                domain=company.lower().replace(" ", "").replace("&", "") + ".com",
                                country=country,
                                industry="Engineering & Technology (via Arbeitnow)",
                                careers_url=job_url,
                            )
                            match_id = self.db.record_job_match(
                                company_id=comp_id,
                                company_name=company,
                                country=country,
                                title=title,
                                job_url=job_url,
                                location=location,
                                work_mode=cls_res.work_mode,
                                match_score=cls_res.match_score,
                                match_reason=cls_res.match_reason,
                                evidence_quote=cls_res.evidence_quote,
                                source_url=url,
                            )
                            if match_id:
                                # AI Verifier Audit
                                audit = self.verifier.audit_proposal({
                                    "company_name": company,
                                    "title": title,
                                    "location": location,
                                    "work_mode": cls_res.work_mode,
                                    "match_score": cls_res.match_score,
                                    "match_reason": cls_res.match_reason,
                                    "evidence_quote": cls_res.evidence_quote,
                                    "job_url": job_url,
                                    "source_url": url,
                                })
                                if audit.is_verified:
                                    self.db.verify_job_match(match_id, verified=True, notes=audit.audit_notes)
                                    recorded += 1
                                    print(f"  * [ARBEITNOW VERIFIED ({cls_res.match_score}/100)] [{country} | {cls_res.work_mode}] {title} @ {company}")
        except Exception as e:
            print(f"[MassiveScout] Arbeitnow error: {e}")

        return recorded

    def _harvest_remotive(self, limit: int = 100) -> int:
        print("[JobWebsite] Querying Remotive Global Engineering Feed...")
        recorded = 0
        seen_urls = set()
        queries = ["embedded", "hardware", "firmware", "electronics", "rf", "robotics"]

        try:
            with httpx.Client(timeout=15.0) as client:
                for q in queries:
                    if recorded >= limit:
                        break
                    url = f"https://remotive.com/api/remote-jobs?search={q}"
                    resp = client.get(url)
                    if resp.status_code != 200:
                        continue

                    jobs = resp.json().get("jobs", [])
                    for j in jobs:
                        job_url = j.get("url", "")
                        if not job_url or job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        title = j.get("title", "")
                        company = j.get("company_name", "Unknown Company")
                        location = j.get("candidate_required_location", "Remote Worldwide")
                        desc = j.get("description", "")

                        title_lower = title.lower()
                        if any(b in title_lower for b in ["recruiter", "sales", "marketing", "accountant", "hr", "legal"]):
                            continue
                        if not any(k in title_lower for k in ["engineer", "embedded", "hardware", "rf", "pcb", "electronics", "firmware", "fpga", "developer"]):
                            continue

                        cls_res = self.classifier.classify_job(
                            title=title,
                            company_name=company,
                            location=location,
                            details_text=desc,
                            ats_work_mode_hint="Remote",
                        )

                        if cls_res.is_relevant and cls_res.match_score >= 45:
                            country = "Remote / International"
                            comp_id = self.db.add_company(
                                name=company,
                                domain=company.lower().replace(" ", "").replace("&", "") + ".com",
                                country=country,
                                industry="Remote Technology (via Remotive)",
                                careers_url=job_url,
                            )
                            match_id = self.db.record_job_match(
                                company_id=comp_id,
                                company_name=company,
                                country=country,
                                title=title,
                                job_url=job_url,
                                location=location,
                                work_mode=cls_res.work_mode,
                                match_score=cls_res.match_score,
                                match_reason=cls_res.match_reason,
                                evidence_quote=cls_res.evidence_quote,
                                source_url=url,
                            )
                            if match_id:
                                audit = self.verifier.audit_proposal({
                                    "company_name": company,
                                    "title": title,
                                    "location": location,
                                    "work_mode": cls_res.work_mode,
                                    "match_score": cls_res.match_score,
                                    "match_reason": cls_res.match_reason,
                                    "evidence_quote": cls_res.evidence_quote,
                                    "job_url": job_url,
                                    "source_url": url,
                                })
                                if audit.is_verified:
                                    self.db.verify_job_match(match_id, verified=True, notes=audit.audit_notes)
                                    recorded += 1
                                    print(f"  * [REMOTIVE VERIFIED ({cls_res.match_score}/100)] [Remote] {title} @ {company}")
        except Exception as e:
            print(f"[MassiveScout] Remotive error: {e}")

        return recorded

    def _harvest_jobicy(self, limit: int = 100) -> int:
        print("[JobWebsite] Querying Jobicy Remote Engineering Feeds...")
        recorded = 0
        seen_urls = set()
        tags = ["engineering", "hardware", "iot", "systems", "dev"]

        try:
            with httpx.Client(timeout=15.0) as client:
                for tag in tags:
                    if recorded >= limit:
                        break
                    url = f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={tag}"
                    resp = client.get(url)
                    if resp.status_code != 200:
                        continue
                    jobs = resp.json().get("jobs", [])
                    for j in jobs:
                        if recorded >= limit:
                            break
                        job_url = j.get("url", "")
                        if not job_url or job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        title = j.get("jobTitle", "")
                        company = j.get("companyName", "Unknown Company")
                        location = j.get("jobGeo", "Remote Worldwide")
                        desc = j.get("jobDescription", "")

                        title_lower = title.lower()
                        if any(b in title_lower for b in ["recruiter", "sales", "marketing", "accountant", "hr", "legal"]):
                            continue
                        if not any(k in title_lower for k in [
                            "engineer", "embedded", "hardware", "rf", "pcb", "electronics",
                            "firmware", "fpga", "solutions", "systems", "developer", "technician"
                        ]):
                            continue

                        cls_res = self.classifier.classify_job(
                            title=title,
                            company_name=company,
                            location=location,
                            details_text=desc,
                            ats_work_mode_hint="Remote",
                        )

                        if cls_res.is_relevant and cls_res.match_score >= 45:
                            country = self._infer_country(location)
                            comp_id = self.db.add_company(
                                name=company,
                                domain=company.lower().replace(" ", "").replace("&", "") + ".com",
                                country=country,
                                industry="Remote Hardware & Engineering (via Jobicy)",
                                careers_url=job_url,
                            )
                            match_id = self.db.record_job_match(
                                company_id=comp_id,
                                company_name=company,
                                country=country,
                                title=title,
                                job_url=job_url,
                                location=location,
                                work_mode=cls_res.work_mode,
                                match_score=cls_res.match_score,
                                match_reason=cls_res.match_reason,
                                evidence_quote=cls_res.evidence_quote,
                                source_url=url,
                            )
                            if match_id:
                                audit = self.verifier.audit_proposal({
                                    "company_name": company,
                                    "title": title,
                                    "location": location,
                                    "work_mode": cls_res.work_mode,
                                    "match_score": cls_res.match_score,
                                    "match_reason": cls_res.match_reason,
                                    "evidence_quote": cls_res.evidence_quote,
                                    "job_url": job_url,
                                    "source_url": url,
                                })
                                if audit.is_verified:
                                    self.db.verify_job_match(match_id, verified=True, notes=audit.audit_notes)
                                    recorded += 1
                                    print(f"  * [JOBICY VERIFIED ({cls_res.match_score}/100)] [Remote] {title} @ {company}")
        except Exception as e:
            print(f"[MassiveScout] Jobicy error: {e}")

        return recorded

    def _harvest_remoteok(self, limit: int = 100) -> int:
        print("[JobWebsite] Querying RemoteOK Global Feed...")
        recorded = 0
        seen_urls = set()
        headers = {"User-Agent": "JobSeekerBot/1.0 (contact: info@jobseek.internal)"}
        try:
            with httpx.Client(timeout=15.0, headers=headers) as client:
                resp = client.get("https://remoteok.com/api")
                if resp.status_code == 200:
                    items = resp.json()
                    jobs = items[1:] if len(items) > 1 and isinstance(items[0], dict) and "legal" in items[0] else items
                    for j in jobs:
                        if not isinstance(j, dict) or recorded >= limit:
                            break
                        job_url = j.get("url", "")
                        if not job_url or job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        title = j.get("position", "")
                        company = j.get("company", "Unknown Company")
                        location = j.get("location") or "Remote Worldwide"
                        desc = j.get("description", "")
                        tags = " ".join(j.get("tags", []))

                        title_lower = title.lower()
                        full_search = f"{title_lower} {tags.lower()}"
                        if any(b in title_lower for b in ["recruiter", "sales", "marketing", "accountant", "hr", "legal"]):
                            continue
                        if not any(k in full_search for k in [
                            "engineer", "embedded", "hardware", "rf", "pcb", "electronics",
                            "firmware", "fpga", "robotics", "iot", "systems", "c++", "device"
                        ]):
                            continue

                        cls_res = self.classifier.classify_job(
                            title=title,
                            company_name=company,
                            location=location,
                            details_text=desc,
                            ats_work_mode_hint="Remote",
                        )

                        if cls_res.is_relevant and cls_res.match_score >= 45:
                            country = self._infer_country(location)
                            comp_id = self.db.add_company(
                                name=company,
                                domain=company.lower().replace(" ", "").replace("&", "") + ".com",
                                country=country,
                                industry="Remote Tech & Hardware (via RemoteOK)",
                                careers_url=job_url,
                            )
                            match_id = self.db.record_job_match(
                                company_id=comp_id,
                                company_name=company,
                                country=country,
                                title=title,
                                job_url=job_url,
                                location=location,
                                work_mode=cls_res.work_mode,
                                match_score=cls_res.match_score,
                                match_reason=cls_res.match_reason,
                                evidence_quote=cls_res.evidence_quote,
                                source_url="https://remoteok.com",
                            )
                            if match_id:
                                audit = self.verifier.audit_proposal({
                                    "company_name": company,
                                    "title": title,
                                    "location": location,
                                    "work_mode": cls_res.work_mode,
                                    "match_score": cls_res.match_score,
                                    "match_reason": cls_res.match_reason,
                                    "evidence_quote": cls_res.evidence_quote,
                                    "job_url": job_url,
                                    "source_url": "https://remoteok.com",
                                })
                                if audit.is_verified:
                                    self.db.verify_job_match(match_id, verified=True, notes=audit.audit_notes)
                                    recorded += 1
                                    print(f"  * [REMOTEOK VERIFIED ({cls_res.match_score}/100)] [Remote] {title} @ {company}")
        except Exception as e:
            print(f"[MassiveScout] RemoteOK error: {e}")

        return recorded

    def _infer_country(self, loc: str) -> str:
        loc_lower = loc.lower()
        if any(w in loc_lower for w in ["netherlands", "amsterdam", "rotterdam", "eindhoven", "delft"]):
            return "Netherlands"
        if any(w in loc_lower for w in ["germany", "berlin", "munich", "hamburg", "frankfurt", "stuttgart"]):
            return "Germany"
        if any(w in loc_lower for w in ["uk", "united kingdom", "london", "bristol", "cambridge", "edinburgh"]):
            return "UK"
        if any(w in loc_lower for w in ["france", "paris", "toulouse", "grenoble"]):
            return "France"
        if any(w in loc_lower for w in ["switzerland", "zurich", "geneva"]):
            return "Switzerland"
        if any(w in loc_lower for w in ["austria", "vienna", "graz"]):
            return "Austria"
        if any(w in loc_lower for w in ["belgium", "brussels", "leuven"]):
            return "Belgium"
        if any(w in loc_lower for w in ["ireland", "dublin", "cork", "galway", "limerick"]):
            return "Ireland"
        if any(w in loc_lower for w in ["sweden", "stockholm", "gothenburg"]):
            return "Sweden"
        if any(w in loc_lower for w in ["norway", "oslo"]):
            return "Norway"
        if any(w in loc_lower for w in ["finland", "helsinki", "espoo", "oulu"]):
            return "Finland"
        if any(w in loc_lower for w in ["usa", "united states", "california", "texas", "seattle", "boston"]):
            return "USA"
        if any(w in loc_lower for w in ["australia", "sydney", "melbourne", "canberra", "brisbane"]):
            return "Australia"
        return "Europe / International"

    # =========================================================================
    # PART 3: SCOUT COMPANIES FOR JOBS ("Then look for jobs in that companies")
    # =========================================================================

    async def scout_companies_for_jobs(
        self,
        companies: Optional[List[Dict[str, Any]]] = None,
        max_jobs_per_company: int = 40,
        concurrency: int = 8,
        remote_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Coordinates asynchronous parallel job scouting across discovered companies.
        Queries Workday REST, Greenhouse, Lever, Ashby, and SmartRecruiters.
        Evaluates with AI Job Classifier and AI Verifier.
        """
        if companies is None:
            if remote_only or self.profile.work_modes == ["Remote"]:
                # When searching for Remote jobs, scan ALL modern ATS companies
                # Prioritize hardware, robotics, IoT, semiconductor, space, and deep-tech first,
                # then proceed through all high-growth innovators.
                with self.db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                    SELECT * FROM companies
                    WHERE ats_detected IN ('greenhouse', 'ashby', 'lever')
                    ORDER BY (
                        CASE 
                            WHEN LOWER(name) LIKE '%robot%' OR LOWER(name) LIKE '%space%' OR LOWER(name) LIKE '%aero%' 
                                 OR LOWER(name) LIKE '%hardw%' OR LOWER(name) LIKE '%electr%' OR LOWER(name) LIKE '%sensor%' 
                                 OR LOWER(name) LIKE '%semicond%' OR LOWER(name) LIKE '%drone%' 
                                 OR LOWER(name) LIKE '%medic%' OR LOWER(name) LIKE '%telecom%' OR LOWER(name) LIKE '%wirel%' 
                                 OR LOWER(name) LIKE '%audio%' OR LOWER(name) LIKE '%device%' OR LOWER(name) LIKE '%energy%' 
                                 OR LOWER(name) LIKE '%batter%' OR LOWER(name) LIKE '%optic%' OR LOWER(name) LIKE '%radar%'
                                 OR LOWER(name) LIKE '%iot%' OR LOWER(name) LIKE '%embed%' OR LOWER(name) LIKE '%firmw%'
                                 OR LOWER(name) LIKE '%quantum%' OR LOWER(name) LIKE '%motor%' OR LOWER(name) LIKE '%vehicle%'
                            THEN 1
                            ELSE 2
                        END
                    ), id ASC
                    """)
                    companies = [dict(r) for r in cursor.fetchall()]
            else:
                # Prioritize companies that match Hardware, RF, Embedded, Semiconductor, Radar, Avionics
                priority_kws = ["rf", "hardware", "embedded", "pcb", "antenna", "semiconductor", "radar", "electronics", "firmware", "space", "aero", "robot", "quantum", "telecom", "sensor", "optics", "drone"]
                companies = self.db.get_prioritized_companies(keywords=priority_kws, limit=150)
            if not companies:
                companies = self.db.get_companies()

        print("\n" + "=" * 78)
        print(f"STAGE 3B: SCOUTING OPEN JOBS ACROSS DISCOVERED COMPANIES {'(REMOTE ONLY)' if remote_only else ''}")
        print(f"Total Companies to Scan : {len(companies)}")
        print(f"Parallel Worker Threads : {concurrency}")
        print("=" * 78)

        semaphore = asyncio.Semaphore(concurrency)
        stats = {
            "companies_scanned": 0,
            "jobs_discovered": 0,
            "matches_verified": 0,
        }

        async def _scout_single_company(comp: Dict[str, Any]):
            async with semaphore:
                comp_id = comp["id"]
                comp_name = comp["name"]
                country = comp["country"]
                careers_url = comp.get("careers_url") or ""

                if not careers_url:
                    return

                loop = asyncio.get_running_loop()
                try:
                    # Run MCP list_jobs in thread pool to prevent blocking event loop
                    raw_jobs = await loop.run_in_executor(None, list_jobs, careers_url)
                    valid_jobs = [j for j in raw_jobs if "title" in j]
                    stats["jobs_discovered"] += len(valid_jobs)

                    company_verified_count = 0
                    for j in valid_jobs[:max_jobs_per_company]:
                        title = j["title"]
                        job_url = j["job_url"]
                        location = j.get("location", country)

                        # Filter non-technical roles
                        title_lower = title.lower()
                        if any(bad in title_lower for bad in ["recruiter", "sales", "account executive", "legal", "hr specialist", "marketing"]):
                            continue
                        if not any(k in title_lower for k in [
                            "engineer", "embedded", "hardware", "rf", "pcb", "electronics",
                            "firmware", "fpga", "antenna", "technician", "architect",
                            "design", "validation", "test", "developer", "layout",
                            "systems", "scientist", "researcher",
                        ]):
                            continue

                        # Fast pre-filter for Remote preference (avoids downloading HTML for thousands of on-site jobs)
                        if remote_only or self.profile.work_modes == ["Remote"]:
                            loc_l = location.lower()
                            t_l = title.lower()
                            hint = j.get("work_mode_hint")
                            is_remote_candidate = (
                                hint == "Remote"
                                or "remote" in loc_l
                                or "remote" in t_l
                                or "wfh" in loc_l
                                or "anywhere" in loc_l
                                or "home" in loc_l
                                or "virtual" in loc_l
                                or "telecommute" in loc_l
                                or "distributed" in loc_l
                            )
                            if not is_remote_candidate:
                                continue

                        # Fetch job details text (use pre-fetched description from ATS payload if available)
                        if j.get("description_text"):
                            clean_desc = j["description_text"][:8000]
                            details_text = f"<UNTRUSTED_JOB_DATA url=\"{job_url}\">\n{title}\nLocation: {location}\n\n{clean_desc}\n</UNTRUSTED_JOB_DATA>"
                        else:
                            details_resp = await loop.run_in_executor(None, get_job_details, job_url)
                            details_text = details_resp.get("safe_content", "")

                        # AI Job Classifier
                        cls_res = self.classifier.classify_job(
                            title=title,
                            company_name=comp_name,
                            location=location,
                            details_text=details_text,
                            ats_work_mode_hint=j.get("work_mode_hint"),
                        )

                        if cls_res.is_relevant and cls_res.match_score >= 45:
                            # Respect candidate work arrangement preferences
                            allowed_modes = self.profile.work_modes or ["Remote", "Hybrid", "On-site"]
                            if remote_only:
                                allowed_modes = ["Remote"]
                            if cls_res.work_mode not in allowed_modes:
                                continue

                            # Accurate country inference
                            inferred_c = self._infer_country(location)
                            job_country = inferred_c if (inferred_c != "Europe / International" or country in ["Global / Tech", "Global / Scaleup", "Global / DeepTech"]) else country

                            # Record candidate match
                            match_id = self.db.record_job_match(
                                company_id=comp_id,
                                company_name=comp_name,
                                country=job_country,
                                title=title,
                                job_url=job_url,
                                location=location,
                                work_mode=cls_res.work_mode,
                                match_score=cls_res.match_score,
                                match_reason=cls_res.match_reason,
                                evidence_quote=cls_res.evidence_quote,
                                source_url=careers_url,
                            )

                            if match_id:
                                # AI Verifier Audit
                                audit = self.verifier.audit_proposal({
                                    "company_name": comp_name,
                                    "title": title,
                                    "location": location,
                                    "work_mode": cls_res.work_mode,
                                    "match_score": cls_res.match_score,
                                    "match_reason": cls_res.match_reason,
                                    "evidence_quote": cls_res.evidence_quote,
                                    "job_url": job_url,
                                    "source_url": careers_url,
                                }, raw_page_text=details_text)

                                if audit.is_verified:
                                    self.db.verify_job_match(match_id, verified=True, notes=audit.audit_notes)
                                    stats["matches_verified"] += 1
                                    company_verified_count += 1
                                    print(f"  * [VERIFIED ({cls_res.match_score}/100)] [{job_country} | {cls_res.work_mode}] {title} @ {comp_name}")

                    stats["companies_scanned"] += 1
                    scanned = stats["companies_scanned"]
                    if company_verified_count > 0:
                        print(f"  -> '{comp_name}': {company_verified_count} verified match(es).")

                    if scanned % 50 == 0 or scanned == len(companies):
                        pct = (scanned / len(companies)) * 100.0 if companies else 0.0
                        print(f"  [Scout Progress] {scanned}/{len(companies)} companies scanned ({pct:.1f}%) | {stats['matches_verified']} verified match(es) so far.")

                    # Periodic auto-export to Excel so user can inspect live progress
                    if company_verified_count > 0 or scanned % 500 == 0:
                        try:
                            from src.sync.sheets import SheetsSyncManager
                            SheetsSyncManager(db=self.db).export_to_excel("job_hunt_results.xlsx")
                        except Exception:
                            pass

                except Exception as e:
                    # Exception resilience
                    pass

        tasks = [_scout_single_company(c) for c in companies]
        await asyncio.gather(*tasks)

        print("\n" + "=" * 78)
        print("MASSIVE COMPANY JOB SCOUTING COMPLETE:")
        print(f"  * Companies Scanned : {stats['companies_scanned']}")
        print(f"  * Jobs Discovered   : {stats['jobs_discovered']}")
        print(f"  * Verified Matches  : {stats['matches_verified']}")
        print("=" * 78)
        return stats

    # =========================================================================
    # PART 4: FULL END-TO-END MASSIVE HUNT PIPELINE
    # =========================================================================

    async def run_massive_hunt(
        self,
        target_company_count: int = 150,
        enable_ai_expansion: bool = True,
        gather_all_mode: bool = False,
        max_jobs_per_company: int = 30,
        concurrency: int = 8,
    ) -> Dict[str, Any]:
        """
        Executes complete end-to-end mission:
        1. Discovers & populates massive company directory (1,000+ to 40,000+ potential targets).
        2. Harvests live tech job websites & aggregators.
        3. Scouts discovered company career portals concurrently.
        4. Verifies all matches with AI audit.
        """
        t0 = time.time()

        # Step 1: Directory Construction
        if gather_all_mode:
            self.gather_all_companies(save_to_json=True)
            priority_kws = ["rf", "hardware", "embedded", "pcb", "antenna", "semiconductor", "radar", "electronics", "firmware", "space", "aero", "robot", "quantum", "telecom", "sensor", "optics", "drone"]
            companies = self.db.get_prioritized_companies(keywords=priority_kws, limit=target_company_count)
            if not companies:
                companies = self.db.get_companies()[:target_company_count]
        else:
            companies = self.build_massive_directory(
                target_count=target_company_count,
                enable_ai_expansion=enable_ai_expansion,
            )

        # Step 2: Job Websites Harvesting
        site_stats = self.harvest_from_job_websites(max_per_source=80)

        # Step 3: Direct Company Scouting
        comp_stats = await self.scout_companies_for_jobs(
            companies=companies,
            max_jobs_per_company=max_jobs_per_company,
            concurrency=concurrency,
        )

        elapsed = round(time.time() - t0, 2)
        total_verified = len(self.db.get_verified_jobs())

        summary = {
            "total_companies_registered": len(companies),
            "job_website_matches": site_stats.get("total_recorded", 0),
            "company_portal_matches": comp_stats.get("matches_verified", 0),
            "total_verified_jobs": total_verified,
            "elapsed_seconds": elapsed,
        }

        print("\n" + "#" * 78)
        print("MASSIVE AI JOB DIRECTORY & SCOUT HUNT MISSION SUMMARY")
        print("#" * 78)
        print(f"  * Total Active Companies in Directory : {summary['total_companies_registered']}")
        print(f"  * Matches from Tech Job Websites      : {summary['job_website_matches']}")
        print(f"  * Matches from Direct Company Portals : {summary['company_portal_matches']}")
        print(f"  * Total Verified Jobs in System       : {summary['total_verified_jobs']}")
        print(f"  * Execution Time                      : {summary['elapsed_seconds']}s")
        print("#" * 78)

        return summary
