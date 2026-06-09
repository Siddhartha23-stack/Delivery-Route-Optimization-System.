"""
Visualization tools for routes and solutions.
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import LineCollection
import numpy as np
from typing import Optional
import colorsys

from models import Solution, Route, Location, Delivery


class RouteVisualizer:
    """Static route visualization using matplotlib."""
    
    COLORS = [
        '#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
        '#911eb4', '#46f0f0', '#f032e6', '#bcf60c', '#fabebe',
        '#008080', '#e6beff', '#9a6324', '#fffac8', '#800000',
        '#aaffc3', '#808000', '#ffd8b1', '#000075', '#808080'
    ]
    
    def __init__(self, figsize: tuple = (14, 10)):
        self.figsize = figsize
    
    def plot_solution(
        self,
        solution: Solution,
        depot: Location,
        title: str = "Optimized Delivery Routes",
        show_time_windows: bool = True,
        save_path: Optional[str] = None
    ):
        """
        Plot complete solution with all routes.
        """
        fig, axes = plt.subplots(1, 2, figsize=(self.figsize[0] * 1.2, self.figsize[1]))
        
        # Left: Route map
        ax_map = axes[0]
        self._plot_routes_on_ax(ax_map, solution, depot)
        ax_map.set_title(title, fontsize=14, fontweight='bold')
        
        # Right: Statistics and timeline
        ax_stats = axes[1]
        self._plot_statistics(ax_stats, solution)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        
        plt.show()
    
    def _plot_routes_on_ax(self, ax, solution: Solution, depot: Location):
        """Plot routes on matplotlib axes."""
        # Plot depot
        ax.scatter(
            depot.longitude, depot.latitude,
            c='black', s=200, marker='s', zorder=5,
            label='Depot', edgecolors='white', linewidth=2
        )
        
        # Plot each route
        for i, route in enumerate(solution.routes):
            if not route.stops:
                continue
            
            color = self.COLORS[i % len(self.COLORS)]
            
            # Build path: depot -> stops -> depot
            lats = [depot.latitude]
            lons = [depot.longitude]
            
            for stop in route.stops:
                lats.append(stop.delivery.location.latitude)
                lons.append(stop.delivery.location.longitude)
            
            lats.append(depot.latitude)
            lons.append(depot.longitude)
            
            # Plot route line
            ax.plot(
                lons, lats, color=color, linewidth=2, alpha=0.7,
                label=f'Vehicle {route.vehicle.id} ({route.num_stops} stops)'
            )
            
            # Plot arrows for direction
            for j in range(len(lons) - 1):
                mid_lon = (lons[j] + lons[j+1]) / 2
                mid_lat = (lats[j] + lats[j+1]) / 2
                dx = lons[j+1] - lons[j]
                dy = lats[j+1] - lats[j]
                
                if abs(dx) > 0.0001 or abs(dy) > 0.0001:
                    ax.annotate(
                        '', xy=(mid_lon + dx*0.1, mid_lat + dy*0.1),
                        xytext=(mid_lon, mid_lat),
                        arrowprops=dict(arrowstyle='->', color=color, lw=1.5)
                    )
            
            # Plot delivery points
            for j, stop in enumerate(route.stops):
                loc = stop.delivery.location
                ax.scatter(
                    loc.longitude, loc.latitude,
                    c=color, s=80, zorder=4, edgecolors='white', linewidth=1
                )
                ax.annotate(
                    str(j + 1), (loc.longitude, loc.latitude),
                    fontsize=8, ha='center', va='center',
                    color='white', fontweight='bold'
                )
        
        # Plot dropped deliveries
        for delivery in solution.dropped_deliveries:
            ax.scatter(
                delivery.location.longitude, delivery.location.latitude,
                c='red', s=100, marker='x', zorder=3, linewidth=2
            )
        
        ax.set_xlabel('Longitude')
        ax.set_ylabel('Latitude')
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)
    
    def _plot_statistics(self, ax, solution: Solution):
        """Plot solution statistics."""
        ax.axis('off')
        
        summary = solution.summary()
        
        stats_text = f"""
        SOLUTION SUMMARY
        ════════════════════════════
        
        Vehicles Used:     {summary['vehicles_used']}
        Total Deliveries:  {summary['total_deliveries']}
        Dropped Orders:    {summary['dropped_deliveries']}
        
        Total Distance:    {summary['total_distance_km']} km
        Total Cost:        ${summary['total_cost']:.2f}
        
        Avg Capacity Use:  {summary['avg_capacity_utilization']}%
        Solve Time:        {summary['solve_time_ms']:.1f} ms
        
        ════════════════════════════
        
        ROUTE DETAILS
        """
        
        for i, route in enumerate(solution.routes):
            if route.num_stops > 0:
                stats_text += f"""
        Vehicle {route.vehicle.id}:
          • Stops: {route.num_stops}
          • Distance: {route.total_distance/1000:.1f} km
          • Load: {route.total_load}/{route.vehicle.capacity}
          • Cost: ${route.total_cost:.2f}
        """
        
        ax.text(
            0.1, 0.95, stats_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment='top',
            fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8)
        )
    
    def plot_timeline(
        self,
        solution: Solution,
        save_path: Optional[str] = None
    ):
        """Plot Gantt-style timeline of deliveries."""
        fig, ax = plt.subplots(figsize=(14, 6))
        
        y_positions = []
        y_labels = []
        
        for i, route in enumerate(solution.routes):
            if not route.stops:
                continue
            
            color = self.COLORS[i % len(self.COLORS)]
            y = i
            y_positions.append(y)
            y_labels.append(f"Vehicle {route.vehicle.id}")
            
            for stop in route.stops:
                tw = stop.delivery.time_window
                
                # Time window bar (light)
                ax.barh(
                    y, (tw.end - tw.start) / 3600, left=tw.start / 3600,
                    height=0.4, color=color, alpha=0.2
                )
                
                # Actual service bar (solid)
                service_duration = stop.delivery.service_time / 3600
                ax.barh(
                    y, service_duration, left=stop.arrival_time / 3600,
                    height=0.4, color=color, alpha=0.8
                )
                
                # Wait time (if any)
                if stop.wait_time > 0:
                    ax.barh(
                        y, stop.wait_time / 3600, 
                        left=(stop.arrival_time - stop.wait_time) / 3600,
                        height=0.4, color='gray', alpha=0.3, hatch='//'
                    )
        
        ax.set_yticks(y_positions)
        ax.set_yticklabels(y_labels)
        ax.set_xlabel('Time (hours from midnight)')
        ax.set_title('Delivery Timeline')
        ax.grid(True, axis='x', alpha=0.3)
        
        # Add legend
        legend_elements = [
            mpatches.Patch(alpha=0.2, label='Time Window'),
            mpatches.Patch(alpha=0.8, label='Service Time'),
            mpatches.Patch(color='gray', alpha=0.3, hatch='//', label='Wait Time')
        ]
        ax.legend(handles=legend_elements, loc='upper right')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        
        plt.show()


class InteractiveMapVisualizer:
    """Interactive map visualization using Folium."""
    
    def __init__(self):
        try:
            import folium
            self.folium = folium
        except ImportError:
            raise ImportError("Folium is required. Install with: pip install folium")
    
    def create_map(
        self,
        solution: Solution,
        depot: Location,
        save_path: str = "route_map.html"
    ):
        """Create interactive HTML map."""
        # Center map on depot
        m = self.folium.Map(
            location=[depot.latitude, depot.longitude],
            zoom_start=12,
            tiles='cartodbpositron'
        )
        
        # Add depot marker
        self.folium.Marker(
            [depot.latitude, depot.longitude],
            popup='Depot',
            icon=self.folium.Icon(color='black', icon='home', prefix='fa')
        ).add_to(m)
        
        colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred',
                  'lightred', 'beige', 'darkblue', 'darkgreen']
        
        for i, route in enumerate(solution.routes):
            if not route.stops:
                continue
            
            color = colors[i % len(colors)]
            
            # Build path coordinates
            path = [[depot.latitude, depot.longitude]]
            for stop in route.stops:
                path.append([
                    stop.delivery.location.latitude,
                    stop.delivery.location.longitude
                ])
            path.append([depot.latitude, depot.longitude])
            
            # Draw route line
            self.folium.PolyLine(
                path, weight=3, color=color, opacity=0.8,
                popup=f"Vehicle {route.vehicle.id}"
            ).add_to(m)
            
            # Add delivery markers
            for j, stop in enumerate(route.stops):
                loc = stop.delivery.location
                popup_text = f"""
                <b>Stop {j+1}</b><br>
                Delivery: {stop.delivery.id}<br>
                Time Window: {stop.delivery.time_window.format()}<br>
                Arrival: {stop.arrival_time // 3600:02d}:{(stop.arrival_time % 3600) // 60:02d}<br>
                Demand: {stop.delivery.demand}
                """
                
                self.folium.CircleMarker(
                    [loc.latitude, loc.longitude],
                    radius=8,
                    color=color,
                    fill=True,
                    popup=popup_text
                ).add_to(m)
        
        # Add dropped deliveries
        for delivery in solution.dropped_deliveries:
            self.folium.Marker(
                [delivery.location.latitude, delivery.location.longitude],
                popup=f'DROPPED: {delivery.id}',
                icon=self.folium.Icon(color='red', icon='times', prefix='fa')
            ).add_to(m)
        
        m.save(save_path)
        print(f"Map saved to {save_path}")
        
        return m
