#!/usr/bin/env python3
"""
Cura Profile Extractor v1.3.0
=============================
Extracts ALL Cura settings into a single, searchable JSON file.

Resolves Cura's 8-layer inheritance system:
  fdmprinter.def.json → manufacturer_base → machine-specific → quality → user overrides

Features:
  - Auto-detects Cura install and AppData paths
  - Extracts preferences, machine settings, G-code, quality profiles, materials
  - Tracks source file for every setting
  - Human-readable output with formatted arrays and G-code
  - Quick-reference summary section
  - Key settings extraction for common values
  - GUI (default) or CLI mode
  - Works with any printer manufacturer (Creality, Prusa, Anycubic, etc.)

v1.3.0 Changes:
  - Added: Auto-population of Advanced Fallbacks fields on Validate & Discover
  - Added: Right-click context menus (Cut/Copy/Paste/Select All) on all text fields
  - Added: Help / Instructions button with comprehensive documentation popup
  - Added: Context menu on log pane for easy copying
  - Improved: Log pane label now hints at right-click functionality

v1.2.1 Changes:
  - Added: USER_OVERRIDES section at top of file for power user fallback configuration
  - Added: Collapsible "Advanced Fallbacks" panel in GUI for runtime overrides
  - Added: Linux and macOS path detection support
  - Improved: Documentation for all override options with examples

v1.2.0 Changes:
  - Fixed: Nested G-code values now properly humanized (effective_value, default_value)
  - Fixed: Quality profile discovery now dynamic (derives manufacturer from definition chain)
  - Fixed: G-code fallback uses actual inheritance chain instead of hardcoded list
  - Fixed: Removed hardcoded Creality/Ender references for full portability
  - Added: Manufacturer auto-detection from definition chain
  - Added: More robust machine definition lookup

v1.1.0 Changes:
  - Semicolon-delimited lists now formatted as sorted arrays
  - G-code split into readable line arrays
  - Added _summary section with quick overview
  - Added _key_settings section with important values
  - Added --raw flag to skip formatting

Usage:
  python cura_profile_extractor.py          # GUI mode
  python cura_profile_extractor.py --cli    # CLI mode
  python cura_profile_extractor.py --help   # Help

Author: Brian's 3D Printer Project
License: MIT
"""

import argparse
import configparser
import json
import os
import re
import sys
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote

__version__ = "1.3.0"


# =============================================================================
# USER OVERRIDES — Power User Fallback Configuration
# =============================================================================
#
# If auto-detection fails (Cura update changed paths, non-standard install,
# Linux/Mac, etc.), uncomment and modify these values. They take precedence
# over auto-detection when set to non-None values.
#
# HOW TO USE:
#   1. Find the setting that's failing (check the log output for clues)
#   2. Uncomment the relevant line below (remove the # at the start)
#   3. Replace the example value with your actual path/value
#   4. Save the file and re-run the script
#
# FINDING YOUR PATHS:
#   - Install path: Where Cura.exe lives. Look for a "share/cura/resources" subfolder.
#   - AppData path: Your user settings. Contains "cura.cfg" and folders like 
#     "machine_instances", "quality_changes", etc.
#   - On Windows: Usually %APPDATA%\cura\<version>
#   - On Linux: Usually ~/.local/share/cura/<version> or ~/.config/cura/<version>
#   - On Mac: Usually ~/Library/Application Support/cura/<version>
#
# EXAMPLE (Windows):
#   USER_INSTALL_PATH_OVERRIDE = r"C:\Program Files\UltiMaker Cura 5.11.0"
#   USER_APPDATA_PATH_OVERRIDE = r"C:\Users\YourName\AppData\Roaming\cura\5.11"
#
# EXAMPLE (Linux):
#   USER_INSTALL_PATH_OVERRIDE = "/home/yourname/.local/share/cura/5.11"
#   USER_APPDATA_PATH_OVERRIDE = "/home/yourname/.config/cura/5.11"
#
# -----------------------------------------------------------------------------

# Path to Cura installation directory (contains share/cura/resources)
# Uncomment and set if auto-detection fails to find your Cura install.
#
# USER_INSTALL_PATH_OVERRIDE = r"C:\Program Files\UltiMaker Cura 5.11.0"
USER_INSTALL_PATH_OVERRIDE = None

# Path to Cura user data directory (contains cura.cfg, machine_instances, etc.)
# Uncomment and set if auto-detection fails to find your settings.
#
# USER_APPDATA_PATH_OVERRIDE = r"C:\Users\YourName\AppData\Roaming\cura\5.11"
USER_APPDATA_PATH_OVERRIDE = None

# Override manufacturer detection if it fails or detects wrong manufacturer.
# This affects which quality profile subdirectory is searched.
# Common values: "creality", "prusa", "anycubic", "elegoo", "ultimaker", "voron"
#
# USER_MANUFACTURER_OVERRIDE = "creality"
USER_MANUFACTURER_OVERRIDE = None

# Override the quality profile subdirectory path (relative to resources/quality/).
# Use this if Cura restructures their quality folder layout.
# Example: For Creality printers, qualities are in "quality/creality/base/"
#
# USER_QUALITY_SUBDIR_OVERRIDE = "creality/base"
USER_QUALITY_SUBDIR_OVERRIDE = None

# Override the G-code setting key names if Cura renames them in future versions.
# This is unlikely to change, but here for completeness.
#
# USER_GCODE_START_KEY = "machine_start_gcode"
# USER_GCODE_END_KEY = "machine_end_gcode"
USER_GCODE_START_KEY = None
USER_GCODE_END_KEY = None

# Additional manufacturer prefixes to recognize in definition inheritance chains.
# The script already knows: creality, prusa, anycubic, elegoo, artillery,
# flashforge, lulzbot, ultimaker, makerbot, voron
# Add any others your printer uses here.
#
# USER_ADDITIONAL_MANUFACTURERS = ["biqu", "tronxy", "geeetech"]
USER_ADDITIONAL_MANUFACTURERS = None

# -----------------------------------------------------------------------------
# END USER OVERRIDES
# =============================================================================


# =============================================================================
# HELP TEXT — Shown in Help/Instructions popup
# =============================================================================

HELP_TEXT = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                      CURA PROFILE EXTRACTOR - HELP                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

WHAT THIS TOOL DOES
═══════════════════
Extracts ALL your Cura slicer settings into a single, searchable JSON file.

Cura stores settings across 8+ different files with complex inheritance. This
tool flattens everything into one file, tracking where each setting came from.

Perfect for:
  • Documenting your printer setup
  • Sharing configurations with others
  • Backing up before major changes
  • Debugging slicer issues
  • Comparing profiles


GUI INTERFACE
═════════════

┌─ CURA PATHS ─────────────────────────────────────────────────────────────────┐
│                                                                              │
│  Install Path:   Where Cura is installed (contains Cura.exe)                 │
│                  Example: C:\\Program Files\\UltiMaker Cura 5.11.0           │
│                                                                              │
│  AppData Path:   Your personal Cura settings folder                          │
│                  Example: C:\\Users\\YourName\\AppData\\Roaming\\cura\\5.11  │
│                                                                              │
│  [Validate & Discover] - Checks paths are valid, finds your printers         │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─ MACHINE ────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  Select the printer profile you want to extract. These are the printers      │
│  you've configured in Cura (not necessarily physical printers).              │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─ EXTRACTION OPTIONS ─────────────────────────────────────────────────────────┐
│                                                                              │
│  ☑ Preferences      - Global Cura preferences (visible settings, etc.)       │
│  ☑ Machine Settings - All printer settings with inheritance tracking         │
│  ☑ G-code           - Your Start and End G-code scripts                      │
│  ☑ Built-in Qualities - Standard quality profiles (Draft, Normal, Fine...)   │
│  ☑ Custom Profiles  - Your custom quality profiles                           │
│  ☑ Plugins          - Installed plugins list                                 │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘

┌─ ADVANCED FALLBACKS ─────────────────────────────────────────────────────────┐
│                                                                              │
│  Only use these if auto-detection fails or detects wrong values.             │
│                                                                              │
│  Manufacturer:    Override detected printer brand (creality, prusa, etc.)    │
│  Quality Subdir:  Override quality profile folder path                       │
│                                                                              │
│  Values are auto-populated when you click "Validate & Discover".             │
│  Edit them only if the detected values are wrong.                            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─ BUTTONS ────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  [Dry Run (Preview)] - Shows what would be extracted without saving          │
│  [Extract All!]      - Extracts and saves to a JSON file                     │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘


COMMAND LINE INTERFACE (CLI)
════════════════════════════

Run with --cli flag for terminal/script usage:

  python cura_profile_extractor.py --cli

OPTIONS:
  --cli                 Run in command-line mode (no GUI)
  --install PATH        Cura installation directory
  --appdata PATH        Cura user data directory  
  --machine NAME        Machine/printer name to extract
  --output FILE         Output JSON file path
  --raw                 Skip human-friendly formatting
  
SKIP OPTIONS (exclude specific data):
  --no-preferences      Skip global preferences
  --no-machine          Skip machine settings
  --no-gcode            Skip G-code extraction
  --no-builtin          Skip built-in quality profiles
  --no-custom           Skip custom quality profiles
  --no-plugins          Skip plugins list

EXAMPLES:
  # Auto-detect everything, extract first machine found
  python cura_profile_extractor.py --cli
  
  # Specify machine and output file
  python cura_profile_extractor.py --cli --machine "Ender 3 Pro" -o my_profile.json
  
  # Extract only G-code and machine settings
  python cura_profile_extractor.py --cli --no-preferences --no-builtin --no-custom


TROUBLESHOOTING
═══════════════

"Could not auto-detect Cura install path"
  → Use Browse button to manually select Cura folder
  → Look for folder containing "share/cura/resources" subfolder
  → Or set USER_INSTALL_PATH_OVERRIDE in the script

"Could not auto-detect Cura AppData path"
  → Windows: Check %APPDATA%\\cura\\
  → Linux: Check ~/.config/cura/ or ~/.local/share/cura/
  → Mac: Check ~/Library/Application Support/cura/
  → Or set USER_APPDATA_PATH_OVERRIDE in the script

"No machines found"
  → Make sure you've created at least one printer in Cura
  → Check that the AppData path points to correct Cura version

"Quality profiles not found" or wrong profiles shown
  → Expand "Advanced Fallbacks" section
  → Set correct Manufacturer (e.g., "creality", "prusa")
  → Set Quality Subdir if needed (e.g., "creality/base")

For permanent fixes, edit the USER_OVERRIDES section at the top of the script.


OUTPUT FILE STRUCTURE
═════════════════════

The JSON output contains:

  _summary          Quick overview of extracted data
  _key_settings     Most important settings at a glance
  metadata          Extraction info (version, date, machine)
  preferences       Global Cura preferences
  machine           Full machine config with inheritance chain
  gcode             Start and End G-code (formatted as line arrays)
  extruders         Extruder-specific settings
  quality_builtin   Built-in quality profiles
  quality_custom    Your custom profiles
  plugins           Installed plugins


TIPS
════

• Right-click in text fields for Copy/Paste/Select All
• The Log pane shows detailed progress - check it if something fails
• Use "Dry Run" first to preview before saving
• JSON output is human-readable - open in any text editor
• Settings show their source file for debugging


VERSION: {version}
""".format(version=__version__)


# =============================================================================
# Path Detection
# =============================================================================

def find_cura_install_path() -> Optional[Path]:
    """Auto-detect Cura installation directory."""
    # Check user override first
    if USER_INSTALL_PATH_OVERRIDE:
        override_path = Path(USER_INSTALL_PATH_OVERRIDE)
        if override_path.exists():
            return override_path
        # User set an override but it doesn't exist - warn but continue with auto-detect
        print(f"WARNING: USER_INSTALL_PATH_OVERRIDE set but path not found: {USER_INSTALL_PATH_OVERRIDE}")
    
    search_paths = [
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")),
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", "")),
    ]
    
    # Linux/Mac paths
    home = Path.home()
    if sys.platform == "linux":
        search_paths.extend([
            home / ".local" / "share",
            Path("/usr/share"),
            Path("/opt"),
        ])
    elif sys.platform == "darwin":  # macOS
        search_paths.extend([
            home / "Applications",
            Path("/Applications"),
        ])
    
    candidates = []
    for base in search_paths:
        if not base.exists():
            continue
        # Look for Cura folders (UltiMaker, older Ultimaker, etc.)
        try:
            for item in base.iterdir():
                if item.is_dir() and "cura" in item.name.lower():
                    # Check if it has the expected structure
                    if (item / "share" / "cura" / "resources").exists():
                        # Extract version from folder name
                        match = re.search(r'(\d+\.\d+\.?\d*)', item.name)
                        version = match.group(1) if match else "0.0.0"
                        candidates.append((version, item))
        except PermissionError:
            continue
    
    if not candidates:
        return None
    
    # Return newest version
    candidates.sort(key=lambda x: [int(p) for p in x[0].split('.')[:3]], reverse=True)
    return candidates[0][1]


def find_cura_appdata_path() -> Optional[Path]:
    """Auto-detect Cura AppData directory."""
    # Check user override first
    if USER_APPDATA_PATH_OVERRIDE:
        override_path = Path(USER_APPDATA_PATH_OVERRIDE)
        if override_path.exists():
            return override_path
        print(f"WARNING: USER_APPDATA_PATH_OVERRIDE set but path not found: {USER_APPDATA_PATH_OVERRIDE}")
    
    # Platform-specific base directories
    home = Path.home()
    search_bases = []
    
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", ""))
        if appdata.exists():
            search_bases.append(appdata / "cura")
    elif sys.platform == "linux":
        search_bases.extend([
            home / ".config" / "cura",
            home / ".local" / "share" / "cura",
        ])
    elif sys.platform == "darwin":  # macOS
        search_bases.append(home / "Library" / "Application Support" / "cura")
    
    # Find newest version folder in any of the search bases
    versions = []
    for base in search_bases:
        if not base.exists():
            continue
        for item in base.iterdir():
            if item.is_dir() and re.match(r'^\d+\.\d+', item.name):
                # Verify it looks like a valid Cura config dir
                if (item / "cura.cfg").exists() or (item / "machine_instances").exists():
                    versions.append(item)
    
    if not versions:
        return None
    
    versions.sort(key=lambda x: [int(p) for p in x.name.split('.')[:2]], reverse=True)
    return versions[0]


def get_default_paths() -> Tuple[str, str]:
    """Get default paths with auto-detection."""
    install = find_cura_install_path()
    appdata = find_cura_appdata_path()
    
    # No hardcoded fallbacks - let the user specify if auto-detect fails
    install_str = str(install) if install else ""
    appdata_str = str(appdata) if appdata else ""
    
    return install_str, appdata_str


# =============================================================================
# File Parsers
# =============================================================================

def parse_cfg_file(filepath: Path) -> Dict[str, Any]:
    """Parse Cura .cfg or .inst.cfg file (INI-style format)."""
    result = {
        "_filepath": str(filepath),
        "_filename": filepath.name,
    }
    
    if not filepath.exists():
        result["_error"] = "File not found"
        return result
    
    try:
        # Read with configparser
        config = configparser.ConfigParser(interpolation=None)
        config.read(filepath, encoding='utf-8')
        
        for section in config.sections():
            result[section] = dict(config[section])
        
        return result
    except Exception as e:
        result["_error"] = str(e)
        return result


def parse_def_json(filepath: Path) -> Dict[str, Any]:
    """Parse Cura .def.json definition file."""
    result = {
        "_filepath": str(filepath),
        "_filename": filepath.name,
    }
    
    if not filepath.exists():
        result["_error"] = "File not found"
        return result
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        result.update(data)
        return result
    except Exception as e:
        result["_error"] = str(e)
        return result


def extract_settings_from_def(def_data: Dict[str, Any], prefix: str = "") -> Dict[str, Dict[str, Any]]:
    """
    Recursively extract all settings from a definition file.
    Returns {setting_key: {default_value, type, description, ...}}
    """
    settings = {}
    
    def recurse(node: Dict[str, Any], path: str = ""):
        if "children" in node:
            for key, child in node["children"].items():
                recurse(child, key)
        
        # Extract setting properties
        if "type" in node and node["type"] != "category":
            setting_info = {}
            for prop in ["default_value", "value", "type", "description", "unit", 
                         "minimum_value", "maximum_value", "enabled", "settable_per_mesh",
                         "settable_per_extruder", "options"]:
                if prop in node:
                    setting_info[prop] = node[prop]
            if setting_info:
                settings[path] = setting_info
    
    if "settings" in def_data:
        for category_key, category in def_data["settings"].items():
            recurse(category, category_key)
    
    if "overrides" in def_data:
        for key, override in def_data["overrides"].items():
            if key not in settings:
                settings[key] = {}
            settings[key].update(override)
            settings[key]["_source"] = def_data.get("_filename", "unknown")
    
    return settings


# =============================================================================
# Post-Processing for Human-Readable Output
# =============================================================================

def humanize_output(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-process extracted data for human readability:
    - Split semicolon-delimited strings into arrays
    - Format G-code as readable multiline (including nested values)
    - Clean up nested structures
    """
    
    # Keys that are semicolon-delimited lists
    SEMICOLON_LIST_KEYS = {
        "visible_settings",
        "categories_expanded", 
        "custom_visible_settings",
        "recent_files",
        "expanded_brands",
    }
    
    # Keys that are G-code settings (parent keys)
    GCODE_PARENT_KEYS = {
        "machine_start_gcode",
        "machine_end_gcode",
        "start_gcode",
        "end_gcode",
    }
    
    # Keys that hold G-code values when inside a G-code parent
    GCODE_VALUE_KEYS = {
        "default_value",
        "effective_value",
        "value",
    }
    
    def format_gcode_string(value: str) -> List[str]:
        """Convert G-code string with escaped newlines to line array."""
        if not isinstance(value, str):
            return value
        # Replace literal \n with actual newlines, then split
        cleaned = value.replace("\\n", "\n").replace("\\t", "\t")
        lines = [line for line in cleaned.split("\n")]
        return lines if len(lines) > 1 else value
    
    def process_value(key: str, value: Any, parent_key: Optional[str] = None) -> Any:
        """Process a single value based on its key and parent context."""
        if value is None:
            return value
            
        # Handle semicolon-delimited lists
        if key in SEMICOLON_LIST_KEYS and isinstance(value, str):
            items = [item.strip() for item in value.split(";") if item.strip()]
            return sorted(items) if len(items) > 10 else items
        
        # Handle G-code - both direct keys and nested values
        if isinstance(value, str):
            # Direct G-code key (e.g., "start_gcode": "G28\nG29...")
            if key in GCODE_PARENT_KEYS:
                return format_gcode_string(value)
            # Nested G-code value (e.g., machine_start_gcode: {effective_value: "..."})
            if parent_key in GCODE_PARENT_KEYS and key in GCODE_VALUE_KEYS:
                return format_gcode_string(value)
        
        # Handle comma-separated coordinate lists (e.g., machine_head_with_fans_polygon)
        if key == "machine_head_with_fans_polygon" and isinstance(value, str):
            try:
                import ast
                return ast.literal_eval(value)
            except:
                return value
        
        return value
    
    def process_dict(d: Dict[str, Any], parent_key: Optional[str] = None) -> Dict[str, Any]:
        """Recursively process a dictionary, tracking parent key for context."""
        result = {}
        for key, value in d.items():
            if isinstance(value, dict):
                # Pass current key as parent_key for nested processing
                result[key] = process_dict(value, parent_key=key)
            elif isinstance(value, list):
                result[key] = [
                    process_dict(item, parent_key=key) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = process_value(key, value, parent_key=parent_key)
        return result
    
    return process_dict(data)


def create_summary_section(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a human-friendly summary section at the top of the output."""
    summary = {
        "_note": "This section provides a quick overview. Full details below.",
    }
    
    # Machine info
    if "machine" in data:
        machine = data["machine"]
        summary["machine_name"] = data.get("metadata", {}).get("machine", "Unknown")
        summary["inheritance"] = " → ".join(
            item["name"] for item in machine.get("inheritance_chain", [])
        )
        summary["total_settings"] = len(machine.get("effective_settings", {}))
        
        # Add detected manufacturer
        if machine.get("detected_manufacturer"):
            summary["manufacturer"] = machine["detected_manufacturer"]
    
    # G-code summary
    if "gcode" in data:
        gcode = data["gcode"]
        summary["gcode_source"] = gcode.get("source", "Unknown")
        start = gcode.get("start_gcode", "")
        end = gcode.get("end_gcode", "")
        summary["start_gcode_lines"] = len(start) if isinstance(start, list) else start.count("\n") + 1
        summary["end_gcode_lines"] = len(end) if isinstance(end, list) else end.count("\n") + 1
    
    # Quality profiles
    if "quality_builtin" in data:
        summary["builtin_qualities"] = list(data["quality_builtin"].keys())
    
    if "quality_custom" in data:
        summary["custom_profiles"] = list(data["quality_custom"].keys())
    
    # Plugins
    if "plugins" in data:
        summary["plugins"] = [
            f"{info.get('name', pid)} v{info.get('version', '?')}"
            for pid, info in data["plugins"].items()
            if not pid.startswith("_")
        ]
    
    return summary


def extract_key_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the most commonly-referenced settings into a quick-reference section."""
    key_settings = {}
    
    # Settings most people care about
    IMPORTANT_SETTINGS = [
        # Layer
        "layer_height", "layer_height_0",
        # Walls
        "wall_thickness", "wall_line_count",
        # Top/Bottom
        "top_layers", "bottom_layers", "top_bottom_thickness",
        # Infill
        "infill_sparse_density", "infill_pattern",
        # Speed
        "speed_print", "speed_infill", "speed_wall", "speed_wall_0", "speed_wall_x",
        "speed_topbottom", "speed_travel", "speed_layer_0",
        # Retraction
        "retraction_enable", "retraction_amount", "retraction_speed",
        "retraction_hop_enabled", "retraction_hop",
        # Temperature (from quality/material)
        "material_print_temperature", "material_bed_temperature",
        # Cooling
        "cool_fan_speed", "cool_fan_speed_min", "cool_fan_speed_max",
        # Support
        "support_enable", "support_type", "support_structure",
        # Adhesion
        "adhesion_type", "skirt_line_count", "brim_width",
        # Machine
        "machine_width", "machine_depth", "machine_height",
        "machine_heated_bed", "machine_nozzle_size",
    ]
    
    effective = data.get("machine", {}).get("effective_settings", {})
    def_changes = data.get("machine", {}).get("definition_changes", {}).get("values", {})
    
    for setting in IMPORTANT_SETTINGS:
        if setting in def_changes:
            key_settings[setting] = {
                "value": def_changes[setting],
                "source": "your_customizations"
            }
        elif setting in effective:
            info = effective[setting]
            value = info.get("effective_value") or info.get("value") or info.get("default_value")
            key_settings[setting] = {
                "value": value,
                "source": info.get("_sources", ["unknown"])[-1] if "_sources" in info else "default"
            }
    
    return key_settings


# =============================================================================
# Core Extraction Logic
# =============================================================================

class CuraExtractor:
    """Main extraction engine."""
    
    def __init__(self, install_path: str, appdata_path: str, log_callback=None):
        self.install_path = Path(install_path)
        self.appdata_path = Path(appdata_path)
        self.log = log_callback or print
        
        # Discovered data
        self.machines: List[str] = []
        self.custom_profiles: List[str] = []
        self.materials: List[str] = []
        self.cura_version: str = "unknown"
        
        # Cache for inheritance chains (computed once per machine)
        self._inheritance_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._manufacturer_cache: Dict[str, str] = {}
    
    def validate_paths(self) -> Tuple[bool, List[str]]:
        """Validate that paths exist and contain expected structure."""
        errors = []
        
        # Check install path
        if not self.install_path or not self.install_path.exists():
            errors.append(f"Install path does not exist: {self.install_path}")
            return False, errors
            
        resources = self.install_path / "share" / "cura" / "resources"
        if not resources.exists():
            errors.append(f"Install path missing resources: {resources}")
        
        definitions = resources / "definitions" if resources.exists() else None
        if definitions and not (definitions / "fdmprinter.def.json").exists():
            errors.append("Missing fdmprinter.def.json in definitions")
        
        # Check appdata path
        if not self.appdata_path or not self.appdata_path.exists():
            errors.append(f"AppData path does not exist: {self.appdata_path}")
        
        if self.appdata_path.exists() and not (self.appdata_path / "cura.cfg").exists():
            errors.append("Missing cura.cfg in AppData")
        
        return len(errors) == 0, errors
    
    def _get_inheritance_chain(self, base_def_name: str) -> List[Dict[str, Any]]:
        """
        Build the full inheritance chain for a definition.
        Returns list of {name, file, inherits} dicts from machine → fdmprinter.
        """
        if base_def_name in self._inheritance_cache:
            return self._inheritance_cache[base_def_name]
        
        definitions_dir = self.install_path / "share" / "cura" / "resources" / "definitions"
        chain = []
        current_def = base_def_name
        
        while current_def:
            def_path = definitions_dir / f"{current_def}.def.json"
            if def_path.exists():
                def_data = parse_def_json(def_path)
                chain.append({
                    "name": current_def,
                    "file": str(def_path),
                    "inherits": def_data.get("inherits"),
                })
                current_def = def_data.get("inherits")
            else:
                break
        
        self._inheritance_cache[base_def_name] = chain
        return chain
    
    def _detect_manufacturer(self, inheritance_chain: List[Dict[str, Any]]) -> Optional[str]:
        """
        Detect the manufacturer from the inheritance chain.
        Looks for patterns like 'creality_base', 'prusa_base', 'anycubic_base', etc.
        """
        # Check user override first
        if USER_MANUFACTURER_OVERRIDE:
            return USER_MANUFACTURER_OVERRIDE
        
        # Build list of known manufacturers (built-in + user-defined)
        known_manufacturers = [
            "creality", "prusa", "anycubic", "elegoo", "artillery",
            "flashforge", "lulzbot", "ultimaker", "makerbot", "voron"
        ]
        if USER_ADDITIONAL_MANUFACTURERS:
            known_manufacturers.extend(USER_ADDITIONAL_MANUFACTURERS)
        
        for item in inheritance_chain:
            name = item["name"].lower()
            # Check for manufacturer_base pattern
            if "_base" in name:
                manufacturer = name.split("_base")[0]
                if manufacturer and manufacturer != "fdm":  # Exclude fdmprinter
                    return manufacturer
            # Check for direct manufacturer prefix
            for known in known_manufacturers:
                if name.startswith(known):
                    return known
        return None
    
    def _find_quality_directories(self, manufacturer: Optional[str]) -> List[Path]:
        """
        Find quality profile directories for a manufacturer.
        Returns list of paths to search for built-in qualities.
        """
        quality_base = self.install_path / "share" / "cura" / "resources" / "quality"
        paths = []
        
        # Check user override first
        if USER_QUALITY_SUBDIR_OVERRIDE:
            override_path = quality_base / USER_QUALITY_SUBDIR_OVERRIDE
            if override_path.exists():
                paths.append(override_path)
            else:
                self.log(f"WARNING: USER_QUALITY_SUBDIR_OVERRIDE path not found: {override_path}")
        
        if manufacturer and (quality_base / manufacturer).exists():
            # Manufacturer-specific quality folder
            mfr_dir = quality_base / manufacturer
            if mfr_dir not in paths:
                paths.append(mfr_dir)
            # Check for 'base' subfolder (common pattern)
            if (mfr_dir / "base").exists() and (mfr_dir / "base") not in paths:
                paths.append(mfr_dir / "base")
        
        # Always include generic quality folder as fallback
        if quality_base.exists() and quality_base not in paths:
            paths.append(quality_base)
        
        return paths
    
    def discover(self) -> Dict[str, Any]:
        """Discover available machines, profiles, and materials."""
        result = {
            "machines": [],
            "custom_profiles": [],
            "builtin_qualities": [],
            "materials": [],
            "plugins": [],
        }
        
        # Extract version from path
        match = re.search(r'(\d+\.\d+\.?\d*)', str(self.install_path))
        if match:
            self.cura_version = match.group(1)
        
        # Discover machines from machine_instances
        machine_dir = self.appdata_path / "machine_instances"
        if machine_dir.exists():
            for f in machine_dir.glob("*.global.cfg"):
                # Decode URL-encoded filename
                name = unquote(f.stem.replace(".global", ""))
                result["machines"].append(name)
                self.machines.append(name)
        
        # Discover custom quality profiles
        quality_changes = self.appdata_path / "quality_changes"
        if quality_changes.exists():
            seen = set()
            for f in quality_changes.glob("*.inst.cfg"):
                cfg = parse_cfg_file(f)
                name = cfg.get("general", {}).get("name", f.stem)
                if name not in seen:
                    result["custom_profiles"].append(name)
                    seen.add(name)
            self.custom_profiles = list(seen)
        
        # Discover built-in quality profiles - scan all quality directories
        quality_base = self.install_path / "share" / "cura" / "resources" / "quality"
        if quality_base.exists():
            seen_qualities: Set[str] = set()
            # Walk all subdirectories for .inst.cfg files
            for cfg_file in quality_base.rglob("*global*.inst.cfg"):
                cfg = parse_cfg_file(cfg_file)
                name = cfg.get("general", {}).get("name", cfg_file.stem)
                if name not in seen_qualities:
                    result["builtin_qualities"].append(name)
                    seen_qualities.add(name)
        
        # Discover materials
        materials_dir = self.install_path / "share" / "cura" / "resources" / "materials"
        if materials_dir.exists():
            for f in list(materials_dir.glob("*.xml.fdm_material"))[:20]:  # Limit for performance
                result["materials"].append(f.stem.replace(".xml", ""))
        
        # Discover plugins
        packages_file = self.appdata_path / "packages.json"
        if packages_file.exists():
            try:
                with open(packages_file, 'r', encoding='utf-8') as f:
                    packages = json.load(f)
                for pkg_id, pkg_info in packages.get("installed", {}).items():
                    name = pkg_info.get("package_info", {}).get("display_name", pkg_id)
                    result["plugins"].append(name)
            except:
                pass
        
        return result
    
    def extract_all(self, machine_name: str, options: Dict[str, bool]) -> Dict[str, Any]:
        """
        Extract all requested data for a specific machine.
        
        Options:
            preferences: bool
            machine_settings: bool
            gcode: bool
            quality_builtin: bool
            quality_custom: bool
            materials: bool
            plugins: bool
        """
        output = {
            "metadata": {
                "cura_version": self.cura_version,
                "extracted_at": datetime.now().isoformat(),
                "machine": machine_name,
                "extractor_version": __version__,
            }
        }
        
        self.log(f"Starting extraction for machine: {machine_name}")
        
        # 1. Preferences
        if options.get("preferences", True):
            self.log("  → Extracting preferences...")
            output["preferences"] = self._extract_preferences()
        
        # 2. Machine settings (includes definition chain)
        if options.get("machine_settings", True):
            self.log("  → Extracting machine settings...")
            output["machine"] = self._extract_machine(machine_name)
        
        # 3. G-code (Start/End)
        if options.get("gcode", True):
            self.log("  → Extracting G-code...")
            # Pass inheritance chain for dynamic fallback
            inheritance_chain = output.get("machine", {}).get("inheritance_chain", [])
            output["gcode"] = self._extract_gcode(machine_name, inheritance_chain)
        
        # 4. Extruder settings
        if options.get("machine_settings", True):
            self.log("  → Extracting extruder settings...")
            output["extruders"] = self._extract_extruders(machine_name)
        
        # 5. Built-in quality profiles (use detected manufacturer)
        if options.get("quality_builtin", True):
            self.log("  → Extracting built-in quality profiles...")
            manufacturer = output.get("machine", {}).get("detected_manufacturer")
            output["quality_builtin"] = self._extract_builtin_qualities(manufacturer)
        
        # 6. Custom quality profiles
        if options.get("quality_custom", True):
            self.log("  → Extracting custom quality profiles...")
            output["quality_custom"] = self._extract_custom_qualities()
        
        # 7. Plugins
        if options.get("plugins", True):
            self.log("  → Extracting plugins...")
            output["plugins"] = self._extract_plugins()
        
        # Add summary and key settings sections
        self.log("  → Generating summary...")
        summary = create_summary_section(output)
        key_settings = extract_key_settings(output)
        
        # Reorder to put summary first
        ordered_output = {
            "_summary": summary,
            "_key_settings": key_settings,
        }
        ordered_output.update(output)
        
        self.log("Extraction complete!")
        return ordered_output
    
    def _extract_preferences(self) -> Dict[str, Any]:
        """Extract cura.cfg preferences."""
        cfg_path = self.appdata_path / "cura.cfg"
        return parse_cfg_file(cfg_path)
    
    def _extract_machine(self, machine_name: str) -> Dict[str, Any]:
        """Extract machine configuration with full inheritance chain."""
        result = {
            "inheritance_chain": [],
            "effective_settings": {},
            "definition_changes": {},
            "detected_manufacturer": None,
        }
        
        # Find machine instance file
        machine_dir = self.appdata_path / "machine_instances"
        machine_file = None
        for f in machine_dir.glob("*.global.cfg"):
            name = unquote(f.stem.replace(".global", ""))
            if name == machine_name:
                machine_file = f
                break
        
        if not machine_file:
            result["_error"] = f"Machine not found: {machine_name}"
            return result
        
        # Parse machine instance
        machine_cfg = parse_cfg_file(machine_file)
        result["instance"] = machine_cfg
        
        # Get container stack
        containers = machine_cfg.get("containers", {})
        result["container_stack"] = containers
        
        # Find definition changes (layer 6 - has G-code!)
        settings_name = containers.get("6", "")
        if settings_name:
            def_changes_dir = self.appdata_path / "definition_changes"
            for f in def_changes_dir.glob("*.inst.cfg"):
                cfg = parse_cfg_file(f)
                if cfg.get("general", {}).get("name", "") == settings_name:
                    result["definition_changes"] = cfg
                    break
        
        # Build inheritance chain from the base definition (layer 7)
        base_def_name = containers.get("7", "")
        if not base_def_name:
            # Try to extract from definition field in metadata
            base_def_name = machine_cfg.get("metadata", {}).get("definition", "")
        
        if base_def_name:
            chain = self._get_inheritance_chain(base_def_name)
            result["inheritance_chain"] = chain
            
            # Detect manufacturer from chain
            manufacturer = self._detect_manufacturer(chain)
            result["detected_manufacturer"] = manufacturer
            self._manufacturer_cache[machine_name] = manufacturer
        
        # Extract effective settings from chain (bottom-up)
        effective = {}
        definitions_dir = self.install_path / "share" / "cura" / "resources" / "definitions"
        
        for def_info in reversed(result["inheritance_chain"]):
            def_path = Path(def_info["file"])
            def_data = parse_def_json(def_path)
            
            # Extract settings from this definition
            settings = extract_settings_from_def(def_data)
            for key, value in settings.items():
                if key not in effective:
                    effective[key] = {"_sources": []}
                effective[key].update(value)
                effective[key]["_sources"].append(def_info["name"])
        
        # Apply definition_changes overrides
        if "values" in result.get("definition_changes", {}):
            for key, value in result["definition_changes"]["values"].items():
                if key not in effective:
                    effective[key] = {"_sources": []}
                effective[key]["effective_value"] = value
                effective[key]["_sources"].append("definition_changes")
        
        result["effective_settings"] = effective
        return result
    
    def _extract_gcode(self, machine_name: str, inheritance_chain: List[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Extract Start and End G-code.
        Uses actual inheritance chain for fallback instead of hardcoded list.
        """
        # Use user overrides or defaults for G-code key names
        start_key = USER_GCODE_START_KEY or "machine_start_gcode"
        end_key = USER_GCODE_END_KEY or "machine_end_gcode"
        
        result = {
            "start_gcode": "",
            "end_gcode": "",
            "source": "unknown",
        }
        
        # First check definition_changes (user customizations)
        def_changes_dir = self.appdata_path / "definition_changes"
        for f in def_changes_dir.glob("*_settings.inst.cfg"):
            # Normalize names for comparison (handle URL encoding, spaces, etc.)
            file_name_normalized = f.name.lower().replace("+", "_").replace("%20", "_")
            machine_name_normalized = machine_name.lower().replace(" ", "_")
            
            if machine_name_normalized in file_name_normalized:
                cfg = parse_cfg_file(f)
                values = cfg.get("values", {})
                if start_key in values:
                    result["start_gcode"] = values[start_key]
                    result["source"] = str(f)
                if end_key in values:
                    result["end_gcode"] = values[end_key]
                    if not result["source"] or result["source"] == "unknown":
                        result["source"] = str(f)
                if result["start_gcode"]:
                    break
        
        # If not found, fall back to actual inheritance chain (dynamic, not hardcoded)
        if not result["start_gcode"] and inheritance_chain:
            for def_info in inheritance_chain:
                def_path = Path(def_info["file"])
                if def_path.exists():
                    def_data = parse_def_json(def_path)
                    overrides = def_data.get("overrides", {})
                    
                    if start_key in overrides:
                        gcode_info = overrides[start_key]
                        result["start_gcode"] = gcode_info.get("default_value", "")
                        result["source"] = str(def_path)
                    if end_key in overrides:
                        gcode_info = overrides[end_key]
                        result["end_gcode"] = gcode_info.get("default_value", "")
                    
                    if result["start_gcode"]:
                        break
        
        return result
    
    def _extract_extruders(self, machine_name: str) -> Dict[str, Any]:
        """Extract extruder configurations."""
        result = {}
        
        extruder_dir = self.appdata_path / "extruders"
        if not extruder_dir.exists():
            return result
        
        for f in extruder_dir.glob("*.extruder.cfg"):
            cfg = parse_cfg_file(f)
            metadata = cfg.get("metadata", {})
            
            # Check if this extruder belongs to our machine
            if metadata.get("machine", "") == machine_name or machine_name in str(f):
                position = metadata.get("position", "0")
                result[f"extruder_{position}"] = cfg
                
                # Get extruder settings
                settings_name = cfg.get("containers", {}).get("6", "")
                if settings_name:
                    for sf in (self.appdata_path / "definition_changes").glob("*.inst.cfg"):
                        scfg = parse_cfg_file(sf)
                        if scfg.get("general", {}).get("name", "") == settings_name:
                            result[f"extruder_{position}_settings"] = scfg
                            break
        
        return result
    
    def _extract_builtin_qualities(self, manufacturer: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract built-in quality profiles.
        Uses detected manufacturer to find the right quality directory.
        """
        result = {}
        
        # Get quality directories to search
        quality_dirs = self._find_quality_directories(manufacturer)
        
        for quality_dir in quality_dirs:
            if not quality_dir.exists():
                continue
                
            # Look for global quality profiles
            for f in quality_dir.glob("*global*.inst.cfg"):
                cfg = parse_cfg_file(f)
                name = cfg.get("general", {}).get("name", f.stem)
                quality_type = cfg.get("metadata", {}).get("quality_type", "unknown")
                
                # Avoid duplicates (prefer manufacturer-specific)
                if quality_type not in result:
                    result[quality_type] = {
                        "name": name,
                        "file": str(f),
                        "settings": cfg.get("values", {}),
                    }
        
        return result
    
    def _extract_custom_qualities(self) -> Dict[str, Any]:
        """Extract custom quality profiles from AppData."""
        result = {}
        
        quality_dir = self.appdata_path / "quality_changes"
        if not quality_dir.exists():
            return result
        
        for f in quality_dir.glob("*.inst.cfg"):
            cfg = parse_cfg_file(f)
            name = cfg.get("general", {}).get("name", f.stem)
            
            # Group by profile name (there may be global + per-extruder files)
            if name not in result:
                result[name] = {
                    "files": [],
                    "settings": {},
                }
            
            result[name]["files"].append(str(f))
            
            # Merge settings
            if "values" in cfg:
                result[name]["settings"].update(cfg["values"])
        
        return result
    
    def _extract_plugins(self) -> Dict[str, Any]:
        """Extract installed plugins."""
        result = {}
        
        packages_file = self.appdata_path / "packages.json"
        if not packages_file.exists():
            return result
        
        try:
            with open(packages_file, 'r', encoding='utf-8') as f:
                packages = json.load(f)
            
            for pkg_id, pkg_info in packages.get("installed", {}).items():
                info = pkg_info.get("package_info", {})
                result[pkg_id] = {
                    "name": info.get("display_name", pkg_id),
                    "version": info.get("package_version", "unknown"),
                    "author": info.get("author", {}).get("author_id", "unknown"),
                    "description": info.get("description", ""),
                }
        except Exception as e:
            result["_error"] = str(e)
        
        return result


# =============================================================================
# GUI Interface
# =============================================================================

class CuraExtractorGUI:
    """Tkinter-based graphical interface."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"Cura Profile Extractor v{__version__}")
        self.root.geometry("800x700")
        self.root.minsize(600, 500)
        
        self.extractor: Optional[CuraExtractor] = None
        self._setup_context_menus()
        self._build_ui()
        self._auto_detect_paths()
    
    def _setup_context_menus(self):
        """Create reusable context menus for text widgets."""
        # Context menu for Entry widgets
        self.entry_context_menu = tk.Menu(self.root, tearoff=0)
        self.entry_context_menu.add_command(label="Cut", accelerator="Ctrl+X")
        self.entry_context_menu.add_command(label="Copy", accelerator="Ctrl+C")
        self.entry_context_menu.add_command(label="Paste", accelerator="Ctrl+V")
        self.entry_context_menu.add_separator()
        self.entry_context_menu.add_command(label="Select All", accelerator="Ctrl+A")
        
        # Context menu for Text/ScrolledText widgets (read-friendly)
        self.text_context_menu = tk.Menu(self.root, tearoff=0)
        self.text_context_menu.add_command(label="Copy", accelerator="Ctrl+C")
        self.text_context_menu.add_separator()
        self.text_context_menu.add_command(label="Select All", accelerator="Ctrl+A")
    
    def _bind_entry_context_menu(self, widget):
        """Bind context menu to an Entry widget."""
        def show_menu(event):
            # Update commands to work with this specific widget
            self.entry_context_menu.entryconfigure("Cut", command=lambda: widget.event_generate("<<Cut>>"))
            self.entry_context_menu.entryconfigure("Copy", command=lambda: widget.event_generate("<<Copy>>"))
            self.entry_context_menu.entryconfigure("Paste", command=lambda: widget.event_generate("<<Paste>>"))
            self.entry_context_menu.entryconfigure("Select All", command=lambda: self._select_all_entry(widget))
            self.entry_context_menu.tk_popup(event.x_root, event.y_root)
        widget.bind("<Button-3>", show_menu)
    
    def _bind_text_context_menu(self, widget):
        """Bind context menu to a Text or ScrolledText widget."""
        def show_menu(event):
            self.text_context_menu.entryconfigure("Copy", command=lambda: widget.event_generate("<<Copy>>"))
            self.text_context_menu.entryconfigure("Select All", command=lambda: self._select_all_text(widget))
            self.text_context_menu.tk_popup(event.x_root, event.y_root)
        widget.bind("<Button-3>", show_menu)
    
    def _select_all_entry(self, widget):
        """Select all text in an Entry widget."""
        widget.select_range(0, tk.END)
        widget.icursor(tk.END)
    
    def _select_all_text(self, widget):
        """Select all text in a Text widget."""
        widget.tag_add(tk.SEL, "1.0", tk.END)
        widget.mark_set(tk.INSERT, "1.0")
        widget.see(tk.INSERT)
    
    def _build_ui(self):
        """Construct the user interface."""
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === Path Configuration ===
        path_frame = ttk.LabelFrame(main_frame, text="Cura Paths", padding="5")
        path_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Install path
        ttk.Label(path_frame, text="Install Path:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.install_var = tk.StringVar()
        install_entry = ttk.Entry(path_frame, textvariable=self.install_var, width=60)
        install_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self._bind_entry_context_menu(install_entry)
        ttk.Button(path_frame, text="Browse", command=self._browse_install).grid(row=0, column=2)
        
        # AppData path
        ttk.Label(path_frame, text="AppData Path:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.appdata_var = tk.StringVar()
        appdata_entry = ttk.Entry(path_frame, textvariable=self.appdata_var, width=60)
        appdata_entry.grid(row=1, column=1, sticky=tk.EW, padx=5)
        self._bind_entry_context_menu(appdata_entry)
        ttk.Button(path_frame, text="Browse", command=self._browse_appdata).grid(row=1, column=2)
        
        path_frame.columnconfigure(1, weight=1)
        
        # Validate button
        ttk.Button(path_frame, text="Validate & Discover", command=self._validate_paths).grid(
            row=2, column=0, columnspan=3, pady=10
        )
        
        # === Machine Selection ===
        machine_frame = ttk.LabelFrame(main_frame, text="Machine", padding="5")
        machine_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(machine_frame, text="Select Machine:").pack(side=tk.LEFT)
        self.machine_var = tk.StringVar()
        self.machine_combo = ttk.Combobox(machine_frame, textvariable=self.machine_var, width=40, state="readonly")
        self.machine_combo.pack(side=tk.LEFT, padx=10)
        
        # === Extraction Options ===
        options_frame = ttk.LabelFrame(main_frame, text="Extraction Options", padding="5")
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.opt_preferences = tk.BooleanVar(value=True)
        self.opt_machine = tk.BooleanVar(value=True)
        self.opt_gcode = tk.BooleanVar(value=True)
        self.opt_builtin = tk.BooleanVar(value=True)
        self.opt_custom = tk.BooleanVar(value=True)
        self.opt_plugins = tk.BooleanVar(value=True)
        
        row1 = ttk.Frame(options_frame)
        row1.pack(fill=tk.X)
        ttk.Checkbutton(row1, text="Preferences", variable=self.opt_preferences).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(row1, text="Machine Settings", variable=self.opt_machine).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(row1, text="G-code", variable=self.opt_gcode).pack(side=tk.LEFT, padx=10)
        
        row2 = ttk.Frame(options_frame)
        row2.pack(fill=tk.X)
        ttk.Checkbutton(row2, text="Built-in Qualities", variable=self.opt_builtin).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(row2, text="Custom Profiles", variable=self.opt_custom).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(row2, text="Plugins", variable=self.opt_plugins).pack(side=tk.LEFT, padx=10)
        
        # === Advanced Fallbacks (Collapsible) ===
        self._build_advanced_fallbacks(main_frame)
        
        # === Action Buttons ===
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(button_frame, text="Dry Run (Preview)", command=self._dry_run).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Extract All!", command=self._extract).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Help / Instructions", command=self._show_help).pack(side=tk.RIGHT, padx=5)
        
        # === Log Output ===
        log_frame = ttk.LabelFrame(main_frame, text="Log (right-click to copy)", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self._bind_text_context_menu(self.log_text)
        
        # === Status Bar ===
        self.status_var = tk.StringVar(value="Ready - Configure paths and click 'Validate & Discover'")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(10, 0))
    
    def _log(self, message: str):
        """Append message to log window."""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def _build_advanced_fallbacks(self, parent):
        """Build the collapsible Advanced Fallbacks section."""
        # Variables for fallback entries
        self.fallback_manufacturer = tk.StringVar()
        self.fallback_quality_subdir = tk.StringVar()
        self.advanced_visible = tk.BooleanVar(value=False)
        
        # Container frame
        container = ttk.Frame(parent)
        container.pack(fill=tk.X, pady=(0, 10))
        
        # Toggle button (styled as link)
        self.advanced_toggle = ttk.Button(
            container, 
            text="▶ Advanced Fallbacks (click to expand)", 
            command=self._toggle_advanced,
            style="Link.TButton"
        )
        self.advanced_toggle.pack(anchor=tk.W)
        
        # Try to create a link-style button (may not work on all systems)
        try:
            style = ttk.Style()
            style.configure("Link.TButton", foreground="blue", padding=0)
        except:
            pass
        
        # The collapsible frame (hidden by default)
        self.advanced_frame = ttk.LabelFrame(
            container, 
            text="Fallback Overrides (use if auto-detection fails)", 
            padding="10"
        )
        
        # Help text
        help_text = ttk.Label(
            self.advanced_frame,
            text="These values override auto-detection. Leave blank to use auto-detection.\n"
                 "For permanent changes, edit the USER_OVERRIDES section in the script file.",
            foreground="gray",
            wraplength=500,
            justify=tk.LEFT
        )
        help_text.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
        
        # Manufacturer override
        ttk.Label(self.advanced_frame, text="Manufacturer:").grid(row=1, column=0, sticky=tk.W, pady=2)
        mfr_entry = ttk.Entry(self.advanced_frame, textvariable=self.fallback_manufacturer, width=30)
        mfr_entry.grid(row=1, column=1, sticky=tk.W, padx=5)
        self._bind_entry_context_menu(mfr_entry)
        ttk.Label(
            self.advanced_frame, 
            text="e.g., creality, prusa, anycubic", 
            foreground="gray"
        ).grid(row=1, column=2, sticky=tk.W)
        
        # Quality subdir override
        ttk.Label(self.advanced_frame, text="Quality Subdir:").grid(row=2, column=0, sticky=tk.W, pady=2)
        qual_entry = ttk.Entry(self.advanced_frame, textvariable=self.fallback_quality_subdir, width=30)
        qual_entry.grid(row=2, column=1, sticky=tk.W, padx=5)
        self._bind_entry_context_menu(qual_entry)
        ttk.Label(
            self.advanced_frame, 
            text="e.g., creality/base (relative to resources/quality/)", 
            foreground="gray"
        ).grid(row=2, column=2, sticky=tk.W)
        
        # Apply button
        apply_btn = ttk.Button(
            self.advanced_frame, 
            text="Apply Fallbacks", 
            command=self._apply_fallbacks
        )
        apply_btn.grid(row=3, column=0, columnspan=3, pady=(10, 0), sticky=tk.W)
        
        # Current status
        self.fallback_status = tk.StringVar(value="No fallbacks applied")
        status_label = ttk.Label(
            self.advanced_frame, 
            textvariable=self.fallback_status, 
            foreground="gray"
        )
        status_label.grid(row=4, column=0, columnspan=3, pady=(5, 0), sticky=tk.W)
    
    def _toggle_advanced(self):
        """Toggle visibility of advanced fallbacks section."""
        if self.advanced_visible.get():
            self.advanced_frame.pack_forget()
            self.advanced_toggle.configure(text="▶ Advanced Fallbacks (click to expand)")
            self.advanced_visible.set(False)
        else:
            self.advanced_frame.pack(fill=tk.X, pady=(5, 0))
            self.advanced_toggle.configure(text="▼ Advanced Fallbacks (click to collapse)")
            self.advanced_visible.set(True)
    
    def _apply_fallbacks(self):
        """Apply user-entered fallback values to the global overrides."""
        global USER_MANUFACTURER_OVERRIDE, USER_QUALITY_SUBDIR_OVERRIDE
        
        applied = []
        
        # Apply manufacturer override
        mfr = self.fallback_manufacturer.get().strip()
        if mfr:
            USER_MANUFACTURER_OVERRIDE = mfr
            applied.append(f"manufacturer={mfr}")
            self._log(f"Applied fallback: manufacturer = {mfr}")
        else:
            USER_MANUFACTURER_OVERRIDE = None
        
        # Apply quality subdir override
        qual = self.fallback_quality_subdir.get().strip()
        if qual:
            USER_QUALITY_SUBDIR_OVERRIDE = qual
            applied.append(f"quality_subdir={qual}")
            self._log(f"Applied fallback: quality_subdir = {qual}")
        else:
            USER_QUALITY_SUBDIR_OVERRIDE = None
        
        # Update status
        if applied:
            self.fallback_status.set(f"Applied: {', '.join(applied)}")
            self._log("Fallbacks applied. Re-run Validate & Discover to use new values.")
        else:
            self.fallback_status.set("No fallbacks applied (all fields empty)")
            self._log("Fallbacks cleared.")
    
    def _populate_fallback_fields(self, machine_name: str):
        """
        Auto-populate fallback fields with detected values.
        This shows users what was auto-detected, allowing them to verify or override.
        """
        if not self.extractor:
            return
        
        # We need to do a quick extraction to get the manufacturer
        # Use cached inheritance chain if available
        machine_dir = self.extractor.appdata_path / "machine_instances"
        machine_file = None
        for f in machine_dir.glob("*.global.cfg"):
            name = unquote(f.stem.replace(".global", ""))
            if name == machine_name:
                machine_file = f
                break
        
        if not machine_file:
            return
        
        # Parse to get base definition
        cfg = parse_cfg_file(machine_file)
        containers = cfg.get("containers", {})
        base_def_name = containers.get("7", "")
        
        if base_def_name:
            # Build inheritance chain and detect manufacturer
            chain = self.extractor._get_inheritance_chain(base_def_name)
            manufacturer = self.extractor._detect_manufacturer(chain)
            
            if manufacturer:
                # Only populate if field is empty (don't override user input)
                if not self.fallback_manufacturer.get().strip():
                    self.fallback_manufacturer.set(manufacturer)
                
                # Also set quality subdir if we can find it
                if not self.fallback_quality_subdir.get().strip():
                    quality_base = self.extractor.install_path / "share" / "cura" / "resources" / "quality"
                    if (quality_base / manufacturer / "base").exists():
                        self.fallback_quality_subdir.set(f"{manufacturer}/base")
                    elif (quality_base / manufacturer).exists():
                        self.fallback_quality_subdir.set(manufacturer)
                
                self.fallback_status.set(f"Auto-detected: manufacturer={manufacturer}")
                self._log(f"  Auto-populated fallbacks: manufacturer={manufacturer}")
    
    def _show_help(self):
        """Display the help/instructions dialog."""
        help_window = tk.Toplevel(self.root)
        help_window.title("Cura Profile Extractor - Help & Instructions")
        help_window.geometry("750x600")
        help_window.minsize(600, 400)
        
        # Make it modal-ish (stay on top of main window)
        help_window.transient(self.root)
        
        # Main frame
        frame = ttk.Frame(help_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrolled text widget for help content
        help_text_widget = scrolledtext.ScrolledText(
            frame, 
            wrap=tk.WORD, 
            font=("Consolas", 10),
            padx=10,
            pady=10
        )
        help_text_widget.pack(fill=tk.BOTH, expand=True)
        
        # Insert help text
        help_text_widget.insert(tk.END, HELP_TEXT)
        help_text_widget.config(state=tk.DISABLED)  # Make read-only
        
        # Bind context menu for copying
        self._bind_text_context_menu(help_text_widget)
        
        # Close button
        close_btn = ttk.Button(
            frame, 
            text="Close", 
            command=help_window.destroy
        )
        close_btn.pack(pady=(10, 0))
        
        # Focus the window
        help_window.focus_set()
    
    def _auto_detect_paths(self):
        """Try to auto-detect Cura paths on startup."""
        install_path, appdata_path = get_default_paths()
        
        if install_path:
            self.install_var.set(install_path)
            self._log(f"Auto-detected install: {install_path}")
        else:
            self._log("Could not auto-detect Cura install path")
        
        if appdata_path:
            self.appdata_var.set(appdata_path)
            self._log(f"Auto-detected AppData: {appdata_path}")
        else:
            self._log("Could not auto-detect Cura AppData path")
        
        # Auto-validate if both paths found
        if install_path and appdata_path:
            self._validate_paths()
    
    def _browse_install(self):
        """Browse for Cura installation directory."""
        path = filedialog.askdirectory(title="Select Cura Installation Directory")
        if path:
            self.install_var.set(path)
    
    def _browse_appdata(self):
        """Browse for Cura AppData directory."""
        path = filedialog.askdirectory(title="Select Cura AppData Directory")
        if path:
            self.appdata_var.set(path)
    
    def _validate_paths(self):
        """Validate paths and discover machines."""
        install_path = self.install_var.get()
        appdata_path = self.appdata_var.get()
        
        if not install_path or not appdata_path:
            messagebox.showwarning("Warning", "Please specify both paths")
            return
        
        self._log("\n" + "=" * 50)
        self._log("Validating paths...")
        
        self.extractor = CuraExtractor(install_path, appdata_path, log_callback=self._log)
        
        valid, errors = self.extractor.validate_paths()
        if not valid:
            self._log("Validation FAILED:")
            for err in errors:
                self._log(f"  ✗ {err}")
            self.status_var.set("Validation failed - check paths")
            return
        
        self._log("Validation OK!")
        
        # Discover machines
        self._log("\nDiscovering configurations...")
        discovered = self.extractor.discover()
        
        self._log(f"  Machines found: {len(discovered['machines'])}")
        for m in discovered['machines']:
            self._log(f"    - {m}")
        
        self._log(f"  Custom profiles: {len(discovered['custom_profiles'])}")
        self._log(f"  Built-in qualities: {len(discovered['builtin_qualities'])}")
        self._log(f"  Plugins: {len(discovered['plugins'])}")
        
        # Update machine dropdown
        self.machine_combo['values'] = discovered['machines']
        if discovered['machines']:
            self.machine_combo.current(0)
            
            # Auto-populate fallback fields based on first machine's detected values
            self._populate_fallback_fields(discovered['machines'][0])
        
        self.status_var.set(f"Found {len(discovered['machines'])} machines - Select one and extract!")
    
    def _get_options(self) -> Dict[str, bool]:
        """Get current extraction options."""
        return {
            "preferences": self.opt_preferences.get(),
            "machine_settings": self.opt_machine.get(),
            "gcode": self.opt_gcode.get(),
            "quality_builtin": self.opt_builtin.get(),
            "quality_custom": self.opt_custom.get(),
            "plugins": self.opt_plugins.get(),
        }
    
    def _dry_run(self):
        """Run extraction without saving to preview what will be extracted."""
        if not self.extractor:
            messagebox.showwarning("Warning", "Please validate paths first")
            return
        
        machine = self.machine_var.get()
        if not machine:
            messagebox.showwarning("Warning", "Please select a machine")
            return
        
        self._log("\n" + "=" * 60)
        self._log("DRY RUN - Preview extraction")
        self._log("=" * 60)
        
        options = self._get_options()
        self._log(f"\nOptions selected:")
        for k, v in options.items():
            self._log(f"  {k}: {'Yes' if v else 'No'}")
        
        self._log(f"\nExtracting for machine: {machine}")
        
        try:
            result = self.extractor.extract_all(machine, options)
            
            # Summary
            self._log("\n" + "-" * 40)
            self._log("Extraction Summary:")
            self._log("-" * 40)
            
            if "preferences" in result:
                self._log(f"  Preferences sections: {len(result['preferences']) - 2}")  # minus _filepath, _filename
            
            if "machine" in result:
                chain_len = len(result['machine'].get('inheritance_chain', []))
                settings_count = len(result['machine'].get('effective_settings', {}))
                manufacturer = result['machine'].get('detected_manufacturer', 'unknown')
                self._log(f"  Detected manufacturer: {manufacturer}")
                self._log(f"  Inheritance chain depth: {chain_len}")
                self._log(f"  Effective settings: {settings_count}")
            
            if "gcode" in result:
                start_len = len(result['gcode'].get('start_gcode', ''))
                end_len = len(result['gcode'].get('end_gcode', ''))
                self._log(f"  Start G-code: {start_len} chars")
                self._log(f"  End G-code: {end_len} chars")
            
            if "quality_builtin" in result:
                self._log(f"  Built-in qualities: {len(result['quality_builtin'])}")
            
            if "quality_custom" in result:
                self._log(f"  Custom profiles: {len(result['quality_custom'])}")
            
            if "plugins" in result:
                self._log(f"  Plugins: {len(result['plugins'])}")
            
            self._log("\n✓ Dry run complete. Click 'Extract All!' to save to file.")
            self.status_var.set("Dry run complete")
            
        except Exception as e:
            self._log(f"\nERROR: {e}")
            self.status_var.set("Dry run failed - check log")
    
    def _extract(self):
        """Run full extraction and save to file."""
        if not self.extractor:
            return
        
        machine = self.machine_var.get()
        if not machine:
            messagebox.showwarning("Warning", "Please select a machine")
            return
        
        # Ask for save location
        default_name = f"cura_profile_{machine.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = filedialog.asksaveasfilename(
            title="Save Extracted Profile",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=default_name
        )
        
        if not filepath:
            return
        
        self._log("\n" + "=" * 60)
        self._log("FULL EXTRACTION")
        self._log("=" * 60)
        
        options = self._get_options()
        
        try:
            result = self.extractor.extract_all(machine, options)
            
            # Apply human-friendly formatting
            self._log("  → Formatting for readability...")
            result = humanize_output(result)
            
            # Save to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            self._log(f"\n✓ Profile saved to: {filepath}")
            self._log(f"  File size: {os.path.getsize(filepath):,} bytes")
            
            self.status_var.set(f"Saved: {filepath}")
            
            # Offer to open
            if messagebox.askyesno("Success", f"Profile saved to:\n{filepath}\n\nOpen in default viewer?"):
                os.startfile(filepath)
            
        except Exception as e:
            self._log(f"\nERROR: {e}")
            self.status_var.set("Extraction failed - check log")
            messagebox.showerror("Error", f"Extraction failed:\n{e}")
    
    def run(self):
        """Start the GUI."""
        self.root.mainloop()


# =============================================================================
# CLI Interface
# =============================================================================

def run_cli(args):
    """Run in CLI mode."""
    print(f"Cura Profile Extractor v{__version__}")
    print("=" * 50)
    
    # Get paths
    install_path = args.install or find_cura_install_path()
    appdata_path = args.appdata or find_cura_appdata_path()
    
    if not install_path:
        print("ERROR: Could not detect Cura install path. Use --install to specify.")
        return 1
    if not appdata_path:
        print("ERROR: Could not detect Cura AppData path. Use --appdata to specify.")
        return 1
    
    print(f"Install: {install_path}")
    print(f"AppData: {appdata_path}")
    
    extractor = CuraExtractor(str(install_path), str(appdata_path))
    
    # Validate
    valid, errors = extractor.validate_paths()
    if not valid:
        print("\nValidation errors:")
        for err in errors:
            print(f"  - {err}")
        return 1
    
    # Discover
    print("\nDiscovering configurations...")
    discovered = extractor.discover()
    
    print(f"  Machines: {discovered['machines']}")
    print(f"  Custom profiles: {discovered['custom_profiles']}")
    
    # Select machine
    machine = args.machine
    if not machine:
        if discovered['machines']:
            machine = discovered['machines'][0]
            print(f"\nUsing first machine: {machine}")
        else:
            print("ERROR: No machines found")
            return 1
    
    # Extract
    options = {
        "preferences": not args.no_preferences,
        "machine_settings": not args.no_machine,
        "gcode": not args.no_gcode,
        "quality_builtin": not args.no_builtin,
        "quality_custom": not args.no_custom,
        "plugins": not args.no_plugins,
    }
    
    print(f"\nExtracting for: {machine}")
    result = extractor.extract_all(machine, options)
    
    # Apply human-friendly formatting unless --raw
    if not args.raw:
        print("Formatting for readability...")
        result = humanize_output(result)
    else:
        print("Skipping formatting (--raw mode)")
    
    # Save
    output_file = args.output or f"cura_profile_{machine.replace(' ', '_')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved to: {output_file}")
    print(f"  Size: {os.path.getsize(output_file):,} bytes")
    
    return 0


# =============================================================================
# Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract ALL Cura settings into a single searchable JSON file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Launch GUI (default)
  %(prog)s --cli              # Run in CLI mode with auto-detection
  %(prog)s --cli --machine "MyPrinter" --output my_profile.json
  %(prog)s --cli --list-machines  # Show discovered machines
  
Supports any Cura-compatible printer (Creality, Prusa, Anycubic, etc.)
"""
    )
    
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode instead of GUI")
    parser.add_argument("--install", type=str, help="Cura installation path")
    parser.add_argument("--appdata", type=str, help="Cura AppData path")
    parser.add_argument("--machine", type=str, help="Machine name to extract")
    parser.add_argument("--output", "-o", type=str, help="Output JSON file path")
    parser.add_argument("--no-preferences", action="store_true", help="Skip preferences")
    parser.add_argument("--no-machine", action="store_true", help="Skip machine settings")
    parser.add_argument("--no-gcode", action="store_true", help="Skip G-code")
    parser.add_argument("--no-builtin", action="store_true", help="Skip built-in qualities")
    parser.add_argument("--no-custom", action="store_true", help="Skip custom profiles")
    parser.add_argument("--no-plugins", action="store_true", help="Skip plugins")
    parser.add_argument("--raw", action="store_true", help="Skip human-friendly formatting")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    
    args = parser.parse_args()
    
    if args.cli:
        sys.exit(run_cli(args))
    else:
        app = CuraExtractorGUI()
        app.run()


if __name__ == "__main__":
    main()
