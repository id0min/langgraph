import dataclasses
import importlib
import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from langchain_core.load.load import Reviver
from langchain_core.load.serializable import Serializable
from langchain_core.pydantic_v1 import BaseModel as LcBaseModel
from pydantic import BaseModel

from langgraph.serde.base import SerializerProtocol

LC_REVIVER = Reviver()


class JsonPlusSerializer(SerializerProtocol):
    def _encode_constructor_args(
        self,
        constructor: type[Any],
        *,
        method: Optional[str] = None,
        args: Optional[list[Any]] = None,
        kwargs: Optional[dict[str, Any]] = None,
    ):
        return {
            "lc": 2,
            "type": "constructor",
            "id": [*constructor.__module__.split("."), constructor.__name__],
            "method": method,
            "args": args if args is not None else [],
            "kwargs": kwargs if kwargs is not None else {},
        }

    def _default(self, obj):
        if isinstance(obj, Serializable):
            return obj.to_json()
        elif isinstance(obj, (BaseModel, LcBaseModel)):
            # prefer non-deprecated method if available
            if hasattr(obj, "model_dump"):
                return self._encode_constructor_args(
                    obj.__class__, kwargs=obj.model_dump()
                )
            else:
                return self._encode_constructor_args(obj.__class__, kwargs=obj.dict())
        elif isinstance(obj, UUID):
            return self._encode_constructor_args(UUID, args=[obj.hex])
        elif isinstance(obj, (set, frozenset)):
            return self._encode_constructor_args(type(obj), args=[list(obj)])
        elif isinstance(obj, datetime):
            return self._encode_constructor_args(
                datetime, method="fromisoformat", args=[obj.isoformat()]
            )
        elif isinstance(obj, timezone):
            return self._encode_constructor_args(timezone, args=obj.__getinitargs__())
        elif isinstance(obj, timedelta):
            return self._encode_constructor_args(
                timedelta, args=[obj.days, obj.seconds, obj.microseconds]
            )
        elif dataclasses.is_dataclass(obj):
            return self._encode_constructor_args(
                obj.__class__,
                kwargs={
                    field.name: getattr(obj, field.name)
                    for field in dataclasses.fields(obj)
                },
            )
        elif isinstance(obj, Enum):
            return self._encode_constructor_args(obj.__class__, args=[obj.value])
        else:
            raise TypeError(
                f"Object of type {obj.__class__.__name__} is not JSON serializable"
            )

    def _reviver(self, value: dict[str, Any]) -> Any:
        if (
            value.get("lc", None) == 2
            and value.get("type", None) == "constructor"
            and value.get("id", None) is not None
        ):
            # Get module and class name
            [*module, name] = value["id"]
            # Import module
            mod = importlib.import_module(".".join(module))
            # Import class
            cls = getattr(mod, name)
            # Instantiate class
            if value["method"] is not None:
                method = getattr(cls, value["method"])
                return method(*value["args"], **value["kwargs"])
            else:
                return cls(*value["args"], **value["kwargs"])

        return LC_REVIVER(value)

    def dumps(self, obj):
        return json.dumps(self._convert_generators(obj), default=self._default, sort_keys=True).encode()

    def _convert_generators(self, obj):
        import types
        if isinstance(obj, types.GeneratorType):
            return list(obj)
        elif isinstance(obj, dict):
            return {k: self._convert_generators(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_generators(elem) for elem in obj]
        elif isinstance(obj, tuple):
            return tuple(self._convert_generators(elem) for elem in obj)
        return obj

    def loads(self, data: bytes) -> Any:
        return json.loads(data, object_hook=self._reviver)
