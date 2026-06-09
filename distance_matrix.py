"""
Distance and time matrix computation with multiple strategies.
"""
import numpy as np
from math import radians, sin, cos, sqrt, atan2
from typing import Optional
from abc import ABC, abstractmethod
import requests
from functools import lru_cache

from models import Location, Delivery, Vehicle


class DistanceCalculator(ABC):
    """Abstract base class for distance calculation."""
    
    @abstractmethod
    def calculate_distance(self, origin: Location, destination: Location) -> float:
        """Calculate distance in meters."""
        pass
    
    @abstractmethod
    def calculate_duration(self, origin: Location, destination: Location, speed_mps: float) -> int:
        """Calculate travel time in seconds."""
        pass
    
    def build_matrix(
        self,
        locations: list[Location],
        speed_mps: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Build distance and time matrices."""
        n = len(locations)
        distance_matrix = np.zeros((n, n), dtype=np.int64)
        time_matrix = np.zeros((n, n), dtype=np.int64)
        
        for i in range(n):
            for j in range(n):
                if i != j:
                    dist = self.calculate_distance(locations[i], locations[j])
                    duration = self.calculate_duration(locations[i], locations[j], speed_mps)
                    distance_matrix[i][j] = int(dist)
                    time_matrix[i][j] = int(duration)
        
        return distance_matrix, time_matrix


class HaversineCalculator(DistanceCalculator):
    """Calculate distances using Haversine formula (great-circle distance)."""
    
    EARTH_RADIUS_METERS = 6_371_000
    
    def calculate_distance(self, origin: Location, destination: Location) -> float:
        lat1, lon1 = radians(origin.latitude), radians(origin.longitude)
        lat2, lon2 = radians(destination.latitude), radians(destination.longitude)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        
        return self.EARTH_RADIUS_METERS * c
    
    def calculate_duration(self, origin: Location, destination: Location, speed_mps: float) -> int:
        distance = self.calculate_distance(origin, destination)
        return int(distance / speed_mps) if speed_mps > 0 else 0


class ManhattanCalculator(DistanceCalculator):
    """
    Manhattan distance approximation for urban grid-based routing.
    More realistic for cities with grid street layouts.
    """
    
    METERS_PER_DEGREE_LAT = 111_320
    
    def calculate_distance(self, origin: Location, destination: Location) -> float:
        lat_diff = abs(origin.latitude - destination.latitude)
        lon_diff = abs(origin.longitude - destination.longitude)
        
        avg_lat = radians((origin.latitude + destination.latitude) / 2)
        meters_per_degree_lon = self.METERS_PER_DEGREE_LAT * cos(avg_lat)
        
        lat_dist = lat_diff * self.METERS_PER_DEGREE_LAT
        lon_dist = lon_diff * meters_per_degree_lon
        
        # Add 20% factor for realistic urban routing
        return (lat_dist + lon_dist) * 1.2
    
    def calculate_duration(self, origin: Location, destination: Location, speed_mps: float) -> int:
        distance = self.calculate_distance(origin, destination)
        # Add traffic factor
        traffic_factor = 1.3
        return int((distance / speed_mps) * traffic_factor) if speed_mps > 0 else 0


class OSRMCalculator(DistanceCalculator):
    """
    Use OSRM (Open Source Routing Machine) for real road distances.
    Requires OSRM server running locally or using public demo server.
    """
    
    def __init__(self, base_url: str = "[router.project-osrm.org](http://router.project-osrm.org)"):
        self.base_url = base_url
        self._cache = {}
    
    def calculate_distance(self, origin: Location, destination: Location) -> float:
        result = self._get_route(origin, destination)
        return result.get("distance", 0)
    
    def calculate_duration(self, origin: Location, destination: Location, speed_mps: float) -> int:
        result = self._get_route(origin, destination)
        return int(result.get("duration", 0))
    
    @lru_cache(maxsize=10000)
    def _get_route(self, origin: Location, destination: Location) -> dict:
        try:
            url = (
                f"{self.base_url}/route/v1/driving/"
                f"{origin.longitude},{origin.latitude};"
                f"{destination.longitude},{destination.latitude}"
                f"?overview=false"
            )
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "Ok" and data.get("routes"):
                    route = data["routes"][0]
                    return {
                        "distance": route["distance"],
                        "duration": route["duration"]
                    }
        except Exception:
            pass
        
        # Fallback to Haversine
        fallback = HaversineCalculator()
        return {
            "distance": fallback.calculate_distance(origin, destination),
            "duration": fallback.calculate_duration(origin, destination, 10)
        }


class DistanceMatrixBuilder:
    """
    Build distance and time matrices for the optimization problem.
    Supports caching and multiple calculation strategies.
    """
    
    def __init__(self, calculator: Optional[DistanceCalculator] = None):
        self.calculator = calculator or ManhattanCalculator()
    
    def build(
        self,
        depot: Location,
        deliveries: list[Delivery],
        vehicles: list[Vehicle]
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Build matrices with depot at index 0.
        
        Returns:
            (distance_matrix, time_matrix) where index 0 is depot
        """
        # Collect all locations: depot first, then delivery locations
        locations = [depot] + [d.location for d in deliveries]
        
        # Use average speed across vehicles for time estimation
        avg_speed = sum(v.speed_mps for v in vehicles) / len(vehicles) if vehicles else 10
        
        return self.calculator.build_matrix(locations, avg_speed)
    
    def build_asymmetric(
        self,
        depot: Location,
        deliveries: list[Delivery],
        vehicles: list[Vehicle],
        traffic_matrix: Optional[np.ndarray] = None
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Build asymmetric matrices accounting for one-way streets and traffic patterns.
        """
        distance_matrix, time_matrix = self.build(depot, deliveries, vehicles)
        
        if traffic_matrix is not None:
            time_matrix = (time_matrix * traffic_matrix).astype(np.int64)
        
        return distance_matrix, time_matrix
