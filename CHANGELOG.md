# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-01-31

### Added

#### Dynamic Settings (Динамические настройки)
- **Runtime Configuration System**: Change bot settings without restart via Telegram interface
- **Configuration Categories**:
  - General: language, log level
  - Notifications: enable/disable notifications
  - Sync: data synchronization interval
  - Violations: abuse detection settings
  - Collector API: Node Agent integration settings
  - Limits: search results, pagination, bulk operations
  - Appearance: UI customization
- **Priority System**: environment variables > database values > default values
- **Type Validation**: supports string, int, float, bool, JSON types
- **Secret Protection**: sensitive values are masked in UI
- **Read-only Settings**: .env variables cannot be overwritten via UI
- New command `/config` for managing settings
- New database table `bot_config` for storing configuration

#### Anti-Abuse System (Violation Detector)
- **Multi-factor Analysis** for detecting account sharing and abuse:

  **Temporal Analyzer**:
  - Detects simultaneous connections from different IPs
  - Device count-aware thresholds (stricter for single-device accounts)
  - Configurable network switch buffer for WiFi/Mobile transitions

  **Geographic Analyzer**:
  - Recognition of 60+ Russian metropolitan areas (agglomerations)
  - "Impossible travel" detection using Haversine distance calculation
  - Travel speed validation:
    - Same city: 50 km/h threshold
    - Domestic travel: 200 km/h
    - International travel: 800 km/h
  - Simultaneous multi-country detection (highest risk)

  **ASN/Provider Analyzer**:
  - Provider type classification with suspicion modifiers:
    - Mobile carriers: ×0.3 (low risk)
    - Mobile ISP: ×0.5
    - Fixed broadband: ×0.8
    - Hosting/Datacenter: ×1.5 (high risk)
    - VPN providers: ×1.8 (very high risk)

  **User Profile Analyzer**:
  - Builds 30-day behavioral baseline from connection history
  - Tracks typical countries, cities, IPs, connection hours
  - Detects anomalies: 2× normal usage = 45 points, >2.5× = critical

  **Device Fingerprint Analyzer**:
  - OS detection from User-Agent (Android, iOS, Windows, macOS, Linux)
  - VPN client detection (V2RayNG, Shadowrocket, Clash, Surge, etc.)
  - Multiple device fingerprint scoring

- **Weighted Scoring System**:
  - Temporal: 25%
  - Geography: 25%
  - ASN: 15%
  - Profile: 20%
  - Device: 15%

- **Action Thresholds**:
  - < 30: No action (normal behavior)
  - 30-50: Monitor
  - 50-65: Warn user
  - 65-80: Soft block (rate limit)
  - 80-90: Temporary block
  - 90+: Hard block + manual review

#### Node Agent Integration
- **Collector API**: `POST /api/v1/connections/batch` endpoint for receiving connection data
- **Agent Token System**:
  - Secure 32-byte hex token generation for node authentication
  - Token management: generate, lookup, set, revoke
  - Unique index for fast token lookups
- **Batch Processing**: efficient handling of connection data batches
- **Automatic Violation Checking**: triggers analysis on each data batch

#### Notifications
- New topic `NOTIFICATIONS_TOPIC_VIOLATIONS` for violation alerts
- Detailed violation reports including:
  - Specific devices and OS detected
  - Countries and cities involved
  - Device fingerprints
  - Recommended action
  - Confidence score

### Changed
- Reduced verbose logging in violation detector (moved to DEBUG level)
- Improved notification formatting for violation events

### Database Migrations
- `20260128_0003_add_node_agent_token.py`: Added `agent_token` column to `nodes` table
- `20260129_0006_add_bot_config_table.py`: Created `bot_config` table for runtime configuration

---

## [1.5.1] - Previous Release

### Fixed
- Minor bug fixes and stability improvements

---

## [1.5.0] - Previous Release

### Added

#### PostgreSQL Integration
- Local data caching to reduce API panel load
- Automatic data synchronization with configurable interval (`SYNC_INTERVAL_SECONDS`)
- Real-time updates through webhook events

#### Data Reading Optimization
- Read operations now use local database:
  - Subscriptions
  - User searches
  - Host lists
  - Node information
  - Panel statistics
  - Configuration profiles
- Node status continues pulling real-time data from the API

#### Diff Notifications
- When data changes through the panel, the bot displays exactly what was modified
- Shows before-and-after values for affected fields

#### Notification Topic Routing
- Route different notification types to different Telegram topics
- Separate topics for: users, nodes, service, HWID, billing, errors
- Fallback to general topic if specific one is not set

#### Graceful Degradation
- System continues functioning through the API if database becomes unavailable
- Full backward compatibility — PostgreSQL is optional

---

## [1.4.0] - Previous Release

### Added
- HWID device management
- Bulk operations for users
- Extended user statistics

---

## [1.3.0] - Previous Release

### Added
- Billing module
- Host management
- API token management

---

## [1.2.0] - Previous Release

### Added
- Node management and monitoring
- Traffic statistics
- Configuration profiles

---

## [1.1.0] - Previous Release

### Added
- User management features
- Search functionality
- Basic statistics

---

## [1.0.0] - Initial Release

### Added
- Basic bot functionality
- Telegram authentication
- API integration with Remnawave panel
- Russian and English localization
