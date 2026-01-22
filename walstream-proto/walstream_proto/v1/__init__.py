"""Auto-generated protocol buffer modules for v1."""

try:
    from .walstream_pb2 import (
        ChangeRecord,
        ReplayRequest,
        ReplayResponse,
        HealthRequest,
        HealthResponse,
    )
    from .walstream_pb2_grpc import (
        ReplayerStub,
        ReplayerServicer,
        add_ReplayerServicer_to_server,
    )

    __all__ = [
        "ChangeRecord",
        "ReplayRequest",
        "ReplayResponse",
        "ReplayerStub",
        "ReplayerServicer",
        "add_ReplayerServicer_to_server",
        "HealthRequest",
        "HealthResponse",
    ]
except ImportError as e:
    # Proto files not yet generated - this is expected before running generate-proto
    import warnings
    warnings.warn(
        f"Proto files not generated. Run 'generate-proto' to generate them. Error: {e}"
    )
    __all__ = []
