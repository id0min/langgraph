import asyncio
import concurrent
import concurrent.futures
import functools
import inspect
import types
from typing import (
    Any,
    Awaitable,
    Callable,
    Optional,
    TypeVar,
    Union,
    overload,
)

from typing_extensions import ParamSpec

from langgraph.channels.ephemeral_value import EphemeralValue
from langgraph.channels.last_value import LastValue
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import CONF, END, START, TAG_HIDDEN
from langgraph.pregel import Pregel
from langgraph.pregel.call import get_runnable_for_func
from langgraph.pregel.read import PregelNode
from langgraph.pregel.write import ChannelWrite, ChannelWriteEntry
from langgraph.store.base import BaseStore
from langgraph.types import RetryPolicy, StreamMode, StreamWriter

P = ParamSpec("P")
P1 = TypeVar("P1")
T = TypeVar("T")


def call(
    func: Callable[P, T],
    *args: Any,
    retry: Optional[RetryPolicy] = None,
    **kwargs: Any,
) -> concurrent.futures.Future[T]:
    from langgraph.constants import CONFIG_KEY_CALL
    from langgraph.utils.config import get_config

    config = get_config()
    impl = config[CONF][CONFIG_KEY_CALL]
    fut = impl(func, (args, kwargs), retry=retry, callbacks=config["callbacks"])
    return fut


@overload
def task(
    *, retry: Optional[RetryPolicy] = None
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, asyncio.Future[T]]]: ...


@overload
def task(  # type: ignore[overload-cannot-match]
    *, retry: Optional[RetryPolicy] = None
) -> Callable[[Callable[P, T]], Callable[P, concurrent.futures.Future[T]]]: ...


@overload
def task(
    __func_or_none__: Callable[P, T],
) -> Callable[P, concurrent.futures.Future[T]]: ...


@overload
def task(
    __func_or_none__: Callable[P, Awaitable[T]],
) -> Callable[P, asyncio.Future[T]]: ...


def task(
    __func_or_none__: Optional[Union[Callable[P, T], Callable[P, Awaitable[T]]]] = None,
    *,
    retry: Optional[RetryPolicy] = None,
) -> Union[
    Callable[[Callable[P, Awaitable[T]]], Callable[P, asyncio.Future[T]]],
    Callable[[Callable[P, T]], Callable[P, concurrent.futures.Future[T]]],
    Callable[P, asyncio.Future[T]],
    Callable[P, concurrent.futures.Future[T]],
]:
    def decorator(
        func: Union[Callable[P, Awaitable[T]], Callable[P, T]],
    ) -> Callable[P, concurrent.futures.Future[T]]:
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def _tick(__allargs__: tuple) -> T:
                return await func(*__allargs__[0], **__allargs__[1])

        else:

            @functools.wraps(func)
            def _tick(__allargs__: tuple) -> T:
                return func(*__allargs__[0], **__allargs__[1])

        return functools.update_wrapper(
            functools.partial(call, _tick, retry=retry), func
        )

    if __func_or_none__ is not None:
        return decorator(__func_or_none__)

    return decorator


def entrypoint(
    *,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    store: Optional[BaseStore] = None,
    config_schema: Optional[type[Any]] = None,
) -> Callable[[types.FunctionType], Pregel]:
    def _imp(func: types.FunctionType) -> Pregel:
        """Convert a function into a Pregel graph.

        Args:
            func: The function to convert. Support both sync and async functions, as well
                   as generator and async generator functions.

        Returns:
            A Pregel graph.
        """
        # wrap generators in a function that writes to StreamWriter
        if inspect.isgeneratorfunction(func):
            original_sig = inspect.signature(func)
            # Check if original signature has a writer argument with a matching type.
            # If not, we'll inject it into the decorator, but not pass it
            # to the wrapped function.
            if "writer" in original_sig.parameters:

                @functools.wraps(func)
                def gen_wrapper(*args: Any, writer: StreamWriter, **kwargs: Any) -> Any:
                    chunks = []
                    for chunk in func(*args, writer=writer, **kwargs):
                        writer(chunk)
                        chunks.append(chunk)
                    return chunks
            else:

                @functools.wraps(func)
                def gen_wrapper(*args: Any, writer: StreamWriter, **kwargs: Any) -> Any:
                    chunks = []
                    # Do not pass the writer argument to the wrapped function
                    # as it does not have a matching parameter
                    for chunk in func(*args, **kwargs):
                        writer(chunk)
                        chunks.append(chunk)
                    return chunks

                # Create a new parameter for the writer argument
                extra_param = inspect.Parameter(
                    "writer",
                    inspect.Parameter.KEYWORD_ONLY,
                    # The extra argument is a keyword-only argument
                    default=lambda _: None,
                )
                # Update the function's signature to include the extra argument
                new_params = list(original_sig.parameters.values()) + [extra_param]
                new_sig = original_sig.replace(parameters=new_params)
                # Update the signature of the wrapper function
                gen_wrapper.__signature__ = new_sig  # type: ignore
            bound = get_runnable_for_func(gen_wrapper)
            stream_mode: StreamMode = "custom"
        elif inspect.isasyncgenfunction(func):
            original_sig = inspect.signature(func)
            # Check if original signature has a writer argument with a matching type.
            # If not, we'll inject it into the decorator, but not pass it
            # to the wrapped function.
            if "writer" in original_sig.parameters:

                @functools.wraps(func)
                async def agen_wrapper(
                    *args: Any, writer: StreamWriter, **kwargs: Any
                ) -> Any:
                    chunks = []
                    async for chunk in func(*args, writer=writer, **kwargs):
                        writer(chunk)
                        chunks.append(chunk)
                    return chunks
            else:

                @functools.wraps(func)
                async def agen_wrapper(
                    *args: Any, writer: StreamWriter, **kwargs: Any
                ) -> Any:
                    chunks = []
                    async for chunk in func(*args, **kwargs):
                        writer(chunk)
                        chunks.append(chunk)
                    return chunks

                # Create a new parameter for the writer argument
                extra_param = inspect.Parameter(
                    "writer",
                    inspect.Parameter.KEYWORD_ONLY,
                    # The extra argument is a keyword-only argument
                    default=lambda _: None,
                )
                # Update the function's signature to include the extra argument
                new_params = list(original_sig.parameters.values()) + [extra_param]
                new_sig = original_sig.replace(parameters=new_params)
                # Update the signature of the wrapper function
                agen_wrapper.__signature__ = new_sig  # type: ignore

            bound = get_runnable_for_func(agen_wrapper)
            stream_mode = "custom"
        else:
            bound = get_runnable_for_func(func)
            stream_mode = "updates"

        # get input and output types
        sig = inspect.signature(func)
        first_parameter_name = next(iter(sig.parameters.keys()), None)
        if not first_parameter_name:
            raise ValueError("Entrypoint function must have at least one parameter")
        input_type = (
            sig.parameters[first_parameter_name].annotation
            if sig.parameters[first_parameter_name].annotation
            is not inspect.Signature.empty
            else Any
        )
        output_type = (
            sig.return_annotation
            if sig.return_annotation is not inspect.Signature.empty
            else Any
        )

        return Pregel(
            nodes={
                func.__name__: PregelNode(
                    bound=bound,
                    triggers=[START],
                    channels=[START],
                    writers=[ChannelWrite([ChannelWriteEntry(END)], tags=[TAG_HIDDEN])],
                )
            },
            channels={
                START: EphemeralValue(input_type),
                END: LastValue(output_type, END),
            },
            input_channels=START,
            output_channels=END,
            stream_channels=END,
            stream_mode=stream_mode,
            stream_eager=True,
            checkpointer=checkpointer,
            store=store,
            config_type=config_schema,
        )

    return _imp
