"""
Configuration constants and settings for the delivery optimization system.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VehicleType(Enum):
    BIKE = "bike"
    SCOOTER = "scooter"
    VAN = "van"
    TRUCK = "truck"


class OptimizationStrategy(Enum):
    MINIMIZE_DISTANCE = "distance"
    MINIMIZE_TIME = "time"
    MINIMIZE_VEHICLES = "vehicles"
    BALANCED = "balanced"


@dataclass
class VehicleConfig:
    """Configuration for different vehicle types."""
    capacity: int  # in units
    max_distance: int  # in meters
    speed_kmh: float  # average speed
    cost_per_km: float
    fixed_cost: float
    
    @property
    def speed_mps(self) -> float:
        return self.speed_kmh * 1000 / 3600


VEHICLE_CONFIGS = {
    VehicleType.BIKE: VehicleConfig(
        capacity=5, max_distance=15000, speed_kmh=15,
        cost_per_km=0.5, fixed_cost=10
    ),
    VehicleType.SCOOTER: VehicleConfig(
        capacity=10, max_distance=30000, speed_kmh=25,
        cost_per_km=1.0, fixed_cost=20
    ),
    VehicleType.VAN: VehicleConfig(
        capacity=50, max_distance=100000, speed_kmh=40,
        cost_per_km=2.5, fixed_cost=50
    ),
    VehicleType.TRUCK: VehicleConfig(
        capacity=200, max_distance=300000, speed_kmh=35,
        cost_per_km=4.0, fixed_cost=100
    ),
}


@dataclass
class OptimizerConfig:
    """Configuration for the route optimizer."""
    max_solve_time_seconds: int = 30
    strategy: OptimizationStrategy = OptimizationStrategy.BALANCED
    allow_dropping: bool = False
    drop_penalty: int = 100000
    time_window_slack: int = 300  # 5 minutes slack
    service_time_default: int = 180  # 3 minutes per stop
    
    # Local search metaheuristic options
    first_solution_strategy: str = "PATH_CHEAPEST_ARC"
    local_search_metaheuristic: str = "GUIDED_LOCAL_SEARCH"


@dataclass
class DepotConfig:
    """Depot configuration."""
    latitude: float
    longitude: float
    name: str = "Central Depot"
    open_time: int = 0  # seconds from midnight
    close_time: int = 86400  # 24 hours


# Default depot (example: central location)
DEFAULT_DEPOT = DepotConfig(
    latitude=28.6139,  # New Delhi
    longitude=77.2090,
    name="Central Warehouse"
)
