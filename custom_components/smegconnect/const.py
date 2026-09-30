"""Constants for the SmegConnect integration."""
from __future__ import annotations

DOMAIN = "smegconnect"
SERVICE_SYNC_CLOCK = "sync_clock"

API_BASE = "https://smegcons.prod-platform.smegconnect.com"
TENANT = "smegcons"

# Config entry keys
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_IOT_USER_CODE = "iot_user_code"

# Device type IDs (from GET /api/v1/devices deviceTypeId field)
DEVICE_TYPE_OVEN = 7
DEVICE_TYPE_BLAST_CHILLER = 12
DEVICE_TYPE_DISHWASHER = 2
DEVICE_TYPE_WINE_CHILLER = 4

DEVICE_TYPE_NAMES = {
    DEVICE_TYPE_OVEN: "Oven",
    DEVICE_TYPE_BLAST_CHILLER: "Blast Chiller",
    DEVICE_TYPE_DISHWASHER: "Dishwasher",
    DEVICE_TYPE_WINE_CHILLER: "Wine Chiller",
}

# CBapplianceCategoryId values (different from deviceTypeId in the device listing).
# These come from the device's own firmware and appear in the status object.
# Confirmed values from live device captures:
#   4  = Oven          (CBapplianceCategoryId in oven status)
#   47 = Blast Chiller (CBapplianceCategoryId in blast chiller status)
#   17 = Dishwasher    (from APK categories.json)
#   34 = Wine Cooler   (from APK categories.json)
APPLIANCE_CATEGORY_NAMES: dict[int, str] = {
    4: "Oven",
    17: "Dishwasher",
    34: "Wine Cooler",
    47: "Blast Chiller",
}

# Internal modelNumber → (commercial_code, display_description) for all 80
# SmegConnect/SmegConnect Plus supported appliances.
#
# Internal modelNumbers sourced directly from the SmegConnect Plus app's
# categories.json asset (extracted from base.apk). Commercial codes and
# product descriptions from smeg.com/smeg-connect/all-products and the
# SmegConnect APK's applCommCode field mappings.
#
# Keys  = internal modelNumber from GET /api/v1/devices (e.g. "0000491139")
# Values = (commercial_code, display_description)
# commercial_code = what "Model" shows in the app's Product/Info tab
#
# To add an unlisted model: provision it, note the CBapplianceModelId from
# the /info status field, read commercial code from the app Product tab,
# look it up in Smeg's catalogue, then add an entry here.
SMEG_MODELS: dict[str, tuple[str, str]] = {

    # -----------------------------------------------------------------------
    # Blast Chillers
    # -----------------------------------------------------------------------
    "0000781592": ("SBC4604WNR",  "Multisense Blast Chiller / 45 cm / Dolce Stil Novo"),   # earlier firmware
    "0000781784": ("SBC4604WNR1", "Multisense Blast Chiller / 45 cm / Dolce Stil Novo"),   # confirmed ✓
    "0000781785": ("SBC4104WG",   "Blast Chiller / 45 cm / Dolce Stil Novo"),
    "0000781786": ("SBC4104WB3",  "Blast Chiller / 45 cm / Dolce Stil Novo"),
    "0000781787": ("SBC4304WX",   "Multisense Blast Chiller / 45 cm / Classica"),

    # -----------------------------------------------------------------------
    # Dishwashers
    # -----------------------------------------------------------------------
    "0000136167": ("STL324BQLLW",  "Fully-integrated Dishwasher / 60 cm"),
    "0000136258": ("STL7324AQLLW", "Fully-integrated Dishwasher / 60 cm"),
    "0000136262": ("STL7324BLW",   "Fully-integrated Dishwasher / 60 cm"),

    # -----------------------------------------------------------------------
    # Galileo Oven series — Dolce Stil Novo
    # SO/SOP prefix: newer Galileo platform (Omnichef, SteamOne, Steam100 Pro, Speedwave)
    # -----------------------------------------------------------------------
    # 60 cm
    "0000491139": ("SOP6606WS2PNR",  "Pyrolytic SteamOne Oven / 60 cm / Dolce Stil Novo"),  # confirmed ✓
    "0000491151": ("SOPA6606WS2PNR", "Pyrolytic SteamOne Oven / 60 cm / Dolce Stil Novo"),
    "0000491087": ("SO6606WAPNR",    "Omnichef Oven / 60 cm / Dolce Stil Novo"),
    "0000491150": ("SOA6606WAPNR",   "Omnichef Oven / 60 cm / Dolce Stil Novo"),
    "0000491138": ("SO6606WS4PNR",   "Steam100 Pro Oven / 60 cm / Dolce Stil Novo"),
    "0000491158": ("SOA6606WS4PNR",  "Steam100 Pro Oven / 60 cm / Dolce Stil Novo"),
    "0000491152": ("SOA6606WM2PNR",  "Speedwave Oven / 60 cm / Dolce Stil Novo"),
    # 45 cm compact
    "0000410008": ("SO4606WAPNR",    "Omnichef Oven / 45 cm compact / Dolce Stil Novo"),    # confirmed ✓
    "0000410009": ("SOA4606WAPNR",   "Omnichef Oven / 45 cm compact / Dolce Stil Novo"),
    "0000440171": ("SO4606WS4PNR",   "Steam100 Pro Oven / 45 cm compact / Dolce Stil Novo"),
    "0000560436": ("SO4606WM2PNR",   "Speedwave Oven / 45 cm compact / Dolce Stil Novo"),
    "0000560432": ("SOA4606WM2PNR",  "Speedwave Oven / 45 cm compact / Dolce Stil Novo"),
    # Linea aesthetic — 60 cm
    "0000491272": ("SO6106WAPG",     "Omnichef Oven / 60 cm / Linea"),
    "0000491273": ("SO6106WAPB3",    "Omnichef Oven / 60 cm / Linea"),
    # Linea aesthetic — 45 cm compact
    "0000410017": ("SO4106WAPG",     "Omnichef Oven / 45 cm compact / Linea"),
    "0000410018": ("SO4106WAPB3",    "Omnichef Oven / 45 cm compact / Linea"),

    # -----------------------------------------------------------------------
    # SFP Pyrolytic + Steam Oven series — Dolce Stil Novo / Linea
    # SFP prefix: pyrolytic + steam (WSP) or thermo-pyrolytic (WTP)
    # -----------------------------------------------------------------------
    # 90 cm
    "0000500142": ("SFPR9606WTPNR",  "Pyrolytic Oven / 90 cm / Dolce Stil Novo"),
    "0000500164": ("SFPRA9606WTPNR", "Pyrolytic Oven / 90 cm / Dolce Stil Novo"),
    "0000500139": ("SFP9305WSPX",    "Pyrolytic Steam Oven / 90 cm / Classica"),
    # 60 cm — Dolce Stil Novo
    "0000490989": ("SFP6606WSPNR",   "Pyrolytic Steam Oven / 60 cm / Dolce Stil Novo"),
    "0000491009": ("SFP6606WSPNX",   "Pyrolytic Steam Oven / 60 cm / Dolce Stil Novo"),
    "0000491001": ("SFP6606WTPNR",   "Pyrolytic Oven / 60 cm / Dolce Stil Novo"),
    "0000491002": ("SFP6606WTPNX",   "Pyrolytic Oven / 60 cm / Dolce Stil Novo"),
    # 60 cm — Classica
    "0000491036": ("SFP6303WTPX",    "Pyrolytic Oven / 60 cm / Classica"),
    # 45 cm compact — Dolce Stil Novo
    "0000491042": ("SFP6604WSPNR",   "Pyrolytic Steam Oven / 45 cm compact / Dolce Stil Novo"),
    "0000491043": ("SFP6604WSPNX",   "Pyrolytic Steam Oven / 45 cm compact / Dolce Stil Novo"),
    "0000491044": ("SFP6604WTPNR",   "Pyrolytic Oven / 45 cm compact / Dolce Stil Novo"),
    "0000491045": ("SFP6604WTPNX",   "Pyrolytic Oven / 45 cm compact / Dolce Stil Novo"),
    "0000451339": ("SFP6104WTPB",    "Pyrolytic Oven / 45 cm compact / Dolce Stil Novo"),
    "0000451340": ("SFP6104WTPN",    "Pyrolytic Oven / 45 cm compact / Dolce Stil Novo"),
    # 45 cm compact — Linea
    "0000491034": ("SFP6106WSPS",    "Pyrolytic Steam Oven / 45 cm compact / Linea"),
    "0000491003": ("SFP6106WTPS",    "Pyrolytic Oven / 45 cm compact / Linea"),
    "0000491040": ("SFP6104WTPS",    "Pyrolytic Oven / 45 cm compact / Linea"),

    # -----------------------------------------------------------------------
    # SF Pyrolytic Oven series — 45 cm compact
    # SF4 prefix: WVCP = ventilated pyrolytic, WMC = multifunction combi
    # -----------------------------------------------------------------------
    # Dolce Stil Novo
    "0000440148": ("SF4606WVCPNR",  "Pyrolytic Oven / 45 cm compact / Dolce Stil Novo"),
    "0000440144": ("SF4606WVCPNX",  "Pyrolytic Oven / 45 cm compact / Dolce Stil Novo"),
    "0000440160": ("SF4604WVCPNR",  "Pyrolytic Oven / 45 cm compact / Dolce Stil Novo"),
    "0000440161": ("SF4604WVCPNX",  "Pyrolytic Oven / 45 cm compact / Dolce Stil Novo"),
    "0000560339": ("SF4606WMCNR",   "Multifunction Oven / 45 cm compact / Dolce Stil Novo"),
    "0000560356": ("SF4606WMCNX",   "Multifunction Oven / 45 cm compact / Dolce Stil Novo"),
    "0000560377": ("SF4604WMCNR",   "Multifunction Oven / 45 cm compact / Dolce Stil Novo"),
    "0000560378": ("SF4604WMCNX",   "Multifunction Oven / 45 cm compact / Dolce Stil Novo"),
    "0000560418": ("SF4604WMCNRK",  "Multifunction Oven / 45 cm compact / Dolce Stil Novo"),
    # Linea
    "0000440147": ("SF4106WVCPS",   "Pyrolytic Oven / 45 cm compact / Linea"),
    "0000440157": ("SF4104WVCPS",   "Pyrolytic Oven / 45 cm compact / Linea"),
    "0000440158": ("SF4104WVCPN",   "Pyrolytic Oven / 45 cm compact / Linea"),
    "0000560350": ("SF4106WMCS",    "Multifunction Oven / 45 cm compact / Linea"),
    "0000560374": ("SF4104WMCN",    "Multifunction Oven / 45 cm compact / Linea"),
    "0000560375": ("SF4104WMCS",    "Multifunction Oven / 45 cm compact / Linea"),
    # Classica
    "0000440159": ("SF4303WVCPX",   "Pyrolytic Oven / 45 cm compact / Classica"),
    "0000560376": ("SF4303WMCX",    "Multifunction Oven / 45 cm compact / Classica"),

    # -----------------------------------------------------------------------
    # Wine Coolers (CVI series) — built-in
    # -----------------------------------------------------------------------
    # Dolce Stil Novo — 82 cm tall (38 bottles)
    "0000752711": ("CVI638LWN3",  "Built-in Wine Cooler / 82 cm / Dolce Stil Novo"),
    "0000752712": ("CVI638RWN3",  "Built-in Wine Cooler / 82 cm / Dolce Stil Novo"),
    "0000752306": ("CVI638LWN2",  "Built-in Wine Cooler / 82 cm / Dolce Stil Novo"),
    "0000752307": ("CVI638RWN2",  "Built-in Wine Cooler / 82 cm / Dolce Stil Novo"),
    # Dolce Stil Novo — 45 cm compact (21 bottles)
    "0000752707": ("CVI621LWNR3", "Built-in Wine Cooler / 45 cm compact / Dolce Stil Novo"),
    "0000752708": ("CVI621LWNX3", "Built-in Wine Cooler / 45 cm compact / Dolce Stil Novo"),
    "0000752709": ("CVI621RWNR3", "Built-in Wine Cooler / 45 cm compact / Dolce Stil Novo"),
    "0000752710": ("CVI621RWNX3", "Built-in Wine Cooler / 45 cm compact / Dolce Stil Novo"),
    # Dolce Stil Novo — standard height (18 bottles)
    "0000752302": ("CVI618LWNX2", "Built-in Wine Cooler / 60 cm / Dolce Stil Novo"),
    "0000752303": ("CVI618RWNX2", "Built-in Wine Cooler / 60 cm / Dolce Stil Novo"),
    "0000752304": ("CVI618LWNR2", "Built-in Wine Cooler / 60 cm / Dolce Stil Novo"),
    "0000752305": ("CVI618RWNR2", "Built-in Wine Cooler / 60 cm / Dolce Stil Novo"),
    # Classica — 45 cm (38 bottles)
    "0000752308": ("CVI338LWX2",  "Built-in Wine Cooler / 45 cm compact / Classica"),
    "0000752309": ("CVI338RWX2",  "Built-in Wine Cooler / 45 cm compact / Classica"),
    # Linea — compact
    "0000752388": ("CVI138LWS2",  "Built-in Wine Cooler / compact / Linea"),
    "0000752389": ("CVI138RWS2",  "Built-in Wine Cooler / compact / Linea"),
    "0000752286": ("CVI118RWS2",  "Built-in Wine Cooler / compact / Linea"),
    "0000752287": ("CVI118LWS2",  "Built-in Wine Cooler / compact / Linea"),
    # Dolce Stil Novo — compact
    "0000752290": ("CVI118RWN2",  "Built-in Wine Cooler / compact / Dolce Stil Novo"),
    "0000752291": ("CVI118LWN2",  "Built-in Wine Cooler / compact / Dolce Stil Novo"),
    # Classica — standard
    "0000752258": ("CVI318RWX2",  "Built-in Wine Cooler / 45 cm / Classica"),
    "0000752259": ("CVI318LWX2",  "Built-in Wine Cooler / 45 cm / Classica"),
}

def decode_fw_version(value: object) -> str | None:
    """Decode a firmware version field to a human-readable 'major.minor.patch' string.

    Oven firmware fields are 24-bit little-endian integers:
      e.g. dispBoardFwRel=2564 (0x000A04) → major=4, minor=10, patch=0 → '4.10.0'

    Blast chiller firmware fields are 4-char base64 strings encoding 3 bytes:
      e.g. dispBoardFwRel='ATEA' → bytes [1, 49, 0] → '1.49.0'

    Confirmed mappings (from Product tab in SmegConnect/Plus app):
      pwrBoardFwRel    → SOFTW Ver.
      dispBoardFwRel   → FIRMW Ver.
      dispBoardParFwRel → SCHTX Ver.
      pwrBoardParFwRel  → PARSW Ver.
    """
    import base64 as _b64
    if value is None:
        return None
    if isinstance(value, str):
        try:
            raw = _b64.b64decode(value)
            if len(raw) >= 3:
                ver = f"{raw[0]}.{raw[1]}.{raw[2]}"
                # "0.0.0" = firmware sentinel for absent hardware board
                return None if ver == "0.0.0" else ver
        except Exception:
            pass
        return str(value) if value else None
    # Integer: 24-bit little-endian major.minor.patch
    n = int(value)
    if n == 0:
        # 0 = board not present (e.g. auxBoardFwRel on ovens without a 4G module)
        return None
    ver = f"{n & 0xFF}.{(n >> 8) & 0xFF}.{(n >> 16) & 0xFF}"
    return None if ver == "0.0.0" else ver


def smeg_device_name(model_number: str) -> str:
    """Return the HA device display name for a given API modelNumber.

    Format: 'Smeg {description} ({commercial_code})'
    e.g.   'Smeg Pyrolytic SteamOne Oven / 60 cm / Dolce Stil Novo (SOP6606WS2PNR)'

    Falls back to 'Smeg {model_number}' for unknown models.
    """
    entry = SMEG_MODELS.get(model_number)
    if entry:
        _commercial_code, description = entry
        # HA already shows the model field as a gray subtitle in device lists —
        # no need to repeat the model code in the name.
        return f"Smeg {description}"
    # Unknown model — use the raw model number so it's still unique
    return f"Smeg {model_number}" if model_number else "Smeg Appliance"

# Command version per device type ("4.0" confirmed for oven + blast chiller from Charles captures)
DEVICE_TYPE_COMMAND_VERSION: dict[int, str] = {
    DEVICE_TYPE_OVEN: "4.0",
    DEVICE_TYPE_BLAST_CHILLER: "4.0",
    DEVICE_TYPE_DISHWASHER: "3.0",
    DEVICE_TYPE_WINE_CHILLER: "3.0",
}

# Oven command codes (confirmed from Charles captures + live device query capture)
# Power: applFeature confirmed from oven availableCommands list and APK bundle.
# Sys_OpSetPowerOnFeature is NOT in oven availableCommands — using it was wrong.
CMD_APPL = "applFeature"                   # oven on/off; param: appl, values: "ON"/"OFF"
CMD_SET_TEMP = "currStepTargetTempSetFeature"  # set temperature; param: currStepTargetTempSet
CMD_LIGHT = "lightFeature"                 # confirmed from Charles captures
CMD_KEEP_WARM = "keepWarmFeature"
CMD_ECO_LIGHT = "ecoLightFeature"
CMD_ECO_LOGIC = "ecoLogicFeature"
CMD_CHILDLOCK = "childlockFeature"
CMD_SOUND = "soundActivFeature"
CMD_DIGITAL_CLOCK = "digClockFeature"
CMD_TIMER1 = "timer1Feature"
CMD_TIMER2 = "timer2Feature"
CMD_TIMER3 = "timer3Feature"
CMD_DISP_BRIGHTNESS = "dispBrightnessFeature"
CMD_WATER_HARDNESS = "waterHardnessFeature"

# Shared oven + blast chiller settings commands (no RemCmd variant for these)
CMD_TEMP_FORMAT = "tempFormatFeature"      # param: tempFormat; oven="°C"/"°F", chiller="0"/"1"
CMD_HOUR_FORMAT = "hourFormatFeature"      # param: hourFormat; oven="24h"/"12h", chiller="0"/"1"
CMD_WEIGHT_FORMAT = "weightFormatFeature"  # param: weightFormat; oven="kg"/"oz", chiller="0"/"1"
CMD_MANUAL_CLOCK = "manualClockFeature"

# Blast chiller command codes (confirmed from SmegConnect Plus live capture)
CMD_CHILLER_APPL = "applRemCmdFeature"     # blast chiller on/off; param: applRemCmd, "1"/"0"
CMD_SEQ_START = "currSeqStartCmd"
CMD_SEQ_STOP = "currSeqStopCmd"
CMD_STEP1_TEMP = "stepOneTargetTempSetFeature"   # confirmed
CMD_STEP2_TEMP = "stepTwoTargetTempSetFeature"
CMD_STEP3_TEMP = "stepThreeTargetTempSetFeature"
CMD_CHILLER_CHILDLOCK = "childlockRemCmdFeature"
CMD_CHILLER_SOUND = "soundActivRemCmdFeature"
CMD_CHILLER_DIGITAL_CLOCK = "digClockRemCmdFeature"   # confirmed param: digClockRemCmd

# Blast chiller bit-field → named field mapping.
# Source: BlastChillerStatusTransformer.java in SmegConnect Plus APK (ADF 0526), confirmed
# 2026-08-20 by direct decompilation of smegconnectplus/base.apk res/raw/adf_0526_json.json
# and BlastChillerStatusTransformer.java.
# The transformer renames raw API bit fields to logical named fields on the client side.
# doorState is NOT in this map — the SBC4604WNR1 firmware does not expose door state.
BLAST_CHILLER_BIT_MAP: dict[str, str] = {
    "applState1_000": "applRemCmd",       # 1 = appliance on, 0 = off
    "applState1_002": "doorRemCmd",       # 1 = door open, 0 = door closed
    "applState2_001": "childlockRemCmd",  # 1 = locked, 0 = unlocked
    "applState2_003": "showroomRemCmd",   # 1 = showroom on, 0 = off
    "applState2_007": "soundActivRemCmd", # 1 = sound on, 0 = off
    "applState2_013": "digClockRemCmd",   # 1 = digital clock on, 0 = off
}

# Blast chiller alarm bit map.
# Source: extractBlastChillerAlarms() / isAlarmActive() in BlastChillerStatusKt.java.
# Each entry is (alarm_register_prefix, bit_index, human_readable_label).
# An alarm is active when BOTH alarmStatus_{bit} AND alarmStatus_{bit+1} equal 1
# (mirrors the two-field AND check in isAlarmActive). Checking only one field
# produces false positives because the firmware sets individual bits to 1 in
# normal operation.
BLAST_CHILLER_ALARM_MAP: list[tuple[str, int, str]] = [
    ("alarmStatus",  0,  "Probe fault"),
    ("alarmStatus",  4,  "Compressor fault"),
    ("alarmStatus",  6,  "Cell resistance fault"),
    ("alarmStatus",  8,  "Evaporator fan fault"),
    ("alarmStatus",  26, "Power and connectivity board fault"),
    ("alarmStatus",  28, "Power and meat probe board fault"),
    ("alarmStatus",  30, "Power and display board fault"),
    ("alarmStatus2", 10, "Display and touch fault"),
]

# Error strings from Smeg S3 labels CDN (smeg-connect-config-app-prod.s3.eu-central-1.amazonaws.com)
# Maps failureCode integer → human-readable description for oven errors.
# Codes 1-9 = Err1-Err9, 10 = Err10, 0xA-0xF = ErrA-ErrF (1-indexed hex digits).
OVEN_ERROR_LABELS: dict[int, str] = {
    1: "Error 1. Please contact Customer Support",
    2: "Error 2. Please contact Customer Support",
    3: "Error 3. Please contact Customer Support",
    4: "Error 4. Please contact Customer Support",
    5: "Error 5. Please contact Customer Support",
    6: "Error 6. Please contact Customer Support",
    7: "Error 7. Please contact Customer Support",
    8: "Error 8. Please contact Customer Support",
    9: "Error 9. Please contact Customer Support",
    10: "Error 10. Please contact Customer Support",
    11: "Error 11. Please contact Customer Support",
    12: "Error 12. Please contact Customer Support",
    13: "Error 13. Please contact Customer Support",
    14: "Error 14. Please contact Customer Support",
    15: "Error 15. Please contact Customer Support",
    16: "Error 16. Please contact Customer Support",
    17: "Error 17. Please contact Customer Support",
    0xA: "Error A. Please contact Customer Support",
    0xB: "Error B. Please contact Customer Support",
    0xC: "Error C. Please contact Customer Support",
    0xD: "Error D. Please contact Customer Support",
    0xE: "Error E. Please contact Customer Support",
    0xF: "Error F. Please contact Customer Support",
}

BLAST_CHILLER_ERROR_LABELS: dict[int, str] = {
    1: "Error 1. Please contact Customer Support",
    3: "Error 3. Please contact Customer Support",
    4: "Error 4. Please contact Customer Support",
    5: "Error 5. Please contact Customer Support",
    10: "Error 10. Please contact Customer Support",
    0xF: "Error F. Please contact Customer Support",
}

# failureLabel sentinel returned by the API when there is no active error
FAILURE_LABEL_NONE = "notification.none"

# Standard request headers (sent on every authenticated call)
STANDARD_HEADERS = {
    "x-tenant": TENANT,
    "Content-Type": "application/json;charset=UTF-8",
    "accept-hlsschema": "3.0",
    "Cache-Control": "no-cache",
}

# Oven temperature limits (°C)
OVEN_MIN_TEMP = 30
OVEN_MAX_TEMP = 280
OVEN_TEMP_STEP = 5

# Platforms to set up per config entry
PLATFORMS = ["sensor", "binary_sensor", "switch", "climate", "number", "select"]
