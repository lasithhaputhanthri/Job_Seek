"""
Phase 9+: AI Global Company Scout & Massive Employer Harvester Agent.
Discovers, indexes, and monitors a massive catalog of global engineering employers
(1,000 to 100,000 potential targets) across:
- RF, Microwave, Radar & Phased Array Antennas
- Embedded Systems, RTOS, Firmware, Robotics & IoT
- Semiconductors, ASIC, FPGA, Mixed-Signal & IC Packaging
- Aerospace, Satellite Communications, Spacecraft & Defense Electronics
- Automotive Radar, EV Powertrains & Autonomous Mobility
- Medical Devices, Precision Instrumentation & Sensing
- Quantum Hardware & Next-Gen Physics Computing

Capabilities:
1. Curated global enterprise registry with verified ATS career endpoints (Workday, Greenhouse, Lever, Ashby, SmartRecruiters).
2. Autonomous AI sector & regional discovery using Gemini Pro / Flash.
3. Durable SQLite registration and task creation.
4. Autonomous job scouting across discovered companies.
"""

import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from src.agents.classifier import AIJobClassifierAgent
from src.agents.llm_engine import ai_engine
from src.agents.verifier import AIVerifierAgent
from src.db import StateDatabase
from src.schemas import UserProfile
from mcp_servers.career_page_reader.server import list_jobs, get_job_details, detect_ats


from src.agents.massive_scout import (
    AIMassiveJobDirectoryAgent,
    ScoutedCompany,
    ScoutedCompanyBatch,
    CURATED_HARDWARE_DIRECTORY as MASSIVE_GLOBAL_EMPLOYERS,
)

# For backward compatibility
AIGlobalCompanyScoutAgent = AIMassiveJobDirectoryAgent

