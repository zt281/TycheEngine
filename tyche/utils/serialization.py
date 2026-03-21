# tyche/utils/serialization.py
import msgpack
import tyche_core

_TYCHE_CORE_MODULE = "tyche_core"

def serialize(payload) -> bytes:
    """Serialize a tyche_core type or plain dict to MessagePack bytes."""
    cls = type(payload)
    if cls.__module__ == _TYCHE_CORE_MODULE:
        fn_name = f"serialize_{cls.__name__.lower().lstrip('py')}"
        fn = getattr(tyche_core, fn_name, None)
        if fn is not None:
            return bytes(fn(payload))
        raise TypeError(f"No serializer registered for tyche_core type '{cls.__name__}'")
    return msgpack.packb(payload, use_bin_type=True)

def deserialize(type_name: str, data: bytes):
    fn = getattr(tyche_core, f"deserialize_{type_name.lower()}", None)
    if fn:
        return fn(data)
    return msgpack.unpackb(data, raw=False)
