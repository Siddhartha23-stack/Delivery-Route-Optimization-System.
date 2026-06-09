"""
REST API for the delivery optimization service.
"""
from flask import Flask, request, jsonify
from dataclasses import asdict
import json
from typing import Optional

from config import OptimizerConfig, OptimizationStrategy
from models import Location, Delivery, Vehicle, TimeWindow, DeliveryPriority
from optimizer import DeliveryOptimizer
from simulation import ScenarioGenerator


def create_app() -> Flask:
    """Create and configure Flask application."""
    app = Flask(__name__)
    
    optimizer = DeliveryOptimizer()
    scenario_gen = ScenarioGenerator()
    
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "healthy", "service": "delivery-route-optimizer"})
    
    @app.route('/optimize', methods=['POST'])
    def optimize_routes():
        """
        Optimize delivery routes.
        
        Request body:
        {
            "depot": {"latitude": float, "longitude": float},
            "deliveries": [
                {
                    "id": str,
                    "latitude": float,
                    "longitude": float,
                    "demand": int,
                    "time_window_start": float,  # hours
                    "time_window_end": float,
                    "service_time": int,  # seconds (optional)
                    "priority": str  # optional: low, normal, high, urgent
                }
            ],
            "vehicles": [
                {
                    "id": str,
                    "capacity": int,
                    "max_distance": int,  # meters
                    "speed_kmh": float
                }
            ],
            "config": {  # optional
                "max_solve_time_seconds": int,
                "strategy": str,  # distance, time, vehicles, balanced
                "allow_dropping": bool
            }
        }
        """
        try:
            data = request.get_json()
            
            # Parse depot
            depot_data = data['depot']
            depot = Location(
                latitude=depot_data['latitude'],
                longitude=depot_data['longitude']
            )
            
            # Parse deliveries
            deliveries = []
            for d in data['deliveries']:
                priority = DeliveryPriority.NORMAL
                if 'priority' in d:
                    priority = DeliveryPriority[d['priority'].upper()]
                
                delivery = Delivery(
                    id=d['id'],
                    location=Location(d['latitude'], d['longitude']),
                    demand=d['demand'],
                    time_window=TimeWindow.from_hours(
                        d['time_window_start'],
                        d['time_window_end']
                    ),
                    service_time=d.get('service_time', 180),
                    priority=priority
                )
                deliveries.append(delivery)
            
            # Parse vehicles
            vehicles = []
            for v in data['vehicles']:
                vehicle = Vehicle(
                    id=v['id'],
                    vehicle_type=v.get('type', 'generic'),
                    capacity=v['capacity'],
                    max_distance=v.get('max_distance', 100000),
                    speed_mps=v.get('speed_kmh', 30) * 1000 / 3600,
                    cost_per_meter=v.get('cost_per_km', 1.0) / 1000,
                    fixed_cost=v.get('fixed_cost', 0),
                    start_location=depot
                )
                vehicles.append(vehicle)
            
            # Parse config
            config = OptimizerConfig()
            if 'config' in data:
                cfg = data['config']
                if 'max_solve_time_seconds' in cfg:
                    config.max_solve_time_seconds = cfg['max_solve_time_seconds']
                if 'strategy' in cfg:
                    config.strategy = OptimizationStrategy(cfg['strategy'])
                if 'allow_dropping' in cfg:
                    config.allow_dropping = cfg['allow_dropping']
            
            # Optimize
            optimizer.config = config
            solution = optimizer.optimize(depot, deliveries, vehicles)
            
            # Format response
            response = {
                "success": True,
                "summary": solution.summary(),
                "routes": []
            }
            
            for route in solution.routes:
                if route.num_stops > 0:
                    route_data = {
                        "vehicle_id": route.vehicle.id,
                        "stops": [],
                        "total_distance_km": round(route.total_distance / 1000, 2),
                        "total_cost": round(route.total_cost, 2),
                        "capacity_utilization": round(route.capacity_utilization * 100, 1)
                    }
                    
                    for stop in route.stops:
                        stop_data = {
                            "delivery_id": stop.delivery.id,
                            "latitude": stop.delivery.location.latitude,
                            "longitude": stop.delivery.location.longitude,
                            "arrival_time": stop.arrival_time,
                            "arrival_formatted": f"{stop.arrival_time // 3600:02d}:{(stop.arrival_time % 3600) // 60:02d}",
                            "time_window": stop.delivery.time_window.format()
                        }
                        route_data["stops"].append(stop_data)
                    
                    response["routes"].append(route_data)
            
            if solution.dropped_deliveries:
                response["dropped"] = [
                    {"id": d.id, "reason": "constraints_infeasible"}
                    for d in solution.dropped_deliveries
                ]
            
            return jsonify(response)
        
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 400
    
    @app.route('/demo/<scenario>', methods=['GET'])
    def run_demo(scenario: str):
        """Run a demo scenario."""
        try:
            if scenario == 'small':
                data = scenario_gen.small_scenario()
            elif scenario == 'medium':
                data = scenario_gen.medium_scenario()
            elif scenario == 'large':
                data = scenario_gen.large_scenario()
            else:
                return jsonify({"error": f"Unknown scenario: {scenario}"}), 400
            
            solution = optimizer.optimize(
                data['depot'],
                data['deliveries'],
                data['vehicles']
            )
            
            return jsonify({
                "scenario": scenario,
                "num_deliveries": len(data['deliveries']),
                "num_vehicles": len(data['vehicles']),
                "summary": solution.summary()
            })
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return app


def run_server(host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
    """Run the Flask development server."""
    app = create_app()
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    run_server(debug=True)
