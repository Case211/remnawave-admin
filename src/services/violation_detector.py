"""
IntelligentViolationDetector — re-export из shared/ для обратной совместимости.

Реальная реализация находится в shared/violation_detector.py.
"""
from shared.violation_detector import (  # noqa: F401
    ViolationAction,
    ViolationScore,
    TemporalScore,
    GeoScore,
    ASNScore,
    ProfileScore,
    DeviceScore,
    TemporalAnalyzer,
    GeoAnalyzer,
    ASNAnalyzer,
    UserProfileAnalyzer,
    DeviceFingerprintAnalyzer,
    IntelligentViolationDetector,
)
