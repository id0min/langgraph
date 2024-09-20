from datetime import datetime
from typing import Any, Literal, Optional, Sequence, TypedDict, Union

Json = Optional[dict[str, Any]]

RunStatus = Literal["pending", "running", "error", "success", "timeout", "interrupted"]

ThreadStatus = Literal["idle", "busy", "interrupted"]

StreamMode = Literal["values", "messages", "updates", "events", "debug"]

DisconnectMode = Literal["cancel", "continue"]

MultitaskStrategy = Literal["reject", "interrupt", "rollback", "enqueue"]

OnConflictBehavior = Literal["raise", "do_nothing"]

OnCompletionBehavior = Literal["delete", "keep"]

All = Literal["*"]


class Config(TypedDict, total=False):
    tags: list[str]
    """
    Tags for this call and any sub-calls (eg. a Chain calling an LLM).
    You can use these to filter calls.
    """

    recursion_limit: int
    """
    Maximum number of times a call can recurse. If not provided, defaults to 25.
    """

    configurable: dict[str, Any]
    """
    Runtime values for attributes previously made configurable on this Runnable,
    or sub-Runnables, through .configurable_fields() or .configurable_alternatives().
    Check .output_schema() for a description of the attributes that have been made 
    configurable.
    """


class GraphSchema(TypedDict):
    """Graph model."""

    graph_id: str
    """The ID of the graph."""
    input_schema: Optional[dict]
    """The schema for the graph state.
    Missing if unable to generate JSON schema from graph."""
    state_schema: Optional[dict]
    """The schema for the graph state.
    Missing if unable to generate JSON schema from graph."""
    config_schema: Optional[dict]
    """The schema for the graph config.
    Missing if unable to generate JSON schema from graph."""


class AssistantBase(TypedDict):
    """Assistant base model."""

    assistant_id: str
    """The ID of the assistant."""
    graph_id: str
    """The ID of the graph."""
    config: Config
    """The assistant config."""
    created_at: datetime
    """The time the assistant was created."""
    updated_at: datetime
    """The last time the assistant was updated."""
    metadata: Json
    """The assistant metadata."""
    version: int
    """The version of the assistant"""


class AssistantVersion(AssistantBase):
    """Assistant version model."""

    pass


class Assistant(AssistantBase):
    """Assistant model."""

    assistant_name: str
    """The name of the assistant"""


class Thread(TypedDict):
    thread_id: str
    """The ID of the thread."""
    created_at: datetime
    """The time the thread was created."""
    updated_at: datetime
    """The last time the thread was updated."""
    metadata: Json
    """The thread metadata."""
    status: ThreadStatus
    """The status of the thread, one of 'idle', 'busy', 'interrupted'."""
    values: Json
    """The current state of the thread."""


class ThreadState(TypedDict):
    values: Union[list[dict], dict[str, Any]]
    """The state values."""
    next: Sequence[str]
    """The next nodes to execute. If empty, the thread is done until new input is 
    received."""
    checkpoint_id: str
    """The ID of the checkpoint."""
    metadata: Json
    """Metadata for this state"""
    created_at: Optional[str]
    """Timestamp of state creation"""
    parent_checkpoint_id: Optional[str]
    """The ID of the parent checkpoint. If missing, this is the root checkpoint."""


class Run(TypedDict):
    run_id: str
    """The ID of the run."""
    thread_id: str
    """The ID of the thread."""
    assistant_id: str
    """The assistant that was used for this run."""
    created_at: datetime
    """The time the run was created."""
    updated_at: datetime
    """The last time the run was updated."""
    status: RunStatus
    """The status of the run. One of 'pending', 'running', "error", 'success', "timeout", "interrupted"."""
    metadata: Json
    """The run metadata."""
    multitask_strategy: MultitaskStrategy
    """Strategy to handle concurrent runs on the same thread."""


class Cron(TypedDict):
    cron_id: str
    """The ID of the cron."""
    thread_id: Optional[str]
    """The ID of the thread."""
    end_time: Optional[datetime]
    """The end date to stop running the cron."""
    schedule: str
    """The schedule to run, cron format."""
    created_at: datetime
    """The time the cron was created."""
    updated_at: datetime
    """The last time the cron was updated."""
    payload: dict
    """The run payload to use for creating new run."""


class RunCreate(TypedDict):
    """Payload for creating a background run."""

    thread_id: Optional[str]
    assistant_id: str
    input: Optional[dict]
    metadata: Optional[dict]
    config: Optional[Config]
    checkpoint_id: Optional[str]
    interrupt_before: Optional[list[str]]
    interrupt_after: Optional[list[str]]
    webhook: Optional[str]
    multitask_strategy: Optional[MultitaskStrategy]
