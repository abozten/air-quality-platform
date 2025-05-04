# backend/app/aggregation.py
import geohash  # Import the library
from typing import List, Dict, Optional
from collections import defaultdict
from .models import AirQualityReading, AggregatedAirQualityPoint # Import AggregatedAirQualityPoint

# Define the structure for aggregated results per geohash cell
# (Using AggregatedAirQualityPoint directly in the result list is cleaner,
# but this internal class helps manage sums and counts)
class AggregatedData:
    def __init__(self):
        self.lat_sum = 0.0
        self.lon_sum = 0.0
        self.pm25_sum = 0.0
        self.pm10_sum = 0.0
        self.no2_sum = 0.0
        self.so2_sum = 0.0
        self.o3_sum = 0.0
        self.pm25_count = 0 # Count per metric for accurate averaging
        self.pm10_count = 0
        self.no2_count = 0
        self.so2_count = 0
        self.o3_count = 0
        self.total_count = 0 # Total number of readings in this cell

    def add_reading(self, reading: AirQualityReading):
        # Use actual lat/lon for averaging position later
        self.lat_sum += reading.latitude
        self.lon_sum += reading.longitude

        # Add values and increment specific counts only if they exist
        if reading.pm25 is not None:
            self.pm25_sum += reading.pm25
            self.pm25_count += 1
        if reading.pm10 is not None:
            self.pm10_sum += reading.pm10
            self.pm10_count += 1
        if reading.no2 is not None:
            self.no2_sum += reading.no2
            self.no2_count += 1
        if reading.so2 is not None:
            self.so2_sum += reading.so2
            self.so2_count += 1
        if reading.o3 is not None:
            self.o3_sum += reading.o3
            self.o3_count += 1

        self.total_count += 1 # Increment total count regardless of individual metrics

    def get_aggregated_point(self, geohash_str: str) -> Optional[AggregatedAirQualityPoint]:
        """ Calculates the average values and returns an AggregatedAirQualityPoint model. """
        if self.total_count == 0:
            return None # Avoid division by zero

        # Calculate representative coordinate for the cell
        avg_lat = self.lat_sum / self.total_count
        avg_lon = self.lon_sum / self.total_count
        # Alternative: use geohash center - geohash.decode(geohash_str)
        # Using averaged lat/lon might be slightly more representative of the data distribution within the cell.

        # Calculate averages only if data was present for that metric
        avg_pm25 = round(self.pm25_sum / self.pm25_count, 2) if self.pm25_count > 0 else None
        avg_pm10 = round(self.pm10_sum / self.pm10_count, 2) if self.pm10_count > 0 else None
        avg_no2 = round(self.no2_sum / self.no2_count, 2) if self.no2_count > 0 else None
        avg_so2 = round(self.so2_sum / self.so2_count, 2) if self.so2_count > 0 else None
        avg_o3 = round(self.o3_sum / self.o3_count, 2) if self.o3_count > 0 else None


        return AggregatedAirQualityPoint(
            geohash=geohash_str,
            latitude=round(avg_lat, 6), # Increased precision for display
            longitude=round(avg_lon, 6), # Increased precision for display
            avg_pm25=avg_pm25,
            avg_pm10=avg_pm10,
            avg_no2=avg_no2,
            avg_so2=avg_so2,
            avg_o3=avg_o3,
            count=self.total_count # Use the total count of readings aggregated
        )


def aggregate_by_geohash(
    points: List[AirQualityReading],
    precision: int = 6,
    max_cells: Optional[int] = None
) -> List[AggregatedAirQualityPoint]: # Return type is now List[AggregatedAirQualityPoint]
    """
    Aggregates air quality readings by geohash for display purposes.

    This function calculates geohashes *on the fly* based on the requested `precision`.
    It does NOT rely on geohashes stored in the database.

    Args:
        points: List of AirQualityReading objects.
        precision: The geohash precision level (length of the geohash string)
                   for this specific aggregation request. Lower precision means larger cells.
        max_cells: Optional maximum number of aggregated cells to return.
                   If specified, the list might be truncated.

    Returns:
        A list of AggregatedAirQualityPoint objects, each representing an aggregated geohash cell.
    """
    if not points:
        return []

    aggregated_cells: Dict[str, AggregatedData] = defaultdict(AggregatedData)

    for point in points:
        if point.latitude is None or point.longitude is None:
            continue # Skip points without coordinates

        try:
            # Calculate geohash using the *requested aggregation precision*
            gh = geohash.encode(point.latitude, point.longitude, precision=precision)
            aggregated_cells[gh].add_reading(point)
        except Exception as e:
            # Log error but continue processing other points
            print(f"Could not process point for aggregation: {point}, Error: {e}") # Use logger in real app
            continue

    # Convert aggregated data into the desired output format
    result_list: List[AggregatedAirQualityPoint] = []
    for gh_str, agg_data in aggregated_cells.items():
        agg_point = agg_data.get_aggregated_point(gh_str)
        if agg_point:
            result_list.append(agg_point)

    # Apply limit if specified
    if max_cells is not None and len(result_list) > max_cells:
         # Optional: Sort here before truncating if needed, e.g., by count or location
         # result_list.sort(key=lambda x: x.count, reverse=True)
         return result_list[:max_cells]
    else:
        return result_list