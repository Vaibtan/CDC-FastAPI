"""
WalStream Protocol Buffers Package.

Import from versioned subpackages:
    from walstream_proto.v1 import ChangeRecord, ReplayRequest

Or use the default exports (v1):
    from walstream_proto import ChangeRecord, ReplayRequest
"""

__version__ = "1.0.0"

# Re-export v1 as default for convenience
try:
    from walstream_proto.v1 import (
        ChangeRecord,
        ReplayRequest,
        ReplayResponse,
        ReplayerStub,
        ReplayerServicer,
        add_ReplayerServicer_to_server,
        HealthRequest,
        HealthResponse,
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
except ImportError:
    # Proto files not yet generated
    __all__ = []
