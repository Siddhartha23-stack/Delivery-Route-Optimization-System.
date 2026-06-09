"""
Simulation tools for generating test data and scenarios.
"""
import random
from typing import Optional
from datetime import datetime
import numpy as np

from config import VehicleType, DepotConfig, VEHICLE_CONFIGS
from models import Delivery, Vehicle, Location, TimeWindow, DeliveryPriority


class DeliverySimulator:
    """Generate realistic delivery scenarios."""
    
    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
    
    def generate_deliveries(
        self,
        num_deliveries: int,
        center_lat: float,
        center_lon: float,
        radius_km: float = 10,
        time_range: tuple = (8, 20),  # 8 AM to 8 PM
        demand_range: tuple = (1, 5),
        cluster_factor: float = 0.3
    ) -> list[Delivery]:
        """
        Generate random deliveries with realistic distributions.
        
        Args:
            num_deliveries: Number of deliveries to generate
            center_lat, center_lon: Center point for delivery area
            radius_km: Radius of delivery area
            time_range: Operating hours (start, end)
            demand_range: Min and max demand per delivery
            cluster_factor: How clustered deliveries are (0-1)
        """
        deliveries = []
        
        # Generate cluster centers
        num_clusters = max(1, int(num_deliveries * cluster_factor / 5))
        cluster_centers = []
        for _ in range(num_clusters):
            lat, lon = self._random_point_in_radius(
                center_lat, center_lon, radius_km * 0.7
            )
            cluster_centers.append((lat, lon))
        
        for i in range(num_deliveries):
            # Decide if this delivery is in a cluster
            if random.random() < cluster_factor and cluster_centers:
                cluster = random.choice(cluster_centers)
                lat, lon = self._random_point_in_radius(
                    cluster[0], cluster[1], radius_km * 0.15
                )
            else:
                lat, lon = self._random_point_in_radius(
                    center_lat, center_lon, radius_km
                )
            
            # Generate time window
            tw_start, tw_end = self._generate_time_window(time_range)
            
            # Generate demand with realistic distribution
            demand = self._generate_demand(demand_range)
            
            # Assign priority
            priority = self._generate_priority()
            
            delivery = Delivery.create(
                latitude=lat,
                longitude=lon,
                demand=demand,
                time_window_start=tw_start,
                time_window_end=tw_end,
                priority=priority,
                customer_name=f"Customer_{i+1}"
            )
            
            deliveries.append(delivery)
        
        return deliveries
    
    def _random_point_in_radius(
        self, lat: float, lon: float, radius_km: float
    ) -> tuple[float, float]:
        """Generate random point within radius."""
        # Convert radius to degrees (approximate)
        radius_deg = radius_km / 111
        
        # Random angle and distance
        angle = random.uniform(0, 2 * np.pi)
        distance = random.uniform(0, radius_deg)
        
        new_lat = lat + distance * np.cos(angle)
        new_lon = lon + distance * np.sin(angle) / np.cos(np.radians(lat))
        
        return round(new_lat, 6), round(new_lon, 6)
    
    def _generate_time_window(
        self, time_range: tuple, window_duration_hours: float = 2
    ) -> tuple[float, float]:
        """Generate realistic time window."""
        start_hour = random.uniform(time_range[0], time_range[1] - window_duration_hours)
        
        # Vary window duration
        duration = random.uniform(1, 4)
        end_hour = min(start_hour + duration, time_range[1])
        
        return round(start_hour, 2), round(end_hour, 2)
    
    def _generate_demand(self, demand_range: tuple) -> int:
        """Generate demand with log-normal distribution."""
        mean = (demand_range[0] + demand_range[1]) / 2
        demand = int(np.random.lognormal(np.log(mean), 0.5))
        return max(demand_range[0], min(demand, demand_range[1]))
    
    def _generate_priority(self) -> DeliveryPriority:
        """Generate priority with realistic distribution."""
        r = random.random()
        if r < 0.05:
            return DeliveryPriority.URGENT
        elif r < 0.20:
            return DeliveryPriority.HIGH
        elif r < 0.70:
            return DeliveryPriority.NORMAL
        else:
            return DeliveryPriority.LOW


class FleetGenerator:
    """Generate vehicle fleets."""
    
    def generate_fleet(
        self,
        depot: Location,
        vehicle_counts: dict[VehicleType, int]
    ) -> list[Vehicle]:
        """
        Generate a fleet of vehicles.
        
        Args:
            depot: Starting location for vehicles
            vehicle_counts: Dict mapping vehicle type to count
        """
        vehicles = []
        
        for vehicle_type, count in vehicle_counts.items():
            for i in range(count):
                vehicle = Vehicle.from_config(
                    vehicle_id=f"{vehicle_type.value}_{i+1}",
                    vehicle_type=vehicle_type,
                    start_location=depot
                )
                vehicles.append(vehicle)
        
        return vehicles
    
    def generate_mixed_fleet(
        self,
        depot: Location,
        total_capacity_needed: int,
        prefer_larger: bool = False
    ) -> list[Vehicle]:
        """
        Generate an optimally sized fleet based on capacity needs.
        """
        vehicles = []
        remaining_capacity = total_capacity_needed * 1.3  # 30% buffer
        
        # Sort vehicle types by capacity
        sorted_types = sorted(
            VehicleType,
            key=lambda t: VEHICLE_CONFIGS[t].capacity,
            reverse=prefer_larger
        )
        
        vehicle_num = 1
        while remaining_capacity > 0:
            # Select appropriate vehicle type
            for vtype in sorted_types:
                config = VEHICLE_CONFIGS[vtype]
                if config.capacity <= remaining_capacity or remaining_capacity < VEHICLE_CONFIGS[sorted_types[-1]].capacity:
                    vehicle = Vehicle.from_config(
                        vehicle_id=f"{vtype.value}_{vehicle_num}",
                        vehicle_type=vtype,
                        start_location=depot
                    )
                    vehicles.append(vehicle)
                    remaining_capacity -= config.capacity
                    vehicle_num += 1
                    break
        
        return vehicles


class ScenarioGenerator:
    """Generate complete test scenarios."""
    
    def __init__(self, seed: Optional[int] = None):
        self.delivery_sim = DeliverySimulator(seed)
        self.fleet_gen = FleetGenerator()
    
    def generate_scenario(
        self,
        name: str,
        depot_config: DepotConfig,
        num_deliveries: int,
        vehicle_types: dict[VehicleType, int],
        **delivery_kwargs
    ) -> dict:
        """Generate a complete scenario."""
        depot = Location(
            latitude=depot_config.latitude,
            longitude=depot_config.longitude,
            address=depot_config.name
        )
        
        deliveries = self.delivery_sim.generate_deliveries(
            num_deliveries=num_deliveries,
            center_lat=depot.latitude,
            center_lon=depot.longitude,
            **delivery_kwargs
        )
        
        vehicles = self.fleet_gen.generate_fleet(depot, vehicle_types)
        
        return {
            "name": name,
            "depot": depot,
            "deliveries": deliveries,
            "vehicles": vehicles
        }
    
    def small_scenario(self) -> dict:
        """Quick test scenario."""
        return self.generate_scenario(
            name="Small Test",
            depot_config=DepotConfig(28.6139, 77.2090, "Delhi Depot"),
            num_deliveries=15,
            vehicle_types={VehicleType.SCOOTER: 3},
            radius_km=5
        )
    
    def medium_scenario(self) -> dict:
        """Medium-sized scenario."""
        return self.generate_scenario(
            name="Medium Test",
            depot_config=DepotConfig(28.6139, 77.2090, "Delhi Depot"),
            num_deliveries=50,
            vehicle_types={
                VehicleType.BIKE: 2,
                VehicleType.SCOOTER: 4,
                VehicleType.VAN: 2
            },
            radius_km=12
        )
    
    def large_scenario(self) -> dict:
        """Large, complex scenario."""
        return self.generate_scenario(
            name="Large Test",
            depot_config=DepotConfig(28.6139, 77.2090, "Delhi Depot"),
            num_deliveries=150,
            vehicle_types={
                VehicleType.BIKE: 5,
                VehicleType.SCOOTER: 10,
                VehicleType.VAN: 5,
                VehicleType.TRUCK: 2
            },
            radius_km=20,
            cluster_factor=0.4
        )
