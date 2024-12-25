# type: ignore

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from langgraph.checkpoint.base import (
    Checkpoint,
    CheckpointKey,
    CheckpointMetadata,
    create_checkpoint,
    empty_checkpoint,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from tests.conftest import DEFAULT_POSTGRES_URI


@asynccontextmanager
async def _pool_saver():
    """Fixture for pool mode testing."""
    database = f"test_{uuid4().hex[:16]}"
    # create unique db
    async with await AsyncConnection.connect(
        DEFAULT_POSTGRES_URI, autocommit=True
    ) as conn:
        await conn.execute(f"CREATE DATABASE {database}")
    try:
        # yield checkpointer
        async with AsyncConnectionPool(
            DEFAULT_POSTGRES_URI + database,
            max_size=10,
            kwargs={"autocommit": True, "row_factory": dict_row},
        ) as pool:
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()
            yield checkpointer
    finally:
        # drop unique db
        async with await AsyncConnection.connect(
            DEFAULT_POSTGRES_URI, autocommit=True
        ) as conn:
            await conn.execute(f"DROP DATABASE {database}")


@asynccontextmanager
async def _pipe_saver():
    """Fixture for pipeline mode testing."""
    database = f"test_{uuid4().hex[:16]}"
    # create unique db
    async with await AsyncConnection.connect(
        DEFAULT_POSTGRES_URI, autocommit=True
    ) as conn:
        await conn.execute(f"CREATE DATABASE {database}")
    try:
        async with await AsyncConnection.connect(
            DEFAULT_POSTGRES_URI + database,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        ) as conn:
            checkpointer = AsyncPostgresSaver(conn)
            await checkpointer.setup()
            async with conn.pipeline() as pipe:
                checkpointer = AsyncPostgresSaver(conn, pipe=pipe)
                yield checkpointer
    finally:
        # drop unique db
        async with await AsyncConnection.connect(
            DEFAULT_POSTGRES_URI, autocommit=True
        ) as conn:
            await conn.execute(f"DROP DATABASE {database}")


@asynccontextmanager
async def _base_saver():
    """Fixture for regular connection mode testing."""
    database = f"test_{uuid4().hex[:16]}"
    # create unique db
    async with await AsyncConnection.connect(
        DEFAULT_POSTGRES_URI, autocommit=True
    ) as conn:
        await conn.execute(f"CREATE DATABASE {database}")
    try:
        async with await AsyncConnection.connect(
            DEFAULT_POSTGRES_URI + database,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        ) as conn:
            checkpointer = AsyncPostgresSaver(conn)
            await checkpointer.setup()
            yield checkpointer
    finally:
        # drop unique db
        async with await AsyncConnection.connect(
            DEFAULT_POSTGRES_URI, autocommit=True
        ) as conn:
            await conn.execute(f"DROP DATABASE {database}")


@asynccontextmanager
async def _saver(name: str):
    if name == "base":
        async with _base_saver() as saver:
            yield saver
    elif name == "pool":
        async with _pool_saver() as saver:
            yield saver
    elif name == "pipe":
        async with _pipe_saver() as saver:
            yield saver


@pytest.fixture
def test_data():
    """Fixture providing test data for checkpoint tests."""
    config_1: RunnableConfig = {
        "configurable": {
            "thread_id": "thread-1",
            # for backwards compatibility testing
            "thread_ts": "1",
            "checkpoint_ns": "",
        }
    }
    config_2: RunnableConfig = {
        "configurable": {
            "thread_id": "thread-2",
            "checkpoint_id": "2",
            "checkpoint_ns": "",
        }
    }
    config_3: RunnableConfig = {
        "configurable": {
            "thread_id": "thread-2",
            "checkpoint_id": "2-inner",
            "checkpoint_ns": "inner",
        }
    }

    chkpnt_1: Checkpoint = empty_checkpoint()
    chkpnt_2: Checkpoint = create_checkpoint(chkpnt_1, {}, 1)
    chkpnt_3: Checkpoint = empty_checkpoint()

    metadata_1: CheckpointMetadata = {
        "source": "input",
        "step": 2,
        "writes": {},
        "score": 1,
    }
    metadata_2: CheckpointMetadata = {
        "source": "loop",
        "step": 1,
        "writes": {"foo": "bar"},
        "score": None,
    }
    metadata_3: CheckpointMetadata = {}

    return {
        "configs": [config_1, config_2, config_3],
        "checkpoints": [chkpnt_1, chkpnt_2, chkpnt_3],
        "metadata": [metadata_1, metadata_2, metadata_3],
    }


@pytest.mark.parametrize("saver_name", ["base", "pool", "pipe"])
async def test_asearch(request, saver_name: str, test_data) -> None:
    async with _saver(saver_name) as saver:
        configs = test_data["configs"]
        checkpoints = test_data["checkpoints"]
        metadata = test_data["metadata"]

        await saver.aput(configs[0], checkpoints[0], metadata[0], {})
        await saver.aput(configs[1], checkpoints[1], metadata[1], {})
        await saver.aput(configs[2], checkpoints[2], metadata[2], {})

        # call method / assertions
        query_1 = {"source": "input"}  # search by 1 key
        query_2 = {
            "step": 1,
            "writes": {"foo": "bar"},
        }  # search by multiple keys
        query_3: dict[str, Any] = {}  # search by no keys, return all checkpoints
        query_4 = {"source": "update", "step": 1}  # no match

        search_results_1 = [c async for c in saver.alist(None, filter=query_1)]
        assert len(search_results_1) == 1
        assert search_results_1[0].metadata == metadata[0]

        search_results_2 = [c async for c in saver.alist(None, filter=query_2)]
        assert len(search_results_2) == 1
        assert search_results_2[0].metadata == metadata[1]

        search_results_3 = [c async for c in saver.alist(None, filter=query_3)]
        assert len(search_results_3) == 3

        search_results_4 = [c async for c in saver.alist(None, filter=query_4)]
        assert len(search_results_4) == 0

        # search by config (defaults to checkpoints across all namespaces)
        search_results_5 = [
            c async for c in saver.alist({"configurable": {"thread_id": "thread-2"}})
        ]
        assert len(search_results_5) == 2
        assert {
            search_results_5[0].config["configurable"]["checkpoint_ns"],
            search_results_5[1].config["configurable"]["checkpoint_ns"],
        } == {"", "inner"}


@pytest.mark.parametrize("saver_name", ["base", "pool", "pipe"])
async def test_null_chars(request, saver_name: str, test_data) -> None:
    async with _saver(saver_name) as saver:
        config = await saver.aput(
            test_data["configs"][0],
            test_data["checkpoints"][0],
            {"my_key": "\x00abc"},
            {},
        )
        assert (await saver.aget_tuple(config)).metadata["my_key"] == "abc"  # type: ignore
        assert [c async for c in saver.alist(None, filter={"my_key": "abc"})][
            0
        ].metadata["my_key"] == "abc"


@pytest.mark.parametrize("saver_name", ["base", "pool", "pipe"])
async def test_aput_aget_writes(request, saver_name: str, test_data) -> None:
    CONFIG = test_data["configs"][1]
    CKPT_ID = CONFIG["configurable"]["checkpoint_id"]
    THREAD_ID = CONFIG["configurable"]["thread_id"]
    CKPT_KEY = CheckpointKey(
        thread_id=THREAD_ID, checkpoint_ns="", checkpoint_id=CKPT_ID
    )

    TASK1 = "task1"
    TASK2 = "task2"

    async with _saver(saver_name) as saver:
        assert await saver.aget_writes(CONFIG, task_id=TASK1) is None

        # Test that writes are saved and retrieved correctly.
        writes1 = (("node1", 1), ("node2", "a"), ("node3", 1.0), ("node4", True))
        await saver.aput_writes(CONFIG, writes1, TASK1)
        assert await saver.aget_writes(CONFIG, task_id=TASK1) == (CKPT_KEY, writes1)

        # Write to another task and check that writes are saved and retrieved correctly.
        writes2 = (("node1", 2), ("node2", "b"), ("node3", 2.0), ("node4", False))
        await saver.aput_writes(CONFIG, writes2, TASK2)
        assert await saver.aget_writes(CONFIG, task_id=TASK2) == (CKPT_KEY, writes2)

        # Test that writes are not overwritten
        assert await saver.aget_writes(CONFIG, task_id=TASK1) == (CKPT_KEY, writes1)


@pytest.mark.parametrize("saver_name", ["base", "pool", "pipe"])
async def test_aget_writes_when_multiple_entries_exist_pick_the_latest(
    request, saver_name: str, test_data
) -> None:
    TASK_ID = "task1"

    async with _saver(saver_name) as saver:
        # Write writes associated with checkpoint 000.
        cfg1: RunnableConfig = {
            "configurable": {
                "thread_id": "thread-1",
                "checkpoint_ns": "",
                "checkpoint_id": "000",
            }
        }
        writes1 = [("node", 1)]
        await saver.aput_writes(cfg1, writes1, TASK_ID)

        # Write writes associated with checkpoint 001.
        cfg2: RunnableConfig = {
            "configurable": {
                "thread_id": "thread-1",
                "checkpoint_ns": "",
                "checkpoint_id": "001",
            }
        }
        writes2 = [("node", 2)]
        await saver.aput_writes(cfg2, writes2, TASK_ID)

        # Write writes associated with checkpoint 002 but different thread.
        cfg3: RunnableConfig = {
            "configurable": {
                "thread_id": "thread-2",
                "checkpoint_ns": "",
                "checkpoint_id": "002",
            }
        }
        writes3 = [("node", 3)]
        await saver.aput_writes(cfg3, writes3, TASK_ID)

        # Check that the latest writes are returned.
        cfg: RunnableConfig = {
            "configurable": {
                "thread_id": "thread-1",
                "checkpoint_ns": "any",
                "checkpoint_id": "any",
            }
        }
        want_key = CheckpointKey(
            thread_id="thread-1", checkpoint_ns="", checkpoint_id="001"
        )
        assert await saver.aget_writes(cfg, task_id=TASK_ID) == (
            want_key,
            tuple(writes2),
        )
