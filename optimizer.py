"""
Core optimization engine using Google OR-Tools.
Solves CVRPTW (Capacitated Vehicle Routing Problem with Time Windows).
"""
import time
from typing import Optional
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import numpy as np

from config import OptimizerConfig, OptimizationStrategy
from models import (
    Delivery, Vehicle, Route, RouteStop, Solution, Location, TimeWindow
)
from distance_matrix import DistanceMatrixBuilder, ManhattanCalculator


class DeliveryOptimizer:
    """
    Main optimization engine for vehicle routing problems.
    
    Features:
    - Capacity constraints
    - Time windows
    - Multiple vehicle types
    - Configurable optimization strategies
    - Optional delivery dropping
    """
    
    def __init__(self, config: Optional[OptimizerConfig] = None):
        self.config = config or OptimizerConfig()
        self.matrix_builder = DistanceMatrixBuilder(ManhattanCalculator())
    
    def optimize(
        self,
        depot: Location,
        deliveries: list[Delivery],
        vehicles: list[Vehicle]
    ) -> Solution:
        """
        Find optimal routes for all deliveries.
        
        Args:
            depot: Starting/ending location for all vehicles
            deliveries: List of delivery requests
            vehicles: Available vehicles
            
        Returns:
            Solution with optimized routes
        """
        if not deliveries:
            return Solution(routes=[])
        
        if not vehicles:
            return Solution(routes=[], dropped_deliveries=deliveries)
        
        start_time = time.time()
        
        # Build distance and time matrices
        distance_matrix, time_matrix = self.matrix_builder.build(
            depot, deliveries, vehicles
        )
        
        # Create routing index manager
        num_locations = len(deliveries) + 1  # +1 for depot
        num_vehicles = len(vehicles)
        depot_index = 0
        
        manager = pywrapcp.RoutingIndexManager(
            num_locations, num_vehicles, depot_index
        )
        
        # Create routing model
        routing = pywrapcp.RoutingModel(manager)
        
        # Distance callback
        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(distance_matrix[from_node][to_node])
        
        distance_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(distance_callback_index)
        
        # Add distance dimension
        max_distance = max(v.max_distance for v in vehicles)
        routing.AddDimension(
            distance_callback_index,
            0,  # no slack
            max_distance,
            True,  # start cumul to zero
            "Distance"
        )
        
        # Time callback
        def time_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            travel_time = int(time_matrix[from_node][to_node])
            
            # Add service time at destination (except depot)
            if to_node > 0:
                travel_time += deliveries[to_node - 1].service_time
            
            return travel_time
        
        time_callback_index = routing.RegisterTransitCallback(time_callback)
        
        # Add time dimension with time windows
        max_time = 24 * 3600  # 24 hours in seconds
        routing.AddDimension(
            time_callback_index,
            self.config.time_window_slack,  # waiting time slack
            max_time,
            False,  # don't force start cumul to zero
            "Time"
        )
        time_dimension = routing.GetDimensionOrDie("Time")
        
        # Set time windows for each location
        for i, delivery in enumerate(deliveries):
            index = manager.NodeToIndex(i + 1)  # +1 because depot is 0
            time_dimension.CumulVar(index).SetRange(
                delivery.time_window.start,
                delivery.time_window.end
            )
        
        # Set depot time window (full day)
        for vehicle_id in range(num_vehicles):
            start_index = routing.Start(vehicle_id)
            end_index = routing.End(vehicle_id)
            time_dimension.CumulVar(start_index).SetRange(0, max_time)
            time_dimension.CumulVar(end_index).SetRange(0, max_time)
        
        # Add capacity dimension
        def demand_callback(from_index):
            from_node = manager.IndexToNode(from_index)
            if from_node == 0:
                return 0
            return deliveries[from_node - 1].demand
        
        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        
        vehicle_capacities = [v.capacity for v in vehicles]
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,  # no slack
            vehicle_capacities,
            True,  # start cumul to zero
            "Capacity"
        )
        
        # Handle undeliverable orders
        if self.config.allow_dropping:
            for i in range(len(deliveries)):
                index = manager.NodeToIndex(i + 1)
                # Penalty based on priority
                priority_multiplier = deliveries[i].priority.value
                penalty = self.config.drop_penalty * priority_multiplier
                routing.AddDisjunction([index], penalty)
        
        # Set objective based on strategy
        self._set_objective(routing, time_dimension, vehicles, manager)
        
        # Configure search parameters
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = getattr(
            routing_enums_pb2.FirstSolutionStrategy,
            self.config.first_solution_strategy
        )
        search_parameters.local_search_metaheuristic = getattr(
            routing_enums_pb2.LocalSearchMetaheuristic,
            self.config.local_search_metaheuristic
        )
        search_parameters.time_limit.seconds = self.config.max_solve_time_seconds
        search_parameters.log_search = False
        
        # Solve
        assignment = routing.SolveWithParameters(search_parameters)
        
        solve_time = (time.time() - start_time) * 1000
        
        if not assignment:
            return Solution(
                routes=[],
                dropped_deliveries=deliveries,
                solve_time_ms=solve_time
            )
        
        # Extract solution
        return self._extract_solution(
            routing, manager, assignment, depot, deliveries, vehicles,
            distance_matrix, time_dimension, solve_time
        )
    
    def _set_objective(
        self,
        routing: pywrapcp.RoutingModel,
        time_dimension,
        vehicles: list[Vehicle],
        manager
    ):
        """Configure optimization objective based on strategy."""
        strategy = self.config.strategy
        
        if strategy == OptimizationStrategy.MINIMIZE_TIME:
            for vehicle_id in range(len(vehicles)):
                end_index = routing.End(vehicle_id)
                time_dimension.SetSpanCostCoefficientForVehicle(1, vehicle_id)
        
        elif strategy == OptimizationStrategy.MINIMIZE_VEHICLES:
            for vehicle_id in range(len(vehicles)):
                routing.SetFixedCostOfVehicle(1000, vehicle_id)
        
        elif strategy == OptimizationStrategy.BALANCED:
            for vehicle_id in range(len(vehicles)):
                routing.SetFixedCostOfVehicle(
                    int(vehicles[vehicle_id].fixed_cost * 10),
                    vehicle_id
                )
    
    def _extract_solution(
        self,
        routing: pywrapcp.RoutingModel,
        manager: pywrapcp.RoutingIndexManager,
        assignment,
        depot: Location,
        deliveries: list[Delivery],
        vehicles: list[Vehicle],
        distance_matrix: np.ndarray,
        time_dimension,
        solve_time: float
    ) -> Solution:
        """Extract routes from OR-Tools solution."""
        routes = []
        dropped = []
        
        # Track which deliveries are served
        served = set()
        
        for vehicle_id in range(len(vehicles)):
            route = Route(vehicle=vehicles[vehicle_id])
            index = routing.Start(vehicle_id)
            
            cumulative_distance = 0.0
            prev_node = 0
            
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                
                if node > 0:  # Not depot
                    delivery = deliveries[node - 1]
                    served.add(node - 1)
                    
                    time_var = time_dimension.CumulVar(index)
                    arrival = assignment.Value(time_var)
                    departure = arrival + delivery.service_time
                    
                    cumulative_distance += distance_matrix[prev_node][node]
                    
                    stop = RouteStop(
                        delivery=delivery,
                        arrival_time=arrival,
                        departure_time=departure,
                        cumulative_load=route.total_load + delivery.demand,
                        cumulative_distance=cumulative_distance
                    )
                    route.add_stop(stop)
                    prev_node = node
                
                index = assignment.Value(routing.NextVar(index))
            
            # Add return to depot distance
            if route.stops:
                last_node = manager.IndexToNode(
                    manager.NodeToIndex(prev_node) if prev_node > 0 else 0
                )
                cumulative_distance += distance_matrix[prev_node][0]
            
            route.total_distance = cumulative_distance
            
            # Calculate total time
            if route.stops:
                end_time_var = time_dimension.CumulVar(routing.End(vehicle_id))
                route.total_time = assignment.Value(end_time_var)
            
            routes.append(route)
        
        # Identify dropped deliveries
        for i, delivery in enumerate(deliveries):
            if i not in served:
                dropped.append(delivery)
        
        return Solution(
            routes=routes,
            dropped_deliveries=dropped,
            solve_time_ms=solve_time,
            objective_value=assignment.ObjectiveValue()
        )


class MultiDepotOptimizer(DeliveryOptimizer):
    """
    Extended optimizer supporting multiple depots.
    Each vehicle can start from a different location.
    """
    
    def optimize_multi_depot(
        self,
        depots: list[Location],
        deliveries: list[Delivery],
        vehicles: list[Vehicle],
        vehicle_depot_assignments: dict[str, int]
    ) -> Solution:
        """
        Optimize with multiple depots.
        
        Args:
            depots: List of depot locations
            deliveries: Delivery requests
            vehicles: Available vehicles
            vehicle_depot_assignments: Maps vehicle ID to depot index
        """
        # For simplicity, partition deliveries by nearest depot
        # and solve separately, then merge solutions
        
        # Cluster deliveries to depots
        from distance_matrix import HaversineCalculator
        calc = HaversineCalculator()
        
        depot_deliveries = {i: [] for i in range(len(depots))}
        for delivery in deliveries:
            distances = [
                calc.calculate_distance(delivery.location, depot)
                for depot in depots
            ]
            nearest = distances.index(min(distances))
            depot_deliveries[nearest].append(delivery)
        
        # Solve for each depot
        all_routes = []
        all_dropped = []
        total_time = 0
        
        for depot_idx, depot in enumerate(depots):
            depot_vehicles = [
                v for v in vehicles
                if vehicle_depot_assignments.get(v.id, 0) == depot_idx
            ]
            
            if depot_vehicles and depot_deliveries[depot_idx]:
                solution = self.optimize(
                    depot, depot_deliveries[depot_idx], depot_vehicles
                )
                all_routes.extend(solution.routes)
                all_dropped.extend(solution.dropped_deliveries)
                total_time += solution.solve_time_ms
        
        return Solution(
            routes=all_routes,
            dropped_deliveries=all_dropped,
            solve_time_ms=total_time
        )
