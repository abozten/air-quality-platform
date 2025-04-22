# backend/app/aggregation.py (New file)
import geohash # Import the library
from typing import List, Dict, Tuple,Optional
from collections import defaultdict
from .models import AirQualityReading # Assuming models.py is in the same directory level
# Define the structure for aggregated results per geohash cell
class AggregatedData:
    def __init__(self):
        self.lat_sum = 0.0
        self.lon_sum = 0.0
        self.pm25_sum = 0.0
        self.pm10_sum = 0.0
        self.no2_sum = 0.0
        self.so2_sum = 0.0
        self.o3_sum = 0.0
        self.count = 0

    def add_reading(self, reading: AirQualityReading):
        # Use actual lat/lon for averaging position later
        self.lat_sum += reading.latitude
        self.lon_sum += reading.longitude
        # Add values only if they exist
        if reading.pm25 is not None: self.pm25_sum += reading.pm25
        if reading.pm10 is not None: self.pm10_sum += reading.pm10
        if reading.no2 is not None: self.no2_sum += reading.no2
        if reading.so2 is not None: self.so2_sum += reading.so2
        if reading.o3 is not None: self.o3_sum += reading.o3
        self.count += 1

    def get_average_point(self, geohash_str: str) -> Dict:
        if self.count == 0:
            return None # Avoid division by zero

        # Decode geohash to get approximate center (or use averaged lat/lon)
        # Using averaged lat/lon might be slightly more representative
        avg_lat = self.lat_sum / self.count
        avg_lon = self.lon_sum / self.count
        # gh_center_lat, gh_center_lon = geohash.decode(geohash_str) # Alternative: use geohash center

        return {
            "geohash": geohash_str,
            "latitude": round(avg_lat, 5),
            "longitude": round(avg_lon, 5),
            "avg_pm25": round(self.pm25_sum / self.count, 2) if self.count else None,
            "avg_pm10": round(self.pm10_sum / self.count, 2) if self.count else None,
            "avg_no2": round(self.no2_sum / self.count, 2) if self.count else None,
            "avg_so2": round(self.so2_sum / self.count, 2) if self.count else None,
            "avg_o3": round(self.o3_sum / self.count, 2) if self.count else None,
            "count": self.count
        }


def aggregate_by_geohash(points: List[AirQualityReading], precision: int = 6, max_cells: Optional[int] = None) -> List[Dict]: # Add max_cells parameter
    """
    Aggregates air quality readings by geohash.

    Args:
        points: List of AirQualityReading objects.
        precision: The geohash precision level (length of the geohash string).
        max_cells: Optional maximum number of aggregated cells to return.
                   If specified, the list might be truncated.

    Returns:
        A list of dictionaries, each representing an aggregated geohash cell.
    """
    if not points:
        return []

    aggregated_cells: Dict[str, AggregatedData] = defaultdict(AggregatedData)

    for point in points:
        if point.latitude is None or point.longitude is None:
            continue # Skip points without coordinates

        try:
            gh = geohash.encode(point.latitude, point.longitude, precision=precision)
            aggregated_cells[gh].add_reading(point)
        except Exception as e:
            print(f"Could not process point: {point}, Error: {e}")
            continue

    # Convert aggregated data into the desired output format
    result_list = []
    for gh_str, agg_data in aggregated_cells.items():
        avg_point = agg_data.get_average_point(gh_str)
        if avg_point:
            result_list.append(avg_point)

    # Apply limit if specified
    if max_cells is not None and len(result_list) > max_cells:
         # Optional: You could sort here before truncating, e.g., by count
         # result_list.sort(key=lambda x: x['count'], reverse=True)
         return result_list[:max_cells]
    else:
        return result_list
