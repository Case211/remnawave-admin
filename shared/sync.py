"""
Sync service for synchronizing data between API and local PostgreSQL database.
Handles periodic sync, webhook events, and on-demand sync.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from shared.config import get_shared_settings as get_settings
from shared.api_client import api_client
from shared.database import db_service
from shared.logger import logger


class SyncService:
    """
    Service for synchronizing data from Remnawave API to local PostgreSQL database.
    
    Features:
    - Periodic full sync (configurable interval)
    - Webhook event handling for real-time updates
    - On-demand sync for specific entities
    - Graceful degradation when DB is unavailable
    """
    
    def __init__(self):
        self._running: bool = False
        self._sync_task: Optional[asyncio.Task] = None
        self._initial_sync_done: bool = False
    
    @property
    def is_running(self) -> bool:
        """Check if sync service is running."""
        return self._running
    
    @property
    def initial_sync_done(self) -> bool:
        """Check if initial sync has been completed."""
        return self._initial_sync_done
    
    async def start(self) -> None:
        """Start the sync service with periodic sync loop."""
        if self._running:
            logger.warning("Sync service is already running")
            return
        
        settings = get_settings()
        
        if not settings.database_enabled:
            logger.info("Database not configured, sync service disabled")
            return
        
        if not db_service.is_connected:
            logger.warning("Database not connected, sync service cannot start")
            return
        
        self._running = True
        logger.info("🔄 Sync service started (interval: %ds)", settings.sync_interval_seconds)
        
        # Run initial sync
        await self._run_initial_sync()
        
        # Start periodic sync loop
        self._sync_task = asyncio.create_task(self._periodic_sync_loop())
    
    async def stop(self) -> None:
        """Stop the sync service."""
        if not self._running:
            return
        
        self._running = False
        
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None
        
        logger.info("Sync service stopped")
    
    async def _run_initial_sync(self) -> None:
        """Run initial synchronization of all data."""
        logger.info("🔄 Running initial sync...")

        try:
            results = await asyncio.gather(
                self.sync_users(),
                self.sync_nodes(),
                self.sync_hosts(),
                self.sync_config_profiles(),
                self.sync_all_hwid_devices(),
                return_exceptions=True
            )

            sync_names = ["users", "nodes", "hosts", "config_profiles", "hwid_devices"]
            summary = []
            for name, result in zip(sync_names, results):
                if isinstance(result, Exception):
                    logger.error("Sync %s failed: %s", name, result)
                else:
                    summary.append(f"{name}={result}")

            self._initial_sync_done = True
            logger.info("✅ Initial sync done: %s", ", ".join(summary))
            
        except Exception as e:
            logger.error("❌ Initial sync failed: %s", e)
    
    async def _periodic_sync_loop(self) -> None:
        """Periodic sync loop."""
        settings = get_settings()
        interval = settings.sync_interval_seconds
        
        while self._running:
            try:
                await asyncio.sleep(interval)
                
                if not self._running:
                    break
                
                logger.debug("Running periodic sync...")
                await self.full_sync()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in periodic sync: %s", e)
                # Continue running, will retry next interval
    
    async def full_sync(self) -> Dict[str, int]:
        """
        Perform full synchronization of all data.
        Returns dict with counts of synced records.
        """
        results = {}
        
        try:
            # Sync users
            results["users"] = await self.sync_users()
        except Exception as e:
            logger.error("Failed to sync users: %s", e)
            results["users"] = -1
        
        try:
            # Sync nodes
            results["nodes"] = await self.sync_nodes()
        except Exception as e:
            logger.error("Failed to sync nodes: %s", e)
            results["nodes"] = -1
        
        try:
            # Sync hosts
            results["hosts"] = await self.sync_hosts()
        except Exception as e:
            logger.error("Failed to sync hosts: %s", e)
            results["hosts"] = -1
        
        try:
            # Sync config profiles
            results["config_profiles"] = await self.sync_config_profiles()
        except Exception as e:
            logger.error("Failed to sync config profiles: %s", e)
            results["config_profiles"] = -1
        
        try:
            # Sync templates
            results["templates"] = await self.sync_templates()
        except Exception as e:
            logger.error("Failed to sync templates: %s", e)
            results["templates"] = -1
        
        try:
            # Sync snippets
            results["snippets"] = await self.sync_snippets()
        except Exception as e:
            logger.error("Failed to sync snippets: %s", e)
            results["snippets"] = -1
        
        try:
            # Sync squads (internal and external)
            results["squads"] = await self.sync_squads()
        except Exception as e:
            logger.error("Failed to sync squads: %s", e)
            results["squads"] = -1

        try:
            # Sync HWID devices
            results["hwid_devices"] = await self.sync_all_hwid_devices()
        except Exception as e:
            logger.error("Failed to sync HWID devices: %s", e)
            results["hwid_devices"] = -1

        try:
            # Sync per-node user traffic
            results["node_traffic"] = await self.sync_node_traffic()
        except Exception as e:
            logger.error("Failed to sync node traffic: %s", e)
            results["node_traffic"] = -1

        logger.debug("Full sync completed: %s", results)
        return results
    
    async def sync_users(self) -> int:
        """
        Sync all users from API to database.
        Uses pagination to handle large datasets.
        Removes local users that no longer exist in API.
        Returns number of synced users.
        """
        if not db_service.is_connected:
            return 0

        total_synced = 0
        start = 0
        page_size = 100
        api_user_uuids: set[str] = set()

        try:
            while True:
                # Fetch users from API with pagination
                response = await api_client.get_users(
                    start=start,
                    size=page_size,
                    skip_cache=True
                )

                # API returns: {"response": {"users": [...], "total": N}}
                payload = response.get("response", response)
                users = payload.get("users") if isinstance(payload, dict) else []
                total = payload.get("total", 0) if isinstance(payload, dict) else 0

                if not users:
                    break

                # Upsert users to database
                for user in users:
                    user_uuid = user.get("uuid")
                    if user_uuid:
                        api_user_uuids.add(user_uuid)
                    try:
                        await db_service.upsert_user({"response": user})
                        total_synced += 1
                    except Exception as e:
                        logger.warning("Failed to sync user %s: %s", user.get("uuid"), e)

                # Check if we've reached the end
                start += page_size
                if start >= total or len(users) < page_size:
                    break

            # Remove local users that no longer exist in API
            if api_user_uuids:
                try:
                    local_users = await db_service.get_all_users(limit=50000)
                    removed = 0
                    for local_user in local_users:
                        local_uuid = local_user.get("uuid")
                        if local_uuid and local_uuid not in api_user_uuids:
                            await db_service.delete_user(local_uuid)
                            removed += 1
                    if removed:
                        logger.info("Removed %d stale users from local DB (not in API)", removed)
                except Exception as e:
                    logger.warning("Failed to reconcile stale users: %s", e)

            # Update sync metadata
            await db_service.update_sync_metadata(
                key="users",
                status="success",
                records_synced=total_synced
            )

            logger.debug("Synced %d users", total_synced)
            return total_synced

        except Exception as e:
            await db_service.update_sync_metadata(
                key="users",
                status="error",
                error_message=str(e)
            )
            raise
    
    async def sync_nodes(self) -> int:
        """
        Sync all nodes from API to database.
        Removes local nodes that no longer exist in API.
        Returns number of synced nodes.
        """
        if not db_service.is_connected:
            return 0

        try:
            # Fetch all nodes from API
            response = await api_client.get_nodes(skip_cache=True)
            nodes = response.get("response", [])

            # Collect API node UUIDs for reconciliation
            api_node_uuids = set()

            total_synced = 0
            for node in nodes:
                node_uuid = node.get("uuid")
                if node_uuid:
                    api_node_uuids.add(node_uuid)
                try:
                    await db_service.upsert_node({"response": node})
                    total_synced += 1
                except Exception as e:
                    logger.warning("Failed to sync node %s: %s", node.get("uuid"), e)

            # Remove local nodes that no longer exist in API
            try:
                local_nodes = await db_service.get_all_nodes()
                for local_node in local_nodes:
                    local_uuid = local_node.get("uuid")
                    if local_uuid and local_uuid not in api_node_uuids:
                        await db_service.delete_node(local_uuid)
                        logger.info("Removed stale node %s from local DB (not in API)", local_uuid)
            except Exception as e:
                logger.warning("Failed to reconcile stale nodes: %s", e)

            # Update sync metadata
            await db_service.update_sync_metadata(
                key="nodes",
                status="success",
                records_synced=total_synced
            )

            logger.debug("Synced %d nodes", total_synced)
            return total_synced

        except Exception as e:
            await db_service.update_sync_metadata(
                key="nodes",
                status="error",
                error_message=str(e)
            )
            raise
    
    async def sync_hosts(self) -> int:
        """
        Sync all hosts from API to database.
        Returns number of synced hosts.
        """
        if not db_service.is_connected:
            return 0
        
        try:
            # Fetch all hosts from API
            response = await api_client.get_hosts(skip_cache=True)
            hosts = response.get("response", [])
            
            total_synced = 0
            for host in hosts:
                try:
                    await db_service.upsert_host({"response": host})
                    total_synced += 1
                except Exception as e:
                    logger.warning("Failed to sync host %s: %s", host.get("uuid"), e)
            
            # Update sync metadata
            await db_service.update_sync_metadata(
                key="hosts",
                status="success",
                records_synced=total_synced
            )
            
            logger.debug("Synced %d hosts", total_synced)
            return total_synced
            
        except Exception as e:
            await db_service.update_sync_metadata(
                key="hosts",
                status="error",
                error_message=str(e)
            )
            raise
    
    async def sync_config_profiles(self) -> int:
        """
        Sync all config profiles from API to database.
        Returns number of synced profiles.
        """
        if not db_service.is_connected:
            return 0
        
        try:
            # Fetch all config profiles from API
            # API returns: {"response": {"configProfiles": [...]}}
            response = await api_client.get_config_profiles(skip_cache=True)
            payload = response.get("response", {})
            profiles = payload.get("configProfiles", []) if isinstance(payload, dict) else []
            
            total_synced = 0
            for profile in profiles:
                try:
                    await db_service.upsert_config_profile({"response": profile})
                    total_synced += 1
                except Exception as e:
                    logger.warning("Failed to sync config profile %s: %s", profile.get("uuid"), e)
            
            # Update sync metadata
            await db_service.update_sync_metadata(
                key="config_profiles",
                status="success",
                records_synced=total_synced
            )
            
            logger.debug("Synced %d config profiles", total_synced)
            return total_synced
            
        except Exception as e:
            await db_service.update_sync_metadata(
                key="config_profiles",
                status="error",
                error_message=str(e)
            )
            raise
    
    async def sync_templates(self) -> int:
        """
        Sync all subscription templates from API to database.
        Returns number of synced templates.
        """
        if not db_service.is_connected:
            return 0
        
        try:
            response = await api_client.get_templates()
            payload = response.get("response", {})
            templates = payload.get("subscriptionTemplates", []) if isinstance(payload, dict) else []
            
            # Clear old templates and insert new
            await db_service.delete_all_templates()
            
            total_synced = 0
            for tpl in templates:
                try:
                    await db_service.upsert_template({"response": tpl})
                    total_synced += 1
                except Exception as e:
                    logger.warning("Failed to sync template %s: %s", tpl.get("uuid"), e)
            
            await db_service.update_sync_metadata(
                key="templates",
                status="success",
                records_synced=total_synced
            )
            
            logger.debug("Synced %d templates", total_synced)
            return total_synced
            
        except Exception as e:
            await db_service.update_sync_metadata(
                key="templates",
                status="error",
                error_message=str(e)
            )
            raise
    
    async def sync_snippets(self) -> int:
        """
        Sync all snippets from API to database.
        Returns number of synced snippets.
        """
        if not db_service.is_connected:
            return 0
        
        try:
            response = await api_client.get_snippets()
            payload = response.get("response", {})
            snippets = payload.get("snippets", []) if isinstance(payload, dict) else []
            
            # Clear old snippets and insert new
            await db_service.delete_all_snippets()
            
            total_synced = 0
            for snippet in snippets:
                try:
                    await db_service.upsert_snippet({"response": snippet})
                    total_synced += 1
                except Exception as e:
                    logger.warning("Failed to sync snippet %s: %s", snippet.get("name"), e)
            
            await db_service.update_sync_metadata(
                key="snippets",
                status="success",
                records_synced=total_synced
            )
            
            logger.debug("Synced %d snippets", total_synced)
            return total_synced
            
        except Exception as e:
            await db_service.update_sync_metadata(
                key="snippets",
                status="error",
                error_message=str(e)
            )
            raise
    
    async def sync_squads(self) -> int:
        """
        Sync all squads (internal and external) from API to database.
        Returns total number of synced squads.
        """
        if not db_service.is_connected:
            return 0
        
        total_synced = 0
        
        # Sync internal squads
        try:
            response = await api_client.get_internal_squads()
            payload = response.get("response", {})
            squads = payload.get("internalSquads", []) if isinstance(payload, dict) else []
            
            await db_service.delete_all_internal_squads()
            
            for squad in squads:
                try:
                    await db_service.upsert_internal_squads({"response": [squad]})
                    total_synced += 1
                except Exception as e:
                    logger.warning("Failed to sync internal squad %s: %s", squad.get("uuid"), e)
                    
        except Exception as e:
            logger.warning("Failed to sync internal squads: %s", e)
        
        # Sync external squads
        try:
            response = await api_client.get_external_squads()
            payload = response.get("response", {})
            squads = payload.get("externalSquads", []) if isinstance(payload, dict) else []
            
            await db_service.delete_all_external_squads()
            
            for squad in squads:
                try:
                    await db_service.upsert_external_squads({"response": [squad]})
                    total_synced += 1
                except Exception as e:
                    logger.warning("Failed to sync external squad %s: %s", squad.get("uuid"), e)
                    
        except Exception as e:
            logger.warning("Failed to sync external squads: %s", e)
        
        await db_service.update_sync_metadata(
            key="squads",
            status="success",
            records_synced=total_synced
        )
        
        logger.debug("Synced %d squads (internal + external)", total_synced)
        return total_synced
    
    # ==================== Webhook Event Handlers with Diff ====================
    
    async def handle_webhook_event(self, event: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle webhook event, update database, and return diff for notifications.
        
        Args:
            event: Event type (e.g., "user.created", "node.modified")
            event_data: Event payload data
            
        Returns:
            Dict with keys:
                - old_data: Data before change (from DB) or None if created
                - new_data: Data after change (from webhook)
                - changes: List of human-readable changes
                - is_new: True if this is a new record
        """
        result = {
            "old_data": None,
            "new_data": event_data,
            "changes": [],
            "is_new": False
        }
        
        if not db_service.is_connected:
            logger.debug("Database not connected, skipping webhook sync for %s", event)
            return result
        
        try:
            if event.startswith("user."):
                return await self._handle_user_webhook_with_diff(event, event_data)
            elif event.startswith("node."):
                return await self._handle_node_webhook_with_diff(event, event_data)
            elif event.startswith("host."):
                return await self._handle_host_webhook_with_diff(event, event_data)
            elif event.startswith("user_hwid_devices."):
                return await self._handle_hwid_webhook(event, event_data)
            else:
                logger.debug("Unhandled webhook event for sync: %s", event)
                return result
                
        except Exception as e:
            logger.error("Error handling webhook event %s: %s", event, e)
            return result
    
    async def _handle_user_webhook_with_diff(self, event: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user webhook events with diff tracking."""
        uuid = event_data.get("uuid")
        result = {
            "old_data": None,
            "new_data": event_data,
            "changes": [],
            "is_new": False
        }
        
        if not uuid:
            logger.warning("User webhook event without UUID: %s", event)
            return result
        
        # Get old data from DB before updating
        # Данные из БД уже в формате API (через _db_row_to_api_format)
        old_db_record = await db_service.get_user_by_uuid(uuid)
        if old_db_record and old_db_record.get("uuid"):
            result["old_data"] = old_db_record
            logger.debug("Found old user data in DB for diff: %s", uuid)
        
        if event == "user.deleted":
            await db_service.delete_user(uuid)
            logger.debug("Deleted user %s from database (webhook)", uuid)
        else:
            # Upsert new data
            await db_service.upsert_user({"response": event_data})
            logger.debug("Updated user %s in database (webhook: %s)", uuid, event)
            
            # Calculate changes if we have old data
            if result["old_data"]:
                result["changes"] = _compare_user_data(result["old_data"], event_data)
                logger.debug("Calculated %d changes for user %s", len(result["changes"]), uuid)
            else:
                result["is_new"] = True
        
        return result
    
    async def _handle_node_webhook_with_diff(self, event: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle node webhook events with diff tracking."""
        uuid = event_data.get("uuid")
        result = {
            "old_data": None,
            "new_data": event_data,
            "changes": [],
            "is_new": False
        }
        
        if not uuid:
            logger.warning("Node webhook event without UUID: %s", event)
            return result
        
        # Get old data from DB (уже в формате API)
        old_db_record = await db_service.get_node_by_uuid(uuid)
        if old_db_record and old_db_record.get("uuid"):
            result["old_data"] = old_db_record
        
        if event == "node.deleted":
            await db_service.delete_node(uuid)
            logger.debug("Deleted node %s from database (webhook)", uuid)
        else:
            await db_service.upsert_node({"response": event_data})
            logger.debug("Updated node %s in database (webhook: %s)", uuid, event)
            
            if result["old_data"]:
                result["changes"] = _compare_node_data(result["old_data"], event_data)
            else:
                result["is_new"] = True
        
        return result
    
    async def _handle_host_webhook_with_diff(self, event: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle host webhook events with diff tracking."""
        uuid = event_data.get("uuid")
        result = {
            "old_data": None,
            "new_data": event_data,
            "changes": [],
            "is_new": False
        }
        
        if not uuid:
            logger.warning("Host webhook event without UUID: %s", event)
            return result
        
        # Get old data from DB (уже в формате API)
        old_db_record = await db_service.get_host_by_uuid(uuid)
        if old_db_record and old_db_record.get("uuid"):
            result["old_data"] = old_db_record
        
        if event == "host.deleted":
            await db_service.delete_host(uuid)
            logger.debug("Deleted host %s from database (webhook)", uuid)
        else:
            await db_service.upsert_host({"response": event_data})
            logger.debug("Updated host %s in database (webhook: %s)", uuid, event)
            
            if result["old_data"]:
                result["changes"] = _compare_host_data(result["old_data"], event_data)
            else:
                result["is_new"] = True
        
        return result
    
    async def _handle_hwid_webhook(self, event: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle HWID device webhook events."""
        result = {
            "old_data": None,
            "new_data": event_data,
            "changes": [],
            "is_new": False
        }

        # Извлекаем данные о пользователе и устройстве
        user_data = event_data.get("user", {})
        hwid_data = event_data.get("hwidDevice", {})

        user_uuid = user_data.get("uuid")
        hwid = hwid_data.get("hwid")

        if not user_uuid or not hwid:
            logger.warning("HWID webhook event without user UUID or HWID: %s", event)
            return result

        if event == "user_hwid_devices.added":
            # Добавляем устройство в БД
            platform = hwid_data.get("platform")
            os_version = hwid_data.get("osVersion")
            device_model = hwid_data.get("deviceModel")
            app_version = hwid_data.get("appVersion")
            user_agent = hwid_data.get("userAgent")
            created_at = hwid_data.get("createdAt")
            updated_at = hwid_data.get("updatedAt")

            from datetime import datetime
            created_dt = None
            updated_dt = None
            if created_at:
                try:
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass
            if updated_at:
                try:
                    updated_dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass

            await db_service.upsert_hwid_device(
                user_uuid=user_uuid,
                hwid=hwid,
                platform=platform,
                os_version=os_version,
                device_model=device_model,
                app_version=app_version,
                user_agent=user_agent,
                created_at=created_dt,
                updated_at=updated_dt
            )
            result["is_new"] = True
            logger.info("Added HWID device %s for user %s (webhook)", hwid[:20], user_uuid)

        elif event == "user_hwid_devices.deleted":
            # Удаляем устройство из БД
            await db_service.delete_hwid_device(user_uuid=user_uuid, hwid=hwid)
            logger.info("Deleted HWID device %s for user %s (webhook)", hwid[:20], user_uuid)

        return result

    # ==================== Node Traffic Sync ====================

    async def sync_node_traffic(self) -> int:
        """Sync per-user traffic for each active node from Remnawave API.

        Calls /api/bandwidth-stats/nodes/{uuid}/users for each connected node,
        stores results in the local user_node_traffic table.
        Returns total number of upserted records.
        """
        if not db_service.is_connected:
            return 0

        try:
            nodes = await db_service.get_all_nodes()
            active_nodes = [
                n for n in nodes
                if n.get("is_connected") and not n.get("is_disabled")
            ]

            now = datetime.now(timezone.utc)
            start_str = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d")
            end_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")

            total_synced = 0

            for node in active_nodes:
                node_uuid = str(node["uuid"])
                try:
                    result = await api_client.get_node_users_usage(
                        node_uuid, start=start_str, end=end_str, top_users_limit=500
                    )
                    response = result.get("response", result) if isinstance(result, dict) else result
                    top_users = response.get("topUsers", []) if isinstance(response, dict) else []

                    for u in top_users:
                        user_uuid = u.get("uuid", u.get("userUuid", ""))
                        total_bytes = int(u.get("total", 0) or 0)
                        if user_uuid and total_bytes > 0:
                            await db_service.upsert_user_node_traffic(
                                user_uuid, node_uuid, total_bytes
                            )
                            total_synced += 1
                except Exception as e:
                    logger.warning(
                        "Failed to sync traffic for node %s: %s",
                        node.get("name", node_uuid), e,
                    )

            await db_service.update_sync_metadata(
                key="node_traffic",
                status="success",
                records_synced=total_synced,
            )
            logger.debug("Synced node traffic: %d records across %d nodes", total_synced, len(active_nodes))
            return total_synced

        except Exception as e:
            await db_service.update_sync_metadata(
                key="node_traffic",
                status="error",
                error_message=str(e),
            )
            raise

    # ==================== On-Demand Sync ====================

    async def sync_single_user(self, uuid: str) -> bool:
        """
        Sync a single user from API to database.
        Returns True if successful.
        """
        if not db_service.is_connected:
            return False
        
        try:
            user = await api_client.get_user_by_uuid(uuid)
            await db_service.upsert_user(user)
            logger.debug("Synced single user %s", uuid)
            return True
        except Exception as e:
            logger.warning("Failed to sync single user %s: %s", uuid, e)
            return False
    
    async def sync_single_node(self, uuid: str) -> bool:
        """
        Sync a single node from API to database.
        Returns True if successful.
        """
        if not db_service.is_connected:
            return False
        
        try:
            node = await api_client.get_node(uuid)
            await db_service.upsert_node(node)
            logger.debug("Synced single node %s", uuid)
            return True
        except Exception as e:
            logger.warning("Failed to sync single node %s: %s", uuid, e)
            return False
    
    async def sync_single_host(self, uuid: str) -> bool:
        """
        Sync a single host from API to database.
        Returns True if successful.
        """
        if not db_service.is_connected:
            return False

        try:
            host = await api_client.get_host(uuid)
            await db_service.upsert_host(host)
            logger.debug("Synced single host %s", uuid)
            return True
        except Exception as e:
            logger.warning("Failed to sync single host %s: %s", uuid, e)
            return False

    async def sync_user_hwid_devices(self, user_uuid: str) -> int:
        """
        Sync HWID devices for a single user from API to database.
        Returns number of synced devices.
        """
        if not db_service.is_connected:
            return 0

        try:
            result = await api_client.get_user_hwid_devices(user_uuid)

            # Handle various API response formats (same logic as GET endpoint)
            response = result.get("response", result) if isinstance(result, dict) else result
            if isinstance(response, list):
                devices = response
            elif isinstance(response, dict):
                # Try common nested keys: "devices", "hwidDevices", "list"
                devices = (
                    response.get("devices")
                    or response.get("hwidDevices")
                    or response.get("list")
                    or []
                )
            else:
                devices = []

            if not devices:
                # Если устройств нет - удаляем все из БД
                await db_service.delete_all_user_hwid_devices(user_uuid)
                return 0

            # Validate that devices is a proper list of dicts/strings, not a misparse
            if not isinstance(devices, list):
                logger.warning(
                    "Unexpected devices type %s for user %s, skipping sync",
                    type(devices).__name__, user_uuid,
                )
                return 0

            synced = await db_service.sync_user_hwid_devices(user_uuid, devices)
            logger.debug("Synced %d HWID devices for user %s", synced, user_uuid)
            return synced

        except Exception as e:
            logger.warning("Failed to sync HWID devices for user %s: %s", user_uuid, e)
            return 0

    async def sync_all_hwid_devices(self) -> int:
        """
        Sync HWID devices for all users with device limit > 0.
        Returns total number of synced devices.
        """
        if not db_service.is_connected:
            return 0

        total_synced = 0
        start = 0
        page_size = 100

        try:
            while True:
                # Получаем устройства из API с пагинацией
                response = await api_client.get_all_hwid_devices(start=start, size=page_size)
                payload = response.get("response", {})
                if isinstance(payload, dict):
                    devices = (
                        payload.get("devices")
                        or payload.get("hwidDevices")
                        or payload.get("list")
                        or []
                    )
                    total = payload.get("total", 0)
                elif isinstance(payload, list):
                    devices = payload
                    total = len(devices)
                else:
                    devices = []
                    total = 0

                if not devices:
                    break

                # Группируем устройства по пользователям
                devices_by_user: Dict[str, List[Dict]] = {}
                for device in devices:
                    user_uuid = device.get("userUuid")
                    if user_uuid:
                        if user_uuid not in devices_by_user:
                            devices_by_user[user_uuid] = []
                        devices_by_user[user_uuid].append(device)

                # Синхронизируем устройства по пользователям
                for user_uuid, user_devices in devices_by_user.items():
                    try:
                        synced = await db_service.sync_user_hwid_devices(user_uuid, user_devices)
                        total_synced += synced
                    except Exception as e:
                        logger.warning("Failed to sync HWID devices for user %s: %s", user_uuid, e)

                # Проверяем, достигли ли конца
                start += page_size
                if start >= total or len(devices) < page_size:
                    break

            # Обновляем метаданные синхронизации
            await db_service.update_sync_metadata(
                key="hwid_devices",
                status="success",
                records_synced=total_synced
            )

            logger.debug("Synced %d HWID devices total", total_synced)
            return total_synced

        except Exception as e:
            await db_service.update_sync_metadata(
                key="hwid_devices",
                status="error",
                error_message=str(e)
            )
            logger.error("Failed to sync all HWID devices: %s", e)
            return total_synced


# ==================== Data Comparison Functions ====================

def _compare_user_data(old_data: Dict[str, Any], new_data: Dict[str, Any]) -> List[str]:
    """
    Compare user data and return list of human-readable changes.
    """
    changes = []
    
    fields_to_compare = {
        "username": ("Username", None),
        "email": ("Email", None),
        "telegramId": ("Telegram ID", None),
        "status": ("Статус", None),
        "expireAt": ("Срок действия", _format_date),
        "trafficLimitBytes": ("Лимит трафика", _format_bytes),
        "hwidDeviceLimit": ("Лимит устройств", None),
        "description": ("Описание", None),
    }
    
    for field, (label, formatter) in fields_to_compare.items():
        old_val = old_data.get(field)
        new_val = new_data.get(field)
        
        # Нормализуем значения для сравнения (особенно даты)
        old_normalized = _normalize_value(old_val)
        new_normalized = _normalize_value(new_val)
        
        if old_normalized != new_normalized:
            old_display = formatter(old_val) if formatter and old_val else (old_val or "—")
            new_display = formatter(new_val) if formatter and new_val else (new_val or "—")
            changes.append(f"• {label}: {old_display} → {new_display}")
            logger.debug("User diff: %s changed from %r to %r", field, old_val, new_val)
    
    return changes


def _normalize_value(value):
    """Нормализует значение для сравнения."""
    if value is None:
        return None
    
    # Нормализуем строки дат для сравнения (убираем микросекунды и Z)
    if isinstance(value, str) and ('T' in value or '-' in value):
        # Пытаемся нормализовать дату
        try:
            # Убираем микросекунды и Z для унифицированного сравнения
            normalized = value.replace('Z', '+00:00')
            # Парсим и форматируем обратно без микросекунд
            from datetime import datetime
            dt = datetime.fromisoformat(normalized)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, AttributeError):
            pass
    
    return value


def _compare_node_data(old_data: Dict[str, Any], new_data: Dict[str, Any]) -> List[str]:
    """
    Compare node data and return list of human-readable changes.
    """
    changes = []
    
    fields_to_compare = {
        "name": ("Название", None),
        "address": ("Адрес", None),
        "port": ("Порт", None),
        "isDisabled": ("Отключена", _format_bool),
        "trafficLimitBytes": ("Лимит трафика", _format_bytes),
    }
    
    for field, (label, formatter) in fields_to_compare.items():
        old_val = old_data.get(field)
        new_val = new_data.get(field)
        
        if old_val != new_val:
            old_display = formatter(old_val) if formatter else (old_val if old_val is not None else "—")
            new_display = formatter(new_val) if formatter else (new_val if new_val is not None else "—")
            changes.append(f"• {label}: {old_display} → {new_display}")
    
    return changes


def _compare_host_data(old_data: Dict[str, Any], new_data: Dict[str, Any]) -> List[str]:
    """
    Compare host data and return list of human-readable changes.
    """
    changes = []
    
    fields_to_compare = {
        "remark": ("Название", None),
        "address": ("Адрес", None),
        "port": ("Порт", None),
        "isDisabled": ("Отключен", _format_bool),
    }
    
    for field, (label, formatter) in fields_to_compare.items():
        old_val = old_data.get(field)
        new_val = new_data.get(field)
        
        if old_val != new_val:
            old_display = formatter(old_val) if formatter else (old_val if old_val is not None else "—")
            new_display = formatter(new_val) if formatter else (new_val if new_val is not None else "—")
            changes.append(f"• {label}: {old_display} → {new_display}")
    
    return changes


def _format_bytes(value) -> str:
    """Format bytes to human-readable format."""
    if value is None or value == 0:
        return "Безлимит"
    
    try:
        value = int(value)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if abs(value) < 1024.0:
                return f"{value:.1f} {unit}"
            value /= 1024.0
        return f"{value:.1f} PB"
    except (ValueError, TypeError):
        return str(value)


def _format_date(value) -> str:
    """Format date to human-readable format."""
    if value is None:
        return "Бессрочно"
    
    if isinstance(value, str):
        try:
            # Try to parse ISO format
            from datetime import datetime
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.strftime("%d.%m.%Y %H:%M")
        except ValueError:
            return value
    
    return str(value)


def _format_bool(value) -> str:
    """Format boolean to human-readable format."""
    if value is True:
        return "Да"
    elif value is False:
        return "Нет"
    return "—"


# Global sync service instance
sync_service = SyncService()
