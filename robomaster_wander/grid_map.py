import math
import numpy as np

class GridMapper:
    def __init__(self, width_m=10.0, height_m=10.0, resolution=0.1):
        """
        Simple Occupancy Grid Mapper
        width_m, height_m: Map size in meters
        resolution: Grid resolution in meters
        """
        self.resolution = resolution
        self.width = int(width_m / resolution)
        self.height = int(height_m / resolution)
        self.center_x = self.width // 2
        self.center_y = self.height // 2
        
        # 0.5 = unknown, 0.0 = free, 1.0 = occupied
        self.map = np.full((self.width, self.height), 0.5)
        
        # Probabilistic updates
        self.log_odds_map = np.zeros((self.width, self.height))
        self.l_occ = math.log(0.8 / 0.2)
        self.l_free = math.log(0.3 / 0.7)
        self.l_max = 5.0
        self.l_min = -5.0

    def update(self, robot_x, robot_y, robot_yaw, sensor_angle, distance_m):
        """
        Update map with a single sensor reading.
        robot_x, robot_y: Robot position in meters (relative to start)
        robot_yaw: Robot heading in radians
        sensor_angle: Sensor angle relative to robot (radians)
        distance_m: Measured distance (meters). If None/Inf, assume free up to max range.
        """
        # Calculate sensor global angle
        global_angle = robot_yaw + sensor_angle
        
        # Max reliable range for ToF (e.g. 2.0m)
        max_range = 2.0
        
        if distance_m is None or distance_m > max_range:
            meas_dist = max_range
            hit = False
        else:
            meas_dist = distance_m
            hit = True
            
        # Raycasting using Bresenham's line algorithm or simple sampling
        # End point
        end_x = robot_x + meas_dist * math.cos(global_angle)
        end_y = robot_y + meas_dist * math.sin(global_angle)
        
        # Convert to grid coordinates
        start_ix = int(robot_x / self.resolution) + self.center_x
        start_iy = int(robot_y / self.resolution) + self.center_y
        end_ix = int(end_x / self.resolution) + self.center_x
        end_iy = int(end_y / self.resolution) + self.center_y
        
        # Get line points
        points = self.bresenham(start_ix, start_iy, end_ix, end_iy)
        
        for (ix, iy) in points:
            if 0 <= ix < self.width and 0 <= iy < self.height:
                # Update free space
                self.log_odds_map[ix][iy] += self.l_free
                
        # Update hit point
        if hit:
            if 0 <= end_ix < self.width and 0 <= end_iy < self.height:
                self.log_odds_map[end_ix][end_iy] += self.l_occ
                
        # Clamp values
        np.clip(self.log_odds_map, self.l_min, self.l_max, out=self.log_odds_map)
        
        # Update probability map for visualization/planning
        # p = 1 - 1 / (1 + exp(l))
        self.map = 1.0 - 1.0 / (1.0 + np.exp(self.log_odds_map))

    def bresenham(self, x0, y0, x1, y1):
        """Bresenham's Line Algorithm"""
        points = []
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        x, y = x0, y0
        sx = -1 if x0 > x1 else 1
        sy = -1 if y0 > y1 else 1
        if dx > dy:
            err = dx / 2.0
            while x != x1:
                points.append((x, y))
                err -= dy
                if err < 0:
                    y += sy
                    err += dx
                x += sx
        else:
            err = dy / 2.0
            while y != y1:
                points.append((x, y))
                err -= dx
                if err < 0:
                    x += sx
                    err += dy
                y += sy
        points.append((x, y))
        return points

    def find_frontier(self, robot_x, robot_y):
        """Find the nearest 'frontier' (boundary between free and unknown)."""
        # Simple heuristic: Look for 0.5 (unknown) cells adjacent to < 0.2 (free) cells.
        # And pick one closest to robot.
        # Optimization: Just sample or search in spiral.
        
        # For simplicity in this demo:
        # Find a target in free space that is far from obstacles.
        # Or just use Potential Field on the grid.
        pass

    def get_potential_field_direction(self, robot_x, robot_y):
        """
        Calculate artificial potential field force.
        Repulsive force from occupied cells.
        Attractive force towards exploration (e.g. forward or unknown).
        """
        rx_idx = int(robot_x / self.resolution) + self.center_x
        ry_idx = int(robot_y / self.resolution) + self.center_y
        
        force_x = 0.0
        force_y = 0.0
        
        # Window size for local planning
        window = 20 # 2 meters
        
        for dx in range(-window, window):
            for dy in range(-window, window):
                ix = rx_idx + dx
                iy = ry_idx + dy
                
                if 0 <= ix < self.width and 0 <= iy < self.height:
                    prob = self.map[ix][iy]
                    if prob > 0.6: # Obstacle
                        dist = math.hypot(dx, dy) * self.resolution
                        if dist < 0.1: dist = 0.1
                        # Repulsive force: 1/d^2
                        f = 1.0 / (dist * dist)
                        angle = math.atan2(dy, dx)
                        force_x -= f * math.cos(angle)
                        force_y -= f * math.sin(angle)
                        
        # Attractive force (bias to move forward/explore)
        # For wandering, just a constant forward bias relative to robot heading?
        # Or random walk vector.
        # Let's add a bias towards "unknown" areas?
        # Too complex for now. Let's just add a constant "forward" force in robot frame
        # and let obstacles deflect it.
        # But we need to return a global vector.
        # Actually, "Wander" usually means "Move Forward until blocked".
        # So attractive force is "Current Heading".
        
        return force_x, force_y
