import osmnx as ox
import networkx as nx
import random
import time
import webbrowser
import json

# -------------------------------
# Step 1: Locations & Configuration
# -------------------------------

customer_location = (17.4000, 78.5000)

shops = {
    "Pizza Shop": (17.3900, 78.4800),
    "Burger Shop": (17.3855, 78.4950),
    "Biryani Shop": (17.4100, 78.5100)
}

delivery_partner = (17.3800, 78.4700)

# -------------------------------
# Step 2: Select Shop
# -------------------------------

print("\nAvailable Shops:")
for i, shop in enumerate(shops.keys(), 1):
    print(f"{i}. {shop}")

# To prevent hanging in a background execution if the user doesn't interact, 
# we can just default to Pizza Shop if no input is provided, but since user runs this interactively:
try:
    choice = int(input("\nSelect shop (1-3): ")) - 1
except:
    print("Invalid input, defaulting to Pizza Shop.")
    choice = 0

shop_name = list(shops.keys())[choice]
shop_location = shops[shop_name]

print(f"\n🛒 Order placed at {shop_name}")

# -------------------------------
# Step 3: Load Map Graph
# -------------------------------

print("\n📡 Loading map graph... This might take a few moments.")
# Load the drive network within 3km of the customer
G = ox.graph_from_point(customer_location, dist=3000, network_type='drive')

def get_node(location):
    return ox.distance.nearest_nodes(G, location[1], location[0])

partner_node = get_node(delivery_partner)
shop_node = get_node(shop_location)
customer_node = get_node(customer_location)

# -------------------------------
# Step 4: Initialize Dynamic Traffic
# -------------------------------

# Assign base speed to all edges
for u, v, k, data in G.edges(keys=True, data=True):
    data['base_speed'] = 40.0  # km/h
    data['speed'] = 40.0
    data['travel_time'] = data['length'] / data['speed']

def update_traffic(G, planned_route_nodes=None):
    """Randomly inject heavy traffic, but deliberately block the immediate planned route to demonstrate live re-routing."""
    local_traffic_edges = []
    global_traffic_edges = []
    
    # Deliberately pick an edge directly ahead on our planned route to block
    target_block_edge = None
    if planned_route_nodes and len(planned_route_nodes) > 3:
        # Block the edge between node 2 and node 3 (right ahead of the bike)
        target_block_edge = (planned_route_nodes[2], planned_route_nodes[3])
    
    # Create a set for O(1) lookup
    relevant_set = set(planned_route_nodes) if planned_route_nodes else set()
    
    for u, v, k, data in G.edges(keys=True, data=True):
        is_near_route = (u in relevant_set or v in relevant_set)
        
        # If this is our target block edge, 100% chance to block it heavily
        if target_block_edge and ((u == target_block_edge[0] and v == target_block_edge[1]) or (v == target_block_edge[0] and u == target_block_edge[1])):
            data['speed'] = random.uniform(2.0, 4.0)  # Extreme traffic
        # 3% chance of random traffic if near route
        elif is_near_route and random.random() < 0.03:
            data['speed'] = random.uniform(5.0, 10.0)  # Very slow traffic
        else:
            # Gradually clear existing traffic everywhere
            data['speed'] = min(data['base_speed'], data['speed'] + 5.0)
            
        data['travel_time'] = data['length'] / data['speed']
        
        # Collect traffic for visualization
        if data['speed'] < 15.0:
            edge_coords = [[G.nodes[u]['y'], G.nodes[u]['x']], [G.nodes[v]['y'], G.nodes[v]['x']]]
            global_traffic_edges.append(edge_coords)
            if is_near_route:
                local_traffic_edges.append(edge_coords)
            
    return local_traffic_edges, global_traffic_edges

# -------------------------------
# Step 5: Simulation Engine
# -------------------------------

def simulate_journey(start_node, target_node, label):
    current_node = start_node
    frames = []
    
    # We need an initial planned route so we know where to spawn traffic
    try:
        planned_route_nodes = nx.shortest_path(G, current_node, target_node, weight='travel_time')
    except nx.NetworkXNoPath:
        planned_route_nodes = [current_node]
        
    print(f"\n🚀 Starting journey: {label}...")
    
    def get_route_stats(route):
        if len(route) < 2: return 0, 0
        t_sum = 0
        d_sum = 0
        for u, v in zip(route[:-1], route[1:]):
            edge_data = min(G[u][v].values(), key=lambda d: d['travel_time'])
            t_sum += edge_data['travel_time']
            d_sum += edge_data['length']
        return t_sum, d_sum

    step_count = 0
    # Stop if we reach target or are trapped (safety limit 1000 steps)
    while current_node != target_node and step_count < 1000:
        step_count += 1
        
        is_rerouting = False
        
        # Every 15 steps, traffic changes (less frequent, looks more natural)
        if step_count % 15 == 0:
            heavy_traffic, global_traffic = update_traffic(G, planned_route_nodes)
        else:
            # Keep previous traffic state visually
            relevant_set = set(planned_route_nodes)
            heavy_traffic = [
                [[G.nodes[u]['y'], G.nodes[u]['x']], [G.nodes[v]['y'], G.nodes[v]['x']]]
                for u, v, k, d in G.edges(keys=True, data=True) if d['speed'] < 15.0 and (u in relevant_set or v in relevant_set)
            ]
            global_traffic = [
                [[G.nodes[u]['y'], G.nodes[u]['x']], [G.nodes[v]['y'], G.nodes[v]['x']]]
                for u, v, k, d in G.edges(keys=True, data=True) if d['speed'] < 15.0
            ]
            
        # Re-calculate shortest path based on *current* travel times (Dynamic Re-routing!)
        try:
            # Ensure planned_route starts from current_node
            if current_node in planned_route_nodes:
                idx = planned_route_nodes.index(current_node)
                current_planned = planned_route_nodes[idx:]
            else:
                current_planned = nx.shortest_path(G, current_node, target_node, weight='travel_time')

            current_time, current_dist = get_route_stats(current_planned)
            
            new_route_nodes = nx.shortest_path(G, current_node, target_node, weight='travel_time')
            new_time, new_dist = get_route_stats(new_route_nodes)
            
            time_saved = current_time - new_time
            
            if time_saved > 0:
                time_savings_pct = time_saved / max(current_time, 1)
                dist_increase_pct = (new_dist - current_dist) / max(current_dist, 1)
                
                # If it's a minor time save (<20%) but a huge detour (>30%), wait it out in traffic!
                if time_savings_pct < 0.20 and dist_increase_pct > 0.30:
                    planned_route_nodes = current_planned
                else:
                    if current_planned != new_route_nodes:
                        is_rerouting = True
                    planned_route_nodes = new_route_nodes
            else:
                planned_route_nodes = current_planned

        except nx.NetworkXNoPath:
            planned_route_nodes = [current_node]
            
        planned_route_coords = [[G.nodes[n]['y'], G.nodes[n]['x']] for n in planned_route_nodes]
        bike_pos = [G.nodes[current_node]['y'], G.nodes[current_node]['x']]
        
        # Determine status label
        if is_rerouting:
            status_label = "🚨 Live Google Maps: Rerouting for faster path..."
        elif heavy_traffic and len(heavy_traffic) > 0:
            status_label = f"{label} (Waiting in traffic, detour is too long...)"
        else:
            status_label = f"{label} (Moving smoothly...)"

        frames.append({
            "bike_pos": bike_pos,
            "planned_route": planned_route_coords,
            "heavy_traffic": heavy_traffic,
            "global_traffic": global_traffic,
            "label": status_label
        })
        
        # Advance one node along the planned route
        if len(planned_route_nodes) > 1:
            current_node = planned_route_nodes[1]
        else:
            break

    # Final frame at destination
    bike_pos = [G.nodes[target_node]['y'], G.nodes[target_node]['x']]
    frames.append({
        "bike_pos": bike_pos,
        "planned_route": [bike_pos],
        "heavy_traffic": [],
        "label": f"✅ Reached {label.split(' ')[-1]}!"
    })
    
    return frames

print("\nSimulating Partner -> Shop...")
frames_part1 = simulate_journey(partner_node, shop_node, "Going to Shop")

print("Simulating Shop -> Customer...")
frames_part2 = simulate_journey(shop_node, customer_node, "Delivering to Customer")

all_frames = frames_part1 + frames_part2

# -------------------------------
# Step 6: Generate Advanced HTML Animation
# -------------------------------
print("\nGenerating Real-Time Animation Map...")

html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Dynamic Route & Traffic Simulation</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html {{ margin: 0; padding: 0; height: 100%; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
        #map {{ width: 100%; height: 100%; }}
        #info-box {{
            position: absolute;
            top: 20px;
            left: 50px;
            z-index: 1000;
            background: rgba(255, 255, 255, 0.95);
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 8px 16px rgba(0,0,0,0.2);
            min-width: 300px;
            backdrop-filter: blur(5px);
        }}
        h3 {{ margin-top: 0; color: #333; }}
        #status-text {{ font-size: 16px; font-weight: bold; color: #0078D7; margin-bottom: 15px; }}
        .legend {{ font-size: 14px; margin-top: 10px; color: #555; }}
        .legend div {{ margin-bottom: 8px; }}
        .color-box {{ display: inline-block; width: 18px; height: 18px; margin-right: 8px; vertical-align: middle; border-radius: 3px; }}
        .emoji-icon {{ background: transparent; border: none; }}
    </style>
</head>
<body>
    <div id="info-box">
        <h3>Live Delivery Tracker</h3>
        <p id="status-text">Initializing Route...</p>
        <div class="legend">
            <div><span class="color-box" style="background: #0078D7;"></span> Planned Route (Re-calculates)</div>
            <div><span class="color-box" style="background: #E81123;"></span> Live Heavy Traffic</div>
            <div style="margin-top: 15px;">🏪 {shop_name} &nbsp;&nbsp;&nbsp; 🏠 Customer</div>
        </div>
    </div>
    <div id="map"></div>

    <script>
        var frames = {json.dumps(all_frames)};
        var shopLoc = [{shop_location[0]}, {shop_location[1]}];
        var custLoc = [{customer_location[0]}, {customer_location[1]}];
        
        var map = L.map('map').setView(shopLoc, 14);
        
        // CartoDB dark or light mode maps look very professional
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '© OpenStreetMap contributors © CARTO',
            maxZoom: 19
        }}).addTo(map);

        // Emoji Icons and SVG
        var createEmojiIcon = function(emoji, size) {{
            return L.divIcon({{
                html: '<div style="font-size: ' + size + 'px; line-height: 1; text-align: center; filter: drop-shadow(2px 4px 6px rgba(0,0,0,0.4));">' + emoji + '</div>',
                className: 'emoji-icon',
                iconSize: [size, size],
                iconAnchor: [size/2, size/2],
                popupAnchor: [0, -size/2]
            }});
        }};

        // Top-down yellow vehicle SVG
        var topDownVehicleSvg = `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" class="vehicle-svg" style="width:100%; height:100%; filter: drop-shadow(2px 4px 6px rgba(0,0,0,0.4)); transition: transform 0.3s ease-out;">
            <rect x="25" y="10" width="50" height="80" rx="15" fill="#FFC107" stroke="#333" stroke-width="2"/>
            <rect x="30" y="25" width="40" height="20" rx="3" fill="#222"/>
            <rect x="30" y="55" width="40" height="15" rx="3" fill="#222"/>
            <!-- headlights -->
            <circle cx="35" cy="12" r="3" fill="#FFF"/>
            <circle cx="65" cy="12" r="3" fill="#FFF"/>
            <!-- taillights -->
            <rect x="30" y="88" width="10" height="4" fill="#F00"/>
            <rect x="60" y="88" width="10" height="4" fill="#F00"/>
        </svg>`;

        var createVehicleIcon = function(size) {{
            return L.divIcon({{
                html: '<div style="width:' + size + 'px; height:' + size + 'px;">' + topDownVehicleSvg + '</div>',
                className: 'vehicle-icon',
                iconSize: [size, size],
                iconAnchor: [size/2, size/2],
                popupAnchor: [0, -size/2]
            }});
        }};

        var shopIcon = createEmojiIcon('🏪', 40);
        var custIcon = createEmojiIcon('🏠', 40);
        var bikeIcon = createVehicleIcon(45);

        L.marker(shopLoc, {{icon: shopIcon}}).addTo(map).bindPopup("<b>{shop_name}</b><br>Pickup Location");
        L.marker(custLoc, {{icon: custIcon}}).addTo(map).bindPopup("<b>Customer</b><br>Delivery Location");

        var bikeMarker = L.marker(frames[0].bike_pos, {{icon: bikeIcon}}).addTo(map);
        
        var routeLine = L.polyline([], {{color: '#0078D7', weight: 6, opacity: 0.8, lineJoin: 'round'}}).addTo(map);
        var trafficLayer = L.layerGroup().addTo(map);
        
        var currentFrame = 0;
        
        // Calculate bearing between two points
        function getBearing(startLat, startLng, destLat, destLng) {{
            startLat = startLat * Math.PI / 180;
            startLng = startLng * Math.PI / 180;
            destLat = destLat * Math.PI / 180;
            destLng = destLng * Math.PI / 180;

            var y = Math.sin(destLng - startLng) * Math.cos(destLat);
            var x = Math.cos(startLat) * Math.sin(destLat) - Math.sin(startLat) * Math.cos(destLat) * Math.cos(destLng - startLng);
            var brng = Math.atan2(y, x);
            brng = brng * 180 / Math.PI;
            return (brng + 360) % 360;
        }}
        
        // Smooth animation logic
        function interpolatePosition(start, end, progress) {{
            return [
                start[0] + (end[0] - start[0]) * progress,
                start[1] + (end[1] - start[1]) * progress
            ];
        }}

        var isAnimating = false;

        function animateFrame() {{
            if (currentFrame >= frames.length - 1) {{
                document.getElementById('status-text').innerText = "✅ Delivery Complete!";
                document.getElementById('status-text').style.color = "#107C10";
                return;
            }}
            
            var frame = frames[currentFrame];
            var nextFrame = frames[currentFrame + 1];
            
            // UI Updates
            document.getElementById('status-text').innerText = frame.label;
            routeLine.setLatLngs(frame.planned_route);
            
            trafficLayer.clearLayers();
            for (var i = 0; i < frame.heavy_traffic.length; i++) {{
                L.polyline(frame.heavy_traffic[i], {{color: '#E81123', weight: 6, opacity: 0.7}}).addTo(trafficLayer);
            }}
            
            // Pan map
            if (currentFrame % 8 === 0) {{
                map.panTo(frame.bike_pos, {{animate: true, duration: 1}});
            }}
            
            // Rotate Icon
            var bearing = getBearing(frame.bike_pos[0], frame.bike_pos[1], nextFrame.bike_pos[0], nextFrame.bike_pos[1]);
            var iconElement = bikeMarker.getElement().querySelector('.vehicle-svg');
            if (iconElement) {{
                iconElement.style.transform = 'rotate(' + bearing + 'deg)';
            }}
            
            // Micro-animation for bike moving smoothly between nodes
            var startTime = performance.now();
            var duration = 400; // ms to move from current node to next node
            
            function step(currentTime) {{
                var elapsed = currentTime - startTime;
                var progress = Math.min(elapsed / duration, 1);
                
                var currentPos = interpolatePosition(frame.bike_pos, nextFrame.bike_pos, progress);
                bikeMarker.setLatLng(currentPos);
                
                if (progress < 1) {{
                    requestAnimationFrame(step);
                }} else {{
                    currentFrame++;
                    // Slight pause between logical steps to simulate traffic logic
                    setTimeout(animateFrame, 150); 
                }}
            }}
            
            requestAnimationFrame(step);
        }}
        
        // Start after a slight delay
        setTimeout(animateFrame, 1500);
        
    </script>
</body>
</html>
"""

file_name = "live_delivery_map.html"
with open(file_name, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"\n✅ All done! The dynamic simulation has been saved to '{file_name}'.")
webbrowser.open(file_name)

# -------------------------------
# Step 7: Generate Backend Analysis HTML
# -------------------------------
print("\nGenerating Backend Server Analysis Map...")

html_backend_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Backend Server: Google Maps Live Traffic Analysis</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html {{ margin: 0; padding: 0; height: 100%; font-family: 'Courier New', Courier, monospace; background: #000; }}
        #map {{ width: 100%; height: 100%; }}
        #info-box {{
            position: absolute;
            top: 20px;
            right: 20px;
            z-index: 1000;
            background: rgba(0, 0, 0, 0.85);
            padding: 20px;
            border: 1px solid #0F0;
            border-radius: 5px;
            box-shadow: 0 0 15px rgba(0,255,0,0.5);
            min-width: 300px;
            color: #0F0;
        }}
        h3 {{ margin-top: 0; color: #0F0; border-bottom: 1px solid #0F0; padding-bottom: 5px; }}
        #status-text {{ font-size: 14px; margin-bottom: 15px; font-weight: bold; }}
        .legend {{ font-size: 12px; margin-top: 10px; }}
        .legend div {{ margin-bottom: 5px; }}
        .color-box {{ display: inline-block; width: 15px; height: 15px; margin-right: 8px; vertical-align: middle; }}
    </style>
</head>
<body>
    <div id="info-box">
        <h3>SERVER TRAFFIC ANALYSIS</h3>
        <p id="status-text">ANALYZING CITY GRID...</p>
        <div class="legend">
            <div><span class="color-box" style="background: #00FFFF;"></span> COMPUTED OPTIMAL ROUTE</div>
            <div><span class="color-box" style="background: #FF0000;"></span> DETECTED CONGESTION (SPEED &lt; 15 KM/H)</div>
        </div>
        <p style="font-size: 10px; margin-top: 15px; color: #888;">Live data feed from Google Maps API Simulator</p>
    </div>
    <div id="map"></div>

    <script>
        var frames = {json.dumps(all_frames)};
        var shopLoc = [{shop_location[0]}, {shop_location[1]}];
        var custLoc = [{customer_location[0]}, {customer_location[1]}];
        
        var map = L.map('map', {{zoomControl: false}}).setView(shopLoc, 13);
        
        // CartoDB Dark Matter map for that "backend server" feel
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '© OpenStreetMap contributors © CARTO',
            maxZoom: 19
        }}).addTo(map);

        var routeLine = L.polyline([], {{color: '#00FFFF', weight: 4, opacity: 0.8, dashArray: '5, 10'}}).addTo(map);
        var globalTrafficLayer = L.layerGroup().addTo(map);
        
        var currentFrame = 0;

        function animateFrame() {{
            if (currentFrame >= frames.length) {{
                document.getElementById('status-text').innerText = "ANALYSIS COMPLETE. VEHICLE ARRIVED.";
                return;
            }}
            
            var frame = frames[currentFrame];
            
            // UI Updates
            if (frame.label.includes("Rerouting")) {{
                document.getElementById('status-text').innerHTML = "<span style='color: #FF0000;'>ALERT: OBSTRUCTION DETECTED. RECALCULATING...</span>";
            }} else if (frame.label.includes("Waiting")) {{
                document.getElementById('status-text').innerHTML = "<span style='color: #FFA500;'>WARNING: TRAFFIC AHEAD. DETOUR SUB-OPTIMAL. WAITING...</span>";
            }} else {{
                document.getElementById('status-text').innerText = "MONITORING GRID... ROUTE OPTIMAL.";
            }}
            
            routeLine.setLatLngs(frame.planned_route);
            
            globalTrafficLayer.clearLayers();
            for (var i = 0; i < frame.global_traffic.length; i++) {{
                L.polyline(frame.global_traffic[i], {{color: '#FF0000', weight: 3, opacity: 0.6}}).addTo(globalTrafficLayer);
            }}
            
            currentFrame++;
            // This runs at exactly the same speed as the bike's logic steps (550ms = 400ms duration + 150ms pause)
            setTimeout(animateFrame, 550); 
        }}
        
        setTimeout(animateFrame, 1500);
        
    </script>
</body>
</html>
"""

backend_file_name = "backend_traffic_analysis.html"
with open(backend_file_name, "w", encoding="utf-8") as f:
    f.write(html_backend_content)

print(f"✅ Backend Traffic Analysis simulation saved to '{backend_file_name}'.")
webbrowser.open(backend_file_name)
