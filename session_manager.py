"""Minimal SessionManager backed by AsyncPostgresSaver."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, AsyncIterator, Sequence, Tuple

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from sql_utilities import (
    create_async_postgres_connection_pool,
    setup_postgres_checkpointer_tables_async,
    test_database_connection_async,
)

logger = logging.getLogger(__name__)


class SessionManager(AsyncPostgresSaver):
    """Thin wrapper around AsyncPostgresSaver with startup and lifecycle helpers."""

    def __init__(self):
        self.pool = None
        self._setup_completed = False

    async def setup(self):
        if self._setup_completed:
            return

        self.pool = create_async_postgres_connection_pool()
        await self.pool.open()
        super().__init__(conn=self.pool)

        if not await setup_postgres_checkpointer_tables_async(self):
            raise RuntimeError("Failed to setup PostgreSQL checkpointer tables")

        self._setup_completed = True
        logger.info("SessionManager setup completed")

    async def ensure_setup(self):
        if not self._setup_completed:
            await self.setup()

    async def start(self):
        await self.ensure_setup()
        if not await test_database_connection_async():
            raise RuntimeError("Failed to establish database connection for SessionManager")
        logger.info("SessionManager started")

    async def stop(self):
        if self.pool:
            await self.pool.close()
            logger.info("SessionManager stopped and pool closed")

    async def aget(self, config: RunnableConfig) -> Optional[Checkpoint]:
        await self.ensure_setup()
        return await super().aget(config)

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        await self.ensure_setup()
        return await super().aget_tuple(config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        await self.ensure_setup()
        return await super().aput(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await self.ensure_setup()
        await super().aput_writes(config, writes, task_id, task_path)

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        await self.ensure_setup()
        async for item in super().alist(config, filter=filter, before=before, limit=limit):
            yield item

    async def adelete_thread(self, thread_id: str) -> None:
        await self.ensure_setup()
        await super().adelete_thread(thread_id)
