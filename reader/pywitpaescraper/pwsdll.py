import ctypes
import os
from enum import IntEnum, IntFlag
from pathlib import Path


class PWSDllInitializationError(RuntimeError):
    pass


class RecType(IntEnum):
    SCENARIO = 1
    HEADER = 38
    AIRGROUP = 20
    PILOT = 22
    AIRCRAFT = 32
    TASKFORCE = 70
    SHIPCLASS = 27
    DEVICE = 31
    LOCATION = 19
    SHIP = 8
    MINES = 30
    LEADER = 21


class Side(IntEnum):
    JAPAN = 0
    ALLIED = 1
    BOTHSIDES = 2


class DeviceType(IntEnum):
    ACCANNON = 0
    GAROCKET = 1
    PGM = 2
    GPBOMB = 3
    APBOMB = 4
    DROPTANK = 5
    RADARDETECT = 6
    JAMMER = 7
    NAVRADAR = 8
    ACRADAR = 9
    SURFRADAR = 10
    AAROCKET = 11
    FLAK = 12
    BALLOON = 13
    FACMACH = 14
    ELINT = 15
    TORPEDO = 16
    DPGUN = 17
    NAVYGUN = 18
    ARMYWEAP = 19
    ASW = 20
    MINE = 21
    AFV = 22
    SQUAD = 23
    ENGR = 24
    VEHICLE = 25
    RESOURCE = 26
    ENGINE = 27


class Nationality(IntEnum):
    NONATIONALITY = 0
    IJARMY = 1
    IJNAVY = 2
    DIVIDER = 3
    USNAVY = 4
    USARMY = 5
    USMARINES = 6
    AUSTRALIAN = 7
    NZ = 8
    BRITISH = 9
    FRENCH = 10
    DUTCH = 11
    CHINESE = 12
    SOVIET = 13
    INDIAN = 14
    CW = 15
    PHIL = 16
    COMCHINESE = 17
    CANADIAN = 18


class Fate(IntEnum):
    ACTIVE = 1
    WIA = 2
    MIA = 3
    KIA = 4
    RES = 0
    TRACOM = 30000


class Rank(IntEnum):
    WO = 0
    LT2 = 1
    LT1 = 2
    CPT = 3
    MAJ = 4
    LTC = 5
    COL = 6
    MGEN = 7
    LGEN = 8
    GEN = 9
    PO2 = 10
    PO1 = 11
    CPO = 12
    WOa = 13
    ENS = 14
    LTJG = 15
    LT = 16
    LCDR = 17
    CDR = 18
    CPTa = 19
    RADM = 20
    VADM = 21
    ADM = 22
    ENSa = 23
    LTJGa = 24
    LTa = 25
    LCDRa = 26
    CDRa = 27
    CPTb = 28
    RADMa = 29
    VADMa = 30
    ADMa = 31
    FO = 32
    LT2a = 33
    LT1a = 34
    CPTc = 35
    MAJa = 36
    LTCa = 37
    COLa = 38
    BGEN = 39
    MGENa = 40
    LGENa = 41
    GENa = 42
    WOb = 43
    PO = 44
    FOa = 45
    FLT = 46
    SLDR = 47
    WCDR = 48
    GCPT = 49
    ACOM = 50
    AVM = 51
    AIRMARSHAL = 52
    AIRCMARSHAL = 53


def rank_to_name(rank_value: int) -> str:
    try:
        return Rank(rank_value).name
    except ValueError:
        return f"UNKNOWN({rank_value})"


class ShipClassType(IntEnum):
    CVB = 1
    CV = 2
    CVL = 3
    CVE = 4
    BB = 5
    BC = 6
    CB = 7
    CA = 8
    CL = 9
    CLAA = 10
    CS = 11
    DD = 12
    DE = 13
    TB = 14
    E = 15
    PG = 16
    PF = 17
    KV = 18
    PC = 19
    PB = 20
    SC = 21
    PT = 22
    MTB = 23
    MGB = 24
    ML = 25
    SS = 26
    SST = 27
    SSX = 28
    AMC = 29
    CM = 30
    CMc = 31
    DM = 32
    DMS = 33
    AM = 34
    AS = 35
    AD = 36
    AV = 37
    AVD = 38
    AVP = 39
    AR = 40
    ARD = 41
    AGP = 42
    AG = 43
    AO = 44
    AE = 45
    AGC = 46
    APA = 47
    LSIL = 48
    LSIM = 49
    LSIS = 50
    APD = 51
    AKA = 52
    LSD = 53
    LSV = 54
    AP = 55
    AK = 56
    AKV = 57
    AKE = 58
    AKL = 59
    TK = 60
    LST = 61
    LCI = 62
    LCIG = 63
    LCIM = 64
    LCIR = 65
    LSM = 66
    LSMR = 67
    LCM = 68
    LCT = 69
    LB = 70
    LCVP = 71
    LCSL = 72
    YO = 73
    ACM = 74
    YMS = 75
    YP = 76
    HDML = 77
    APc = 78
    AMc = 79
    xAP = 80
    xAPc = 81
    xAK = 82
    xAKL = 83


def ship_class_type_to_name(class_type_value: int) -> str:
    try:
        return ShipClassType(class_type_value).name
    except ValueError:
        return f"UNKNOWN({class_type_value})"


class AircraftType(IntEnum):
    FI = 0
    FB = 1
    NF = 2
    DB = 3
    LongB = 4
    REC = 5
    MedB = 8
    PBY = 9
    FP = 10
    TBF = 12


def aircraft_type_to_name(aircraft_type_value: int) -> str:
    try:
        return AircraftType(aircraft_type_value).name
    except ValueError:
        return f"UNKNOWN({aircraft_type_value})"


class AircraftAttribFlag(IntFlag):
    HEAVY_BOMBER = 0x01
    MEDIUM_BOMBER = 0x02
    ATTACK_BOMBER = 0x04
    CARRIER_CAPABLE = 0x08
    AMPHIBIAN = 0x10
    LIGHT_BOMBER = 0x20
    FLOAT_PLANE = 0x40
    RESERVED_BIT_7 = 0x80


def decode_aircraft_attrib_flags(attrib_value: int) -> dict[str, bool]:
    value = int(attrib_value) & 0xFF
    return {
        "heavy_bomber": bool(value & AircraftAttribFlag.HEAVY_BOMBER),
        "medium_bomber": bool(value & AircraftAttribFlag.MEDIUM_BOMBER),
        "light_bomber": bool(value & AircraftAttribFlag.LIGHT_BOMBER),
        "carrier_capable": bool(value & AircraftAttribFlag.CARRIER_CAPABLE),
        "amphibian": bool(value & AircraftAttribFlag.AMPHIBIAN),
        "attack_bomber": bool(value & AircraftAttribFlag.ATTACK_BOMBER),
        "float_plane": bool(value & AircraftAttribFlag.FLOAT_PLANE),
        "reserved_bit_7": bool(value & AircraftAttribFlag.RESERVED_BIT_7),
    }


class TaskForceMission(IntEnum):
    AIRCOMBAT = 1
    SURFACE = 2
    BOMBARDMENT = 3
    FASTTRANSPORT = 4
    TRANSPORT = 5
    REPLENISHMENT = 6
    MINELAYING = 7
    SUBPATROL = 8
    SUBMINELAYING = 9
    SUBTRANSPORT = 10
    CARGO = 11
    AIRTRANSPORT = 13
    CVESCORT = 14
    AMPHIB = 15
    ASWCOMBAT = 16
    PTBOAT = 17
    TANKER = 18
    MINESWEEPING = 19
    LANDINGCRAFT = 20
    SUPPORT = 22
    LOCALMINESWEEPING = 23
    ESCORT = 25


class LocationType(IntEnum):
    BEACH = 0
    BASE = 1
    AA = 3
    HQ = 4
    AF = 5
    INF = 7
    ARM = 8
    ARTY = 9
    ENGRS = 10
    CD = 11
    TF = 12


def location_type_to_name(location_type_value: int) -> str:
    try:
        return LocationType(location_type_value).name
    except ValueError:
        return f"UNKNOWN({location_type_value})"


def is_task_force_location_type(location_type_value: int) -> bool:
    return location_type_value == LocationType.TF


def is_base_or_beach_location_type(location_type_value: int) -> bool:
    # AF entries represent fixed base locations in this data model.
    return location_type_value in (LocationType.BASE, LocationType.AF, LocationType.BEACH)


def is_ground_unit_location_type(location_type_value: int) -> bool:
    # Ground-unit categories are all defined location types except BASE, BEACH, and TF.
    if is_base_or_beach_location_type(location_type_value) or is_task_force_location_type(location_type_value):
        return False
    try:
        LocationType(location_type_value)
    except ValueError:
        return False
    return True


def location_record_role(location_type_value: int) -> str:
    """Classify a location record into the dataset role used by this project.

    Roles:
    - "task_force": task force/taskgroup locations
    - "base": base locations (including AF-type base entries)
    - "beach": beach/supply beach locations
    - "ground_unit": all other defined ground-unit location categories
    - "unknown": undefined location type value
    """
    if is_task_force_location_type(location_type_value):
        return "task_force"
    if location_type_value in (LocationType.BASE, LocationType.AF):
        return "base"
    if location_type_value == LocationType.BEACH:
        return "beach"
    if is_ground_unit_location_type(location_type_value):
        return "ground_unit"
    return "unknown"


_HQ_KIND_MAP: dict[int, str] = {
    1: "theater",
    2: "army",
    3: "corp",
    4: "air",
    5: "naval",
    6: "amphib",
}


def decode_hq_kind(hq_type_value: int) -> str | None:
    """Decode the PWSLocation.HQtype ushort to a human-readable HQ kind.

    The game stores the kind as a small integer:
      1 → 'theater'  (e.g. Pacific Fleet, India Command)
      2 → 'army'     (e.g. 1st Australian Army, KNIL Army Command)
      3 → 'corp'     (e.g. I US Amphib, Burma Command, III US Corps)
      4 → 'air'      (e.g. Eleventh USAAF, 221 Group RAF)
      5 → 'naval'    (e.g. Asiatic Fleet, Eastern Fleet)
      6 → 'amphib'   (e.g. III US Amphib Force, V US Amphib Force)
    Returns None for unrecognised values (including 0).
    """
    return _HQ_KIND_MAP.get(hq_type_value)


class PWSPool(ctypes.Structure):
    _fields_ = [
        ("poolJ", ctypes.c_int),
        ("poolA", ctypes.c_int),
    ]


class PWSTaskGroup(ctypes.Structure):
    _fields_ = [
        ("skip", ctypes.c_char * 4),
        ("tfEndurance", ctypes.c_int),
        ("tfEnduranceReq", ctypes.c_int),
        ("skip2", ctypes.c_char * 32),
        ("tfFlagship", ctypes.c_int),
        ("skip3", ctypes.c_char * 6),
        ("tfHomePort", ctypes.c_ushort),
        ("skip4", ctypes.c_char * 292),
        ("skip4a", ctypes.c_char),
        ("tfMission", ctypes.c_char),
        ("skip5", ctypes.c_char * 3),
        ("tfSpeed", ctypes.c_char),
        ("skip6", ctypes.c_char * 202),
    ]


class PWSTaskGroupInfo(ctypes.Structure):
    _fields_ = [
        ("taskgroup", PWSTaskGroup * 4000),
    ]


class PWSScenInfo(ctypes.Structure):
    _fields_ = [
        ("skip",                 ctypes.c_char * 30),
        ("gameturn",             ctypes.c_ushort),
        ("skip2",                ctypes.c_char * 84),
        ("japanVP",              ctypes.c_int),
        ("alliedVP",             ctypes.c_int),
        ("skip3",                ctypes.c_char * 60),
        ("planesBuilt",          PWSPool * 1000),
        ("armamentBuilt",        PWSPool * 2000),
        ("planeTLoss",           ctypes.c_int * 1000),
        ("planeTUsed",           PWSPool * 1000),
        ("armamentUsed",         PWSPool * 2000),
        ("skip4",                ctypes.c_char * 12692),
        ("japanLCULoss",         ctypes.c_int),
        ("alliedLCULoss",        ctypes.c_int),
        ("japanLCUdayLoss",      ctypes.c_int),
        ("alliedLCUdayLoss",     ctypes.c_int),
        ("skip5",                ctypes.c_char),
        ("gametype",             ctypes.c_ubyte),
        ("pbemphase",            ctypes.c_ubyte),
        ("password1",            ctypes.c_char * 9),
        ("password2",            ctypes.c_char * 9),
        ("skip6",                ctypes.c_char * 19),
        ("scenario",             ctypes.c_char * 66),
        ("skip6a",               ctypes.c_char * 134),
        ("pilotpool_skip",       ctypes.c_char * 654),
        ("skip8",                ctypes.c_char * 2),
        ("politicalPointsJapan", ctypes.c_int),
        ("politicalPointsAllied",ctypes.c_int),
        ("scenPolPtsJapan",      ctypes.c_ushort),
        ("scenPolPtsAllied",     ctypes.c_ushort),
        ("all_the_rest",         ctypes.c_char),
    ]


class PWSHeader(ctypes.Structure):
    _fields_ = [
        ("comment", ctypes.c_char * 1000),
        ("timestamp", ctypes.c_char * 800),
    ]


class PWSMinefield(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_ushort),
        ("y", ctypes.c_ushort),
        ("side", ctypes.c_ushort),
        ("skip", ctypes.c_char * 4),
        ("number", ctypes.c_ushort),
        ("skip2", ctypes.c_char * 8),
    ]


class PWSMinefieldInfo(ctypes.Structure):
    _fields_ = [
        ("minefield", PWSMinefield * 6000),
    ]


class PWSLeader(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 25),
        ("rank", ctypes.c_char),
        ("leadership", ctypes.c_char),
        ("inspiration", ctypes.c_char),
        ("naval", ctypes.c_char),
        ("air", ctypes.c_char),
        ("land", ctypes.c_char),
        ("admin", ctypes.c_char),
        ("aggression", ctypes.c_char),
        ("skip", ctypes.c_char * 9),
        ("nation", ctypes.c_char),
        ("skip2", ctypes.c_char),
        ("delay", ctypes.c_int),
        ("polPoints", ctypes.c_char),
        ("type", ctypes.c_char),
        ("skip3", ctypes.c_char * 130),
    ]


class PWSLeaderInfo(ctypes.Structure):
    _fields_ = [
        ("leader", PWSLeader * 50000),
    ]


class PWSShipClass(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 25),
        ("type", ctypes.c_char),
        ("nation", ctypes.c_char),
        ("skip", ctypes.c_char),
        ("tonnage", ctypes.c_int),
        ("fuel", ctypes.c_ushort),
        ("endurance", ctypes.c_ushort),
        ("maxSpd", ctypes.c_char),
        ("cruiseSpd", ctypes.c_char),
        ("manSpeed", ctypes.c_char),
        ("durability", ctypes.c_ubyte),
        ("bitmap", ctypes.c_ushort),
        ("beltArmor", ctypes.c_ushort),
        ("deckArmor", ctypes.c_ushort),
        ("towerArmor", ctypes.c_ushort),
        ("capacity", ctypes.c_ushort),
        ("troopCapacity", ctypes.c_ushort),
        ("cargoCapacity", ctypes.c_ushort),
        ("liquidCapacity", ctypes.c_ushort),
        ("wepID", ctypes.c_ushort * 20),
        ("wepNum", ctypes.c_ushort * 20),
        ("wepFace", ctypes.c_char * 20),
        ("wepAmmo", ctypes.c_ushort * 20),
        ("wepTurret", ctypes.c_char * 20),
        ("wepArmor", ctypes.c_ushort * 20),
        ("upgradeID", ctypes.c_ushort),
        ("availMonth", ctypes.c_char),
        ("availYear", ctypes.c_char),
        ("upgradeShipyardSize", ctypes.c_char),
        ("skip2", ctypes.c_char),
        ("classConvertSet", ctypes.c_ushort),
        ("upgradeDmg", ctypes.c_ushort),
        ("minUpgDelay", ctypes.c_ushort),
        ("minConvDelay", ctypes.c_ushort),
        ("skip3", ctypes.c_char * 22),
        ("specialAttribute", ctypes.c_char),
        ("skip4", ctypes.c_char * 5),
        ("repairPtsPerDmgPt", ctypes.c_ushort),
        ("skip5", ctypes.c_char * 80),
    ]


class PWSShipClassInfo(ctypes.Structure):
    _fields_ = [
        ("shipclass", PWSShipClass * 5000),
    ]


class PWSPilot(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 25),
        ("skip", ctypes.c_char * 7),
        ("agrp", ctypes.c_ushort),
        ("skip2", ctypes.c_char * 4),
        ("kills", ctypes.c_ushort),
        ("missions", ctypes.c_ushort),
        ("skip3", ctypes.c_char),
        ("rank", ctypes.c_char),
        ("exp", ctypes.c_char),
        ("fatigue", ctypes.c_char),
        ("fate", ctypes.c_char),
        ("wound", ctypes.c_char),
        ("delay", ctypes.c_ushort),
        ("skip4", ctypes.c_char * 6),
        ("nationality", ctypes.c_char),
        ("skip5", ctypes.c_char * 8),
        ("air", ctypes.c_char),
        ("navB", ctypes.c_char),
        ("navT", ctypes.c_char),
        ("navS", ctypes.c_char),
        ("recN", ctypes.c_char),
        ("asw", ctypes.c_char),
        ("tran", ctypes.c_char),
        ("grndB", ctypes.c_char),
        ("lowN", ctypes.c_char),
        ("lowG", ctypes.c_char),
        ("staf", ctypes.c_char),
        ("defN", ctypes.c_char),
        ("skip6", ctypes.c_char * 41),
        ("type", ctypes.c_char),
        ("skip7", ctypes.c_char * 61),
    ]


class PWSPilotInfo(ctypes.Structure):
    _fields_ = [
        ("pilot", PWSPilot * 50000),
    ]


class PWSAircraft(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 25),
        ("type", ctypes.c_char),
        ("skip", ctypes.c_char * 2),
        ("maxAlt", ctypes.c_ushort),
        ("maxSpd", ctypes.c_ushort),
        ("cruiseSpd", ctypes.c_ushort),
        ("climbRate", ctypes.c_ushort),
        ("man", ctypes.c_ushort),
        ("endurance", ctypes.c_ushort),
        ("armor", ctypes.c_char),
        ("durability", ctypes.c_char),
        ("wepID", ctypes.c_ushort * 10),
        ("skip2", ctypes.c_char * 20),
        ("wepNum", ctypes.c_ushort * 10),
        ("skip3", ctypes.c_char * 20),
        ("wepFace", ctypes.c_char * 10),
        ("skip4", ctypes.c_char * 50),
        ("maxLoad", ctypes.c_ushort),
        ("availMonth", ctypes.c_char),
        ("availYear", ctypes.c_char),
        ("skip5", ctypes.c_char * 2),
        ("buildRate", ctypes.c_ushort),
        ("bitmap", ctypes.c_ushort),
        ("upgrade", ctypes.c_ushort),
        ("research", ctypes.c_ushort),
        ("dayair", ctypes.c_int),
        ("dayground", ctypes.c_int),
        ("dayflak", ctypes.c_int),
        ("dayops", ctypes.c_int),
        ("totair", ctypes.c_int),
        ("totground", ctypes.c_int),
        ("totflak", ctypes.c_int),
        ("totops", ctypes.c_int),
        ("side", ctypes.c_char),
        ("svcrating", ctypes.c_char),
        ("skip6", ctypes.c_char * 2),
        ("attrib", ctypes.c_char),
        ("skip7", ctypes.c_char * 38),
        ("man10", ctypes.c_char),
        ("man15", ctypes.c_char),
        ("man20", ctypes.c_char),
        ("man31", ctypes.c_char),
        ("man32", ctypes.c_char),
        ("rangeNormal", ctypes.c_char),
        ("skip8", ctypes.c_char * 5),
        ("endMonth", ctypes.c_char),
        ("endYear", ctypes.c_char),
        ("nation", ctypes.c_char),
        ("skip9", ctypes.c_char * 3),
        ("rangeExtended", ctypes.c_char),
        ("skip10", ctypes.c_char * 5),
        ("rangeDTNormal", ctypes.c_char),
        ("skip11", ctypes.c_char * 3),
        ("rangeDTExtended", ctypes.c_char),
        ("skip12", ctypes.c_char * 3),
        ("rangeDTMax", ctypes.c_char),
        ("skip13", ctypes.c_char * 93),
    ]


class PWSAircraftInfo(ctypes.Structure):
    _fields_ = [
        ("aircraft", PWSAircraft * 1000),
    ]


class PWSDevice(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 25),
        ("skip", ctypes.c_char),
        ("type", ctypes.c_ushort),
        ("load", ctypes.c_ushort),
        ("range", ctypes.c_ushort),
        ("eff", ctypes.c_ushort),
        ("pen", ctypes.c_ushort),
        ("acc", ctypes.c_ushort),
        ("skip2", ctypes.c_char * 8),
        ("dud", ctypes.c_ushort),
        ("ceiling", ctypes.c_ushort),
        ("armor", ctypes.c_ushort),
        ("antiarm", ctypes.c_ushort),
        ("antisoft", ctypes.c_ushort),
        ("upgrade", ctypes.c_ushort),
        ("buildrate", ctypes.c_ushort),
        ("availYear", ctypes.c_ushort),
        ("availMonth", ctypes.c_ushort),
        ("skip2a", ctypes.c_char * 4),
        ("side", ctypes.c_char),
        ("skip3", ctypes.c_char * 7),
        ("endYear", ctypes.c_char),
        ("endMonth", ctypes.c_char),
        ("skip4", ctypes.c_char * 158),
    ]


class PWSDeviceInfo(ctypes.Structure):
    _fields_ = [
        ("device", PWSDevice * 2000),
    ]


class PWSAirGroup(ctypes.Structure):
    _fields_ = [
        ("groupname", ctypes.c_char * 26),
        ("skip", ctypes.c_char * 4),
        ("acType", ctypes.c_short),
        ("leaderID", ctypes.c_int),
        ("hqID", ctypes.c_short),
        ("skip2", ctypes.c_char * 2),
        ("baseID", ctypes.c_ushort),
        ("reinforceBaseID", ctypes.c_ushort),
        ("primaryMission", ctypes.c_short),
        ("secondaryMission", ctypes.c_short),
        ("targetID", ctypes.c_short),
        ("skip3", ctypes.c_char * 8),
        ("fragmentNumber", ctypes.c_short),
        ("skip4", ctypes.c_char * 3),
        ("acPercent", ctypes.c_char),
        ("skip5", ctypes.c_char * 120),
        ("pilotMorale", ctypes.c_char),
        ("pilotExp", ctypes.c_char),
        ("skip6", ctypes.c_char * 6),
        ("targetX", ctypes.c_int),
        ("targetY", ctypes.c_int),
        ("skip7", ctypes.c_char * 4),
        ("acReady", ctypes.c_char),
        ("skip8", ctypes.c_char),
        ("acMaintained", ctypes.c_char),
        ("acReserve", ctypes.c_char),
        ("skip9", ctypes.c_char),
        ("acDamaged", ctypes.c_char),
        ("skip10", ctypes.c_char * 2),
        ("acAlt", ctypes.c_short),
        ("skip11", ctypes.c_char * 4),
        ("nation", ctypes.c_char),
        ("skip12", ctypes.c_char),
        ("delay", ctypes.c_int),
        ("delayReinforcement", ctypes.c_char),
        ("skip13", ctypes.c_char * 7),
        ("acKills", ctypes.c_short),
        ("skip14", ctypes.c_char * 2),
        ("pilotsAvail", ctypes.c_short),
        ("skip15", ctypes.c_char * 7),
        ("maxplanes", ctypes.c_char),
        ("skip16", ctypes.c_char * 58),
        ("acRange", ctypes.c_short),
        ("skip17", ctypes.c_char * 2),
        ("upgradeTo", ctypes.c_short),
        ("skip18", ctypes.c_char * 60),
        ("agrUpgrade", ctypes.c_short * 10),
        ("skip19", ctypes.c_char * 2),
        ("withdraw", ctypes.c_int),
        ("delay2", ctypes.c_int),
        ("skip20", ctypes.c_char * 112),
        ("acReinfAvail", ctypes.c_ubyte),
        ("skip21", ctypes.c_char * 33),
        ("pilotsActive", ctypes.c_short),
        ("skip22", ctypes.c_char * 12),
        ("acPctCAP", ctypes.c_char),
        ("acPctLRCAP", ctypes.c_char),
        ("acPctASW", ctypes.c_char),
        ("acPctSearch", ctypes.c_char),
        ("acPctTrain", ctypes.c_char),
        ("acPctRest", ctypes.c_char),
        ("skip23", ctypes.c_char * 62),
        ("acSearchASWStart", ctypes.c_char),
        ("acSearchASWEnd", ctypes.c_char),
        ("acSearchNavStart", ctypes.c_char),
        ("acSearchNavEnd", ctypes.c_char),
        ("skip24", ctypes.c_char * 48),
    ]


class PWSAirGroupInfo(ctypes.Structure):
    _fields_ = [
        ("airgroup", PWSAirGroup * 30000),
    ]


class PWSShip(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 25),
        ("nation", ctypes.c_char),
        ("skip", ctypes.c_char),
        ("shipExpDay", ctypes.c_char),
        ("shipExpNight", ctypes.c_char),
        ("shipStopBuild", ctypes.c_char),
        ("skip2", ctypes.c_char * 2),
        ("shipLeader", ctypes.c_int),
        ("shipDelay", ctypes.c_int),
        ("shipArrivalPort", ctypes.c_ushort),
        ("skip3", ctypes.c_char * 2),
        ("shipWithdrawal", ctypes.c_int),
        ("shipReturn", ctypes.c_int),
        ("shipClass", ctypes.c_ushort),
        ("shipSpeed", ctypes.c_char),
        ("skip4", ctypes.c_char * 3),
        ("shipEndurance", ctypes.c_ushort),
        ("shipBase", ctypes.c_ushort),
        ("shipTF", ctypes.c_ushort),
        ("skip5", ctypes.c_char * 6),
        ("shipWeapon", ctypes.c_ushort * 20),
        ("skip6", ctypes.c_char * 60),
        ("shipWpnAmmo", ctypes.c_ushort * 20),
        ("skip7", ctypes.c_char * 20),
        ("shipWpnArmor", ctypes.c_ushort * 20),
        ("shipWpnDmg", ctypes.c_char * 20),
        ("shipOps", ctypes.c_ushort),
        ("skip8", ctypes.c_char * 8),
        ("shipUnitLoaded", ctypes.c_int),
        ("skip9", ctypes.c_char * 10),
        ("shipSupplyLoaded", ctypes.c_ushort),
        ("shipFuelLoaded", ctypes.c_ushort),
        ("shipResourcesLoaded", ctypes.c_ushort),
        ("shipOilLoaded", ctypes.c_ushort),
        ("skip10", ctypes.c_char * 9),
        ("shipFireDmg", ctypes.c_char),
        ("shipSysDmg", ctypes.c_char),
        ("shipFloatDmg", ctypes.c_char),
        ("shipMajorFloatDmg", ctypes.c_char),
        ("shipEngineDmg", ctypes.c_char),
        ("shipMajorEngineDmg", ctypes.c_char),
        ("shipFOWStatus", ctypes.c_char),
        ("shipRepairPriority", ctypes.c_char),
        ("shipRepairMode", ctypes.c_char),
        ("skip11a", ctypes.c_char),
        ("shipTempAPConv", ctypes.c_char),
        ("shipRepairDelay", ctypes.c_ushort),
        ("shipConversionDelay", ctypes.c_ushort),
        ("skip11", ctypes.c_char * 2),
        ("shipSunkDevice", ctypes.c_ushort),
        ("shipSunkDelay", ctypes.c_ushort),
        ("shipSunkX", ctypes.c_ushort),
        ("shipSunkY", ctypes.c_ushort),
        ("shipSunkBase", ctypes.c_ushort),
        ("shipSunkYear", ctypes.c_char),
        ("shipSunkMonth", ctypes.c_char),
        ("shipSunkDay", ctypes.c_char),
        ("shipBuild", ctypes.c_char),
        ("skip12", ctypes.c_char),
        ("shipScuttled", ctypes.c_char),
        ("skip13", ctypes.c_char),
        ("shipUpgrade", ctypes.c_char),
        ("skip14", ctypes.c_char * 30),
        ("shipFOWDelay", ctypes.c_ushort),
        ("shipFOWShip", ctypes.c_ushort),
        ("skip15", ctypes.c_char * 64),
    ]


class PWSShipInfo(ctypes.Structure):
    _fields_ = [
        ("ship", PWSShip * 20000),
    ]


class PWSLocation(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 25),
        ("skip", ctypes.c_char),
        ("owner", ctypes.c_ushort),
        ("type", ctypes.c_ushort),
        ("symbol", ctypes.c_ushort),
        ("skip2", ctypes.c_char * 4),
        ("X", ctypes.c_ushort),
        ("Y", ctypes.c_ushort),
        ("TOE", ctypes.c_ushort),
        ("arrive", ctypes.c_ushort),
        ("skip3", ctypes.c_char * 8),
        ("indFail", ctypes.c_ushort),
        ("skip3a", ctypes.c_char * 48),
        ("locNear", ctypes.c_ushort),
        ("prepPercent", ctypes.c_ushort),
        ("skip4", ctypes.c_char * 4),
        ("combatMode", ctypes.c_char),
        ("skip5", ctypes.c_char * 7),
        ("HQtype", ctypes.c_ushort),
        ("radius", ctypes.c_ushort),
        ("attachedHQ", ctypes.c_ushort),
        ("skip6", ctypes.c_char * 4),
        ("leaderID", ctypes.c_int),
        ("skip7", ctypes.c_char * 4),
        ("deviceID", ctypes.c_ushort * 20),
        ("deviceNumber", ctypes.c_ushort * 20),
        ("deviceDis", ctypes.c_ushort * 20),
        ("skip8", ctypes.c_short * 40),
        ("deviceTOE", ctypes.c_ushort * 20),
        ("deviceTOENum", ctypes.c_ushort * 20),
        ("airfieldSPS", ctypes.c_int),
        ("portSPS", ctypes.c_ushort),
        ("port", ctypes.c_ushort),
        ("portExpand", ctypes.c_ushort),
        ("airfield", ctypes.c_ushort),
        ("airfieldExpand", ctypes.c_ushort),
        ("fort", ctypes.c_ushort),
        ("fortExpand", ctypes.c_ushort),
        ("skip9", ctypes.c_char * 6),
        ("runwayDmg", ctypes.c_ushort),
        ("portDmg", ctypes.c_ushort),
        ("airfieldDmg", ctypes.c_ushort),
        ("skip10", ctypes.c_ushort * 20),
        ("skip10a", ctypes.c_char * 7),
        ("shipRepair", ctypes.c_int),
        ("skip11", ctypes.c_char * 7),
        ("resources", ctypes.c_int),
        ("resourcesNeeded", ctypes.c_int),
        ("skip12", ctypes.c_char * 4),
        ("oil", ctypes.c_int),
        ("oilNeeded", ctypes.c_int),
        ("fuel", ctypes.c_int),
        ("fuelRequested", ctypes.c_int),
        ("supply", ctypes.c_int),
        ("supplyNeeded", ctypes.c_int),
        ("skip13", ctypes.c_char * 4),
        ("supportReq", ctypes.c_int),
        ("supportTotal", ctypes.c_int),
        ("AVsupportReq", ctypes.c_int),
        ("AVsupportTotal", ctypes.c_int),
        ("delay", ctypes.c_int),
        ("skip14", ctypes.c_char * 8),
        ("suffix", ctypes.c_ushort),
        ("skip15", ctypes.c_ushort),
        ("artillery", ctypes.c_short),
        ("aa", ctypes.c_short),
        ("hasAircraft", ctypes.c_short),
        ("skip16", ctypes.c_ushort),
        ("avSquads", ctypes.c_short),
        ("skip17", ctypes.c_char * 58),
        ("exp", ctypes.c_char),
        ("morale", ctypes.c_char),
        ("fatigue", ctypes.c_char),
        ("marchDir", ctypes.c_char),
        ("marchLen", ctypes.c_char),
        ("skip18", ctypes.c_char * 3),
        ("shipCount", ctypes.c_int),
        ("skip19", ctypes.c_char * 2),
        ("destX", ctypes.c_ushort),
        ("destY", ctypes.c_ushort),
        ("loadedUnit", ctypes.c_ushort),
        ("parentID", ctypes.c_ushort),
        ("fragMbr", ctypes.c_ushort),
        ("detectionLevel", ctypes.c_char),
        ("maxDetectionLevel", ctypes.c_char),
        ("skip20", ctypes.c_char * 108),
        ("japanVP", ctypes.c_ushort),
        ("alliedVP", ctypes.c_ushort),
        ("skip21", ctypes.c_char * 28),
        ("nation", ctypes.c_char),
        ("skip22", ctypes.c_char * 9),
        ("dailySupply", ctypes.c_ushort),
        ("dailyFuel", ctypes.c_ushort),
        ("dailyOil", ctypes.c_ushort),
        ("dailyRes", ctypes.c_ushort),
        ("skip23", ctypes.c_char * 8),
        ("replace", ctypes.c_char),
        ("skip24", ctypes.c_char * 3),
        ("deviceBld", ctypes.c_char * 20),
        ("skip25", ctypes.c_char * 6),
        ("deviceRep", ctypes.c_char * 20),
        ("skip26", ctypes.c_char * 12),
        ("japGarrison", ctypes.c_ushort),
        ("upgradeTOE", ctypes.c_ushort),
        ("operationsMode", ctypes.c_ushort),
        ("withdrawal", ctypes.c_ushort),
        ("skip27", ctypes.c_char * 10),
        ("upgradeTOEdelay", ctypes.c_int),
        ("skip28", ctypes.c_char * 30),
        ("pack", ctypes.c_char),
        ("skip29", ctypes.c_char),
        ("primaryUnit", ctypes.c_ushort),
        ("skip30", ctypes.c_char * 2),
        ("airgroupStack", ctypes.c_ushort),
        ("aircraftStack", ctypes.c_ushort),
        ("attr", ctypes.c_int),
        ("skip31", ctypes.c_char * 2),
        ("airHQTorpMax", ctypes.c_char),
        ("skip32", ctypes.c_char * 3),
        ("airHQTorpCur", ctypes.c_char),
        ("skip33", ctypes.c_char * 3),
        ("alliedGarrison", ctypes.c_ushort),
        ("skip34", ctypes.c_char * 140),
        ("lcuUpgrade", ctypes.c_char),
        ("skip35", ctypes.c_char * 51),
    ]


class PWSLocationInfo(ctypes.Structure):
    _fields_ = [
        ("location", PWSLocation * 18000),
    ]


class PWSAddressUnion(ctypes.Union):
    _fields_ = [
        ("debug", ctypes.c_void_p),
        ("sceninfo", ctypes.c_void_p),
        ("header", ctypes.c_void_p),
        ("airgroups", ctypes.c_void_p),
        ("taskgroups", ctypes.c_void_p),
        ("minefields", ctypes.c_void_p),
        ("leaders", ctypes.c_void_p),
        ("ships", ctypes.c_void_p),
        ("shipclasses", ctypes.c_void_p),
        ("pilots", ctypes.c_void_p),
        ("aircrafts", ctypes.c_void_p),
        ("devices", ctypes.c_void_p),
        ("locations", ctypes.c_void_p),
    ]


class PWSStruct(ctypes.Structure):
    _fields_ = [
        ("PWSopened", ctypes.c_int),
        ("PWSid", ctypes.c_int),
        ("PWSrec", ctypes.c_int),
        ("PWSaddress", PWSAddressUnion),
        ("PWSMessage", ctypes.c_char_p),
    ]


class PWSDll:
    def __init__(self, dll_dir: Path) -> None:
        self.dll_dir = dll_dir
        self._dll_directory_handle = None
        self._pwsdll7 = None
        self._pwsdll = None
        try:
            self._load_dlls()
            self._declare_functions()
        except Exception as exc:
            raise PWSDllInitializationError(
                f"Failed to initialize PWSDll from directory: {self.dll_dir}"
            ) from exc

    def _load_dlls(self) -> None:
        pwsdll7_path = self.dll_dir / "pwsdll7.dll"
        pwsdll_path = self.dll_dir / "pwsdll.dll"

        # local patch (ekko): pwsdll7.dll is optional on this game build (pwsdll.dll imports only
        # KERNEL32.dll, verified with objdump -p), so load it only when present.
        if not pwsdll_path.exists():
            raise FileNotFoundError(f"Missing required primary DLL: {pwsdll_path}")

        if hasattr(os, "add_dll_directory"):
            self._dll_directory_handle = os.add_dll_directory(str(self.dll_dir))

        # Load dependency first (when present) so pwsdll.dll can resolve symbols at call time.
        if pwsdll7_path.exists():
            self._pwsdll7 = ctypes.WinDLL(str(pwsdll7_path))
        self._pwsdll = ctypes.WinDLL(str(pwsdll_path))

    def _declare_functions(self) -> None:
        self.PWSOpenFile = self._pwsdll.PWSOpenFile
        self.PWSGetNextItem = self._pwsdll.PWSGetNextItem
        self.PWSCloseFile = self._pwsdll.PWSCloseFile

        # Signature model from provided C struct details:
        # first parameter is _pws_struct* that the DLL populates.
        self.PWSOpenFile.argtypes = [ctypes.POINTER(PWSStruct), ctypes.c_char_p, ctypes.c_int]
        self.PWSGetNextItem.argtypes = [ctypes.POINTER(PWSStruct)]
        self.PWSCloseFile.argtypes = [ctypes.POINTER(PWSStruct)]

        self.PWSOpenFile.restype = ctypes.c_void_p
        self.PWSGetNextItem.restype = ctypes.c_void_p
        self.PWSCloseFile.restype = ctypes.c_void_p

    def new_context(self, rec_type: RecType = RecType.SCENARIO) -> PWSStruct:
        ctx = PWSStruct()
        ctx.PWSopened = 0
        ctx.PWSid = int(rec_type)
        ctx.PWSrec = 0
        ctx.PWSaddress = PWSAddressUnion()
        ctx.PWSMessage = None
        return ctx

    def pws_open_file(self, ctx: PWSStruct, file_path: str, mode: int) -> int:
        result = self.PWSOpenFile(ctypes.byref(ctx), file_path.encode("ascii"), mode)
        return int(result) if result else 0

    def pws_get_next_item(self, ctx: PWSStruct) -> int:
        result = self.PWSGetNextItem(ctypes.byref(ctx))
        return int(result) if result else 0

    def pws_close_file(self, ctx: PWSStruct) -> int:
        result = self.PWSCloseFile(ctypes.byref(ctx))
        return int(result) if result else 0

    @property
    def raw(self):
        return self._pwsdll