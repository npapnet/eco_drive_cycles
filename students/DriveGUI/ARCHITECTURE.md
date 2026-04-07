# DriveGUI Architecture and Data Flow

> **FROZEN** — `students/DriveGUI/` is a historical reference implementation. It is self-contained and must NOT import from `src/drive_cycle_calculator`. The active successor is `examples/gui/main.py`. This file documents the original student code as-is.

## Overview
The `DriveGUI` toolkit is a Python-based application designed to process and visualize eco-driving data logs from vehicle OBD/GPS systems. The application features a graphical user interface (GUI) built with `tkinter` and relies heavily on `pandas` for data manipulation and `matplotlib` for generating charts.

## Entry Points
- **`driving_cycles_calculatorV1.py`**: This is the main graphical entry point. Running this script opens the GUI. It orchestrates the entire workflow: selecting the input folder, kicking off the smoothing calculations, and presenting buttons to visualize varied metrics across Morning and Evening sessions.

## File Connections and Modules

1. **GUI & Orchestration**
   - `driving_cycles_calculatorV1.py`: Binds everything together. It connects UI buttons to functions imported from other modules.
   - It references `calculations.py` for raw data ingestion and smoothing.
   - It references various `show_*` functions from individual metric files (e.g., `average_speed.py`, `co2_chart.py`) to render and display the visualizations.

2. **Data Ingestion & Processing Core**
   - `calculations.py`: The fundamental processing engine. It is responsible for parsing raw Excel logs and producing a consolidated, normalized dataset containing derived metrics like geometric acceleration.

3. **Metrics & Visualization Modules**
   - Each of the following scripts contains a focused `show_*` function to calculate and plot a specific grouped-bar metric (usually categorizing data into "Morning", "Evening", and "Overall" based on the internal time associated with the sheet name):
     - `average_acceleration.py`
     - `average_deceleration.py`
     - `average_speed.py`
     - `average_speed_without_stops.py`
     - `maximum_speed.py`
     - `number_of_stops.py`
     - `stop_percentage.py`
     - `total_stop_percentage.py`
     - `engine_load.py`
     - `fuel_consumption_chart.py`
     - `co2_chart.py`
   - **Representative Route logic**:
     - `representative_route.py` computes multiple metrics across all driving sessions, compares the overall dataset averages to individual sessions to define a normalized "similarity score," and displays a table of the most representative session.
     - `speed_profile.py` handles plotting the speed curve specifically for the most representative session.

## Data Processing Flow Order

1. **Folder Selection & File Scanning**
   - The user selects a directory via the GUI containing raw recorded Excel files (`.xlsx`). 
   - Files are listed and sorted chronologically based on internal header date strings or file modification times.

2. **Data Smoothing and Basic Calculations (`calculations.py`)**
   - **Reads**: Raw `.xlsx` files mapping to a specific set of required columns: `GPS Time`, `Speed (OBD)(km/h)`, `CO₂ in g/km...`, `Engine Load(%)`, and `Fuel flow rate...`.
   - **Processes**:
     - Converts GPS Time to elapsed seconds (`Διάρκεια (sec)`).
     - Applies a rolling mean (window=4) over speed to create smoothed speed (`Εξομαλυνση`).
     - Converts smoothed speed to m/s (`Ταχ m/s`).
     - Differentiates speed to obtain acceleration/deceleration (`a(m/s2)`).
     - Separates positive and negative accelerations into respective distinct columns (`Επιταχυνση`, `Επιβραδυνση`).
   - **Outputs**: Generates a consolidated log named `calculations_log_<timestamp>.xlsx` in an `INPUT/log/` subfolder. Each original drive session acts as a separate sheet (named like `YYYY-MM-DD_Morning` or `YYYY-MM-DD_Evening`).

3. **Metric Extraction and Visualization**
   - Once the user clicks to view a chart, the corresponding visualization script (e.g., `average_speed.py`) dynamically finds the **newest** `calculations_log_*.xlsx` generated during the processing phase.
   - It iterates over the worksheets (each representing a drive segment), filters/calculates final metric values (e.g., stopping percentages, moving speeds), aggregates them by Date & Session, and generates a `matplotlib` grouped-bar chart.
