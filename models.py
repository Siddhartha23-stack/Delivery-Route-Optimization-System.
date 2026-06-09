"""
Data models representing deliveries, vehicles, routes, and solutions.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
import uuid


class DeliveryPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class DeliveryStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclass
class Location:
    """Geographic location with coordinates."""
    latitude: float
    longitude: float
    address: Optional[str] = None
    
    def to_tuple(self) -> tuple[float, float]:
        return (self.latitude, self.longitude)
    
    def __hash__(self):
        return hash((round(self.latitude, 6), round(self.longitude, 6)))


@dataclass
class TimeWindow:
    """Time window for delivery."""
    start: int  # seconds from midnight
    end: int    # seconds from midnight
    
    def __post_init__(self):
        if self.start >= self.end:
            raise ValueError("Start time must be before end time")
    
    @classmethod
    def from_hours(cls, start_hour: float, end_hour: float) -> "TimeWindow":
        return cls(
            start=int(start_hour * 3600),
            end=int(end_hour * 3600)
        )
    
    @property
    def duration_minutes(self) -> float:
        return (self.end - self.start) / 60
    
    def format(self) -> str:
        start_h, start_m = divmod(self.start // 60, 60)
        end_h, end_m = divmod(self.end // 60, 60)
        return f"{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}"


@dataclass
class Delivery:
    """A delivery request."""
    id: str
    location: Location
    demand: int  # units to deliver
    time_window: TimeWindow
    service_time: int = 180  # seconds to complete delivery
    priority: DeliveryPriority = DeliveryPriority.NORMAL
    status: DeliveryStatus = DeliveryStatus.PENDING
    customer_name: Optional[str] = None
    notes: Optional[str] = None
    
    @classmethod
    def create(
        cls,
        latitude: float,
        longitude: float,
        demand: int,
        time_window_start: float,
        time_window_end: float,
        **kwargs
    ) -> "Delivery":
        return cls(
            id=str(uuid.uuid4())[:8],
            location=Location(latitude, longitude),
            demand=demand,
            time_window=TimeWindow.from_hours(time_window_start, time_window_end),
            **kwargs
        )


@dataclass
class Vehicle:
    """A delivery vehicle."""
    id: str
    vehicle_type: str
    capacity: int
    max_distance: int  # meters
    speed_mps: float
    cost_per_meter: float
    fixed_cost: float
    start_location: Location
    end_location: Optional[Location] = None  # None means return to start
    
    @classmethod
    def from_config(
        cls,
        vehicle_id: str,
        vehicle_type,
        start_location: Location
    ) -> "Vehicle":
        from config import VEHICLE_CONFIGS
        config = VEHICLE_CONFIGS[vehicle_type]
        return cls(
            id=vehicle_id,
            vehicle_type=vehicle_type.value,
            capacity=config.capacity,
            max_distance=config.max_distance,
            speed_mps=config.speed_mps,
            cost_per_meter=config.cost_per_km / 1000,
            fixed_cost=config.fixed_cost,
            start_location=start_location
        )


@dataclass
class RouteStop:
    """A stop in a route."""
    delivery: Delivery
    arrival_time: int  # seconds from midnight
    departure_time: int
    cumulative_load: int
    cumulative_distance: float
    
    @property
    def wait_time(self) -> int:
        return max(0, self.delivery.time_window.start - self.arrival_time)
    
    def format_times(self) -> str:
        arr_h, arr_m = divmod(self.arrival_time // 60, 60)
        dep_h, dep_m = divmod(self.departure_time // 60, 60)
        return f"Arrive: {arr_h:02d}:{arr_m:02d}, Depart: {dep_h:02d}:{dep_m:02d}"


@dataclass
class Route:
    """A complete route for a vehicle."""
    vehicle: Vehicle
    stops: list[RouteStop] = field(default_factory=list)
    total_distance: float = 0.0
    total_time: int = 0
    total_load: int = 0
    
    @property
    def num_stops(self) -> int:
        return len(self.stops)
    
    @property
    def total_cost(self) -> float:
        return self.vehicle.fixed_cost + (self.total_distance * self.vehicle.cost_per_meter)
    
    @property
    def capacity_utilization(self) -> float:
        if self.vehicle.capacity == 0:
            return 0.0
        return self.total_load / self.vehicle.capacity
    
    def add_stop(self, stop: RouteStop):
        self.stops.append(stop)
        self.total_load += stop.delivery.demand


@dataclass
class Solution:
    """Complete routing solution."""
    routes: list[Route]
    dropped_deliveries: list[Delivery] = field(default_factory=list)
    solve_time_ms: float = 0.0
    objective_value: float = 0.0
    
    @property
    def total_distance(self) -> float:
        return sum(r.total_distance for r in self.routes)
    
    @property
    def total_cost(self) -> float:
        return sum(r.total_cost for r in self.routes)
    
    @property
    def num_vehicles_used(self) -> int:
        return len([r for r in self.routes if r.num_stops > 0])
    
    @property
    def total_deliveries(self) -> int:
        return sum(r.num_stops for r in self.routes)
    
    def summary(self) -> dict:
        return {
            "vehicles_used": self.num_vehicles_used,
            "total_deliveries": self.total_deliveries,
            "dropped_deliveries": len(self.dropped_deliveries),
            "total_distance_km": round(self.total_distance / 1000, 2),
            "total_cost": round(self.total_cost, 2),
            "solve_time_ms": round(self.solve_time_ms, 2),
            "avg_capacity_utilization": round(
                sum(r.capacity_utilization for r in self.routes if r.num_stops > 0) 
                / max(1, self.num_vehicles_used) * 100, 1
            )
        }
