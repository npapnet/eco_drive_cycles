# Processing Formulas and Mentality

This document details the mathematical algorithms and filtering logic applied at each step of the DriveGUI data pipeline to produce eco-driving cycle charts.

## 1. Initial Smoothing and Conversion (`calculations.py`)

Before creating specialized charts, the raw data undergoes standardization filtering for consistency:
- **Elapsed Time (`Διάρκεια (sec)`)**: Extracted from raw "GPS Time" arrays, normalizing varying formats into plain elapsed seconds from the start of the log.
- **Speed Smoothing (`Εξομαλυνση`)**: A centered rolling mean function spanning 4 samples (`window=4, center=True, min_periods=4`) is applied to raw OBD speed (km/h) to filter out jitter, sensor noise, and GPS scatter errors.
- **Conversion to Metric Units (`Ταχ m/s`)**: Smoothed speed is divided by 3.6 to convert to $m/s$.
- **Acceleration Pipeline (`a(m/s2)`)**: Acceleration is derived via mathematical differentiation `.diff()` across consecutive samples of the target velocity (`Ταχ m/s`).
- **Splitting Accelerations**:
  - `Επιταχυνση` exclusively isolates values $> 0$ (positive acceleration).
  - `Επιβραδυνση` exclusively isolates values $< 0$ (negative acceleration / deceleration).

## 2. Calculation of Specific Metrics

The subsequent charting scripts process the locally cached variables inside `calculations_log_...xlsx` using the following patterns:

### Average Speed
- **Filter**: None, accepts the entire array.
- **Formula**: `Mean(Ταχ m/s) * 3.6`
- **Mentality**: Averages the speed (including stops) directly from the smoothed `m/s` column to determine the overall pace of the trip, converting it back to $km/h$. 

### Average Speed Without Stops
- **Filter**: Excludes rows where $Speed(km/h) \le 2.0$ km/h (the default stop threshold parameter).
- **Formula**: `Mean(Speed[Speed > Threshold])`
- **Mentality**: Filters out prolonged idle periods (like red traffic lights or heavy stationary stops) to capture the actual flow rate when the vehicle operates unhindered.

### Average Acceleration / Deceleration
- **Logic**: Reads specifically from the heavily filtered `Επιταχυνση` (Acceleration $> 0$) or `Επιβραδυνση` (Deceleration $< 0$) columns.
- **Formula**: Simple Arithmetic Mean of the non-empty column space (omitting `NaN` values representing neutral/opposing motion).
- **Mentality**: Isolates only periods where the pedal is effectively pushed (or brakes applied / engine coasting occurs), thereby indicating driver aggressiveness independently of traffic stops.

### Stop Percentage (%)
- **Logic**: Counts rows where $Speed \le 2.0$ km/h, checking against the smoothed velocity.
- **Formula**: `(Count(Speed <= 2.0) / Total_Samples) * 100`
- **Mentality**: Analyzes infrastructural drag and congestion, indicating the proportion of an eco-cycle spent purely idling.

### CO₂ Emissions and Fuel Flow
- **Target Fields**: Reads `CO₂ in g/km (Average)(g/km)` and `Fuel flow rate/hour(l/hr)`.
- **Formula**: Arithmetic Mean across all active samples in a trip.
- **Mentality**: Extracts the direct average of raw sampled OBD sensor rates per trip for direct visualization. 

### Representative Route Similarity Calculator (Heuristic)
The toolkit nominates one specific single driven session as the "Most Representative" using an equal weight similarity heuristic scoring system against 7 parameters: Duration, Mean Speed, Mean Moving Speed, Number of Stops, Stops Percentage, Mean Positive Acceleration, and Mean Deceleration.

- **Similarity Score Formulation**: 
  $Similarity (\%) = 100 - \frac{| Representative\_Value - Overall\_Average\_Value |}{ |Overall\_Average\_Value| } \times 100$
- **Mentality**: Evaluates the absolute percentage discrepancy across metrics from the dataset's grand mean, then averages those percentages. Whichever driving session boasts the highest mean percentage similarity gets nominated dynamically as the most representative baseline cycle.
