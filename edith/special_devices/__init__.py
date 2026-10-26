"""Special-device adapters with a simulator-first vehicle contract."""

from .vehicle import (
    AuthorizedOEMVehicleAdapter,
    VehicleAdapter,
    VehicleAdapterRegistry,
    VehicleSimulatorAdapter,
)

__all__ = [
    "AuthorizedOEMVehicleAdapter",
    "VehicleAdapter",
    "VehicleAdapterRegistry",
    "VehicleSimulatorAdapter",
]
