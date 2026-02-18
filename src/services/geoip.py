"""Re-export: actual code in shared/geoip.py"""
from shared.geoip import *  # noqa: F401,F403
from shared.geoip import (  # noqa: F401
    IPMetadata,
    GeoIPService,
    get_geoip_service,
)
