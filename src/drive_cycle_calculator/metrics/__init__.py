from drive_cycle_calculator.metrics._computations import (
    compute_average_acceleration,
    compute_average_deceleration,
    # Public flat functions — backward-compat exports
    compute_average_speed,
    compute_average_speed_without_stops,
    compute_co2_emissions,
    compute_engine_load,
    compute_fuel_consumption,
    compute_maximum_speed,
    compute_number_of_stops,
    compute_session_metrics,
    compute_speed_profile,
    compute_stop_percentage,
    compute_total_stop_percentage,
    find_representative_sheet,
    similarity,
)
from drive_cycle_calculator.metrics.trip import Trip, TripCollection

__all__ = [
    "Trip",
    "TripCollection",
    "compute_average_speed",
    "compute_average_speed_without_stops",
    "compute_average_acceleration",
    "compute_average_deceleration",
    "compute_co2_emissions",
    "compute_engine_load",
    "compute_fuel_consumption",
    "compute_maximum_speed",
    "compute_number_of_stops",
    "compute_session_metrics",
    "compute_speed_profile",
    "compute_stop_percentage",
    "compute_total_stop_percentage",
    "find_representative_sheet",
    "similarity",
]
