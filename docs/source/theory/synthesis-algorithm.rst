Drive Cycle Synthesis Algorithm
===============================

The drive cycle synthesis engine in ``drive_cycle_calculator`` constructs a representative, synthetic 1 Hz driving cycle from a database of real-world trip logs. This document details the mathematical and algorithmic steps of the synthesis process, and compares the rule-based WLTP approach with the more generic, data-driven clustering approach.

---

High-Level Synthesis Pipeline
-----------------------------

The synthesis algorithm follows a unified sequence of steps, regardless of whether the target cycle uses standard WLTP phases or data-driven clusters:

.. mermaid::

   flowchart TD
       A["Microtrip Database\n(MicrotripCollection)"] --> B["Build Global Markov Transition Matrix T_global\nDiscretize Speed-Acceleration Space"]
       B --> C["Compute Frobenius Distance D_i\nFor each microtrip's local matrix T_i"]
       C --> D["Group Assignment\n(WLTP Phase or Clustering)"]
       D --> E["Compute Kinematic Targets\nDuration-weighted targets per group"]
       E --> F["Stochastic Selection\nMarkov-guided selection per group"]
       F --> G["Assembly & Junction Smoothing\nConcatenation + linear velocity ramps"]
       G --> H["Final Drive Cycle\n1 Hz Speed-Time profile"]

---

Core Algorithm Steps
--------------------

1. Microtrip Segmentation
~~~~~~~~~~~~~~~~~~~~~~~~~
Trips are first sliced into stop-to-stop motion segments (microtrips) using ``MicrotripSegmenter``.

* A **stop boundary** is detected when the vehicle speed drops below ``stop_threshold_kmh`` (default 2 km/h) for at least ``stop_min_duration_s`` (default 1.0 s).
* A **microtrip** is a continuous motion phase starting when speed exceeds the threshold and ending at the start of the next stop.
* Each microtrip :math:`i` stores its 1 Hz speed trace and is summarized by key metrics: duration :math:`T_i`, distance :math:`D_i`, mean speed :math:`V_i`, Relative Positive Acceleration (:math:`RPA_i`), and trailing stop duration :math:`S_i`.

2. Markov Chain State Discretization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To model the transition behavior of vehicles, the continuous 2D space of speed and acceleration is discretized into bins:

* **Speed bins**: Width defined by ``speed_bin_width_kmh`` (default 5.0 km/h).
* **Acceleration bins**: Width defined by ``acc_bin_width_ms2`` (default 0.1 m/s²), bounded by ``acc_range_ms2`` (default ±2.0 m/s²).

Each 1 Hz sample in a microtrip is assigned an integer bin index for speed :math:`v_{\text{bin}}` and acceleration :math:`a_{\text{bin}}`. These are mapped to a string state label:

.. math::

   \text{state} = \text{v}\{\text{speed\_lo}\}\text{\_a}\{\text{acc\_lo}\}

*Example:* ``v030_a+0.2`` represents a speed of :math:`30 \le v < 35` km/h and an acceleration of :math:`+0.2 \le a < +0.3` m/s².

From the sequence of states :math:`\mathbf{s} = (s_1, s_2, \dots, s_N)` of a microtrip, a transition count matrix is built. Each row is normalized to yield a row-stochastic local transition matrix :math:`T_i`:

.. math::

   (T_i)_{A, B} = P(s_{t+1} = B \mid s_t = A) = \frac{C_i(A \to B)}{\sum_{S} C_i(A \to S)}

where :math:`C_i(A \to B)` is the number of transitions from state :math:`A` to state :math:`B` within microtrip :math:`i`.

A **global transition matrix** :math:`T_{\text{global}}` is computed by summing counts across all microtrips in the dataset before row normalization.

3. Frobenius Distance (Markov Realism Score)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The representativeness of a microtrip's dynamic profile is evaluated by computing the normalized Frobenius distance :math:`D_i` between its local transition matrix :math:`T_i` and the fleet-level global transition matrix :math:`T_{\text{global}}`:

.. math::

   D_i = \frac{1}{|S_{\text{shared}}|} \sqrt{\sum_{A \in S_{\text{shared}}} \sum_{B} \left( (T_i)_{A, B} - (T_{\text{global}})_{A, B} \right)^2}

where :math:`S_{\text{shared}}` is the set of starting states present in both :math:`T_i` and :math:`T_{\text{global}}`.

* **Interpretation**: A lower :math:`D_i` indicates that the microtrip's speed-acceleration changes closely match the fleet's typical driving style. If there are no shared states, :math:`D_i = 1.0`.

4. Group Assignment Strategies: WLTP vs. Clustering
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Before stochastic selection, microtrips must be grouped. The package provides two different strategies for this assignment:

.. list-table:: Group Assignment Strategies
   :widths: 20 40 40
   :header-rows: 1

   * - Aspect
     - WLTP Phase-based
     - Cluster-based (Generic Method)
   * - **Grouping Criteria**
     - Rule-based speed boundaries
     - Data-driven multivariate clustering
   * - **Number of Groups**
     - Fixed: 4 phases
     - Flexible: :math:`K` clusters (user-specified)
   * - **Features Used**
     - Maximum speed (:math:`v_{\text{max}}`) only
     - Multi-dimensional kinematics (mean speed, RPA, etc.)
   * - **Philosophy**
     - Standardized, deterministic phase classification
     - Discovering natural driving patterns in the data

WLTP (GTR 15) Phase Assignment
""""""""""""""""""""""""""""""
Each microtrip is classified into one of four speed phases based on its maximum speed:

* **Low**: :math:`0.0 < v_{\text{max}} \le 56.5` km/h
* **Medium**: :math:`56.5 < v_{\text{max}} \le 76.6` km/h
* **High**: :math:`76.6 < v_{\text{max}} \le 97.4` km/h
* **Extra High**: :math:`v_{\text{max}} > 97.4` km/h

Cluster-based Assignment (The Generic Method)
"""""""""""""""""""""""""""""""""""""""""""""
The clustering strategy is a **more generic method** because it replaces manual speed-limit-based rules with a generic clustering algorithm (e.g., K-Means, DBSCAN, or hierarchical clustering) operating on a multi-dimensional kinematic feature space.

Instead of classifying only by maximum speed, the generic method utilizes the ``Clusterer`` protocol to assign a group ID (``cluster_id``) to each microtrip:

1. Feature vectors are extracted from the microtrip summary (e.g., ``mean_speed_kmh``, ``rpa``, ``idle_fraction``, ``speed_95th_kmh``, ``max_acc_ms2``, etc.).
2. Features are normalized and passed to a clustering model (such as ``KMeansClusterer``).
3. The clusterer partitions the microtrips into :math:`K` clusters. These clusters capture driving characteristics beyond speed alone, such as driving aggressiveness, traffic congestion patterns, or road geometry.

Any grouping mechanism that yields a ``pd.Series`` mapping microtrip IDs to group labels is compatible with the synthesis pipeline, making clustering the most extensible approach.

5. Kinematic Target Determination
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Within each group :math:`g`, target kinematic metrics :math:`\tau_{g, m}` are calculated as duration-weighted means across all microtrips assigned to that group:

.. math::

   \tau_{g, m} = \frac{\sum_{i \in g} m_i \cdot T_i^{\text{total}}}{\sum_{i \in g} T_i^{\text{total}}}

where :math:`m_i` is the metric value for microtrip :math:`i`, and :math:`T_i^{\text{total}}` is the total duration (motion + trailing stop).

* **Exception for RPA**: To preserve energy consistency (GTR 15 §4), the Relative Positive Acceleration target is weighted by **distance** rather than duration:

.. math::

   \tau_{g, \text{RPA}} = \frac{\sum_{i \in g} \text{RPA}_i \cdot D_i}{\sum_{i \in g} D_i}

The standard set of target metrics includes:

* ``mean_speed_kmh``: Average speed including stops.
* ``rpa``: Relative Positive Acceleration (m/s²).
* ``idle_fraction``: Stop duration divided by total duration.
* ``speed_95th_kmh``: 95th percentile speed (optional).

6. Stochastic Markov-Guided Selection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
For each group :math:`g`, a sequence of microtrips is assembled stochastically. The selection process runs :math:`N_{\text{trials}}` (default 1000) random assembly trials:

1. **Sampling Weights**: Candidates within the group are drawn with a probability biased by their representative Frobenius distance:

.. math::

   W_i \propto \exp(-\lambda \cdot D_i)

where :math:`\lambda` is ``markov_lambda``. A higher :math:`\lambda` increases the selection bias toward microtrips that closely follow the global transition probability.

2. **Reuse Suppression**: To prevent a single representative microtrip from dominating the cycle, any microtrip whose accumulated duration in the current trial sequence exceeds a percentage threshold :math:`\text{max\_reuse\_fraction}` (default 0.4) is temporarily given a weight of :math:`0`.

3. **Termination Condition**: Microtrips are appended to the trial sequence until the cumulative distance reaches the configured minimum distance target for that group (e.g. ``min_distance_per_phase`` or ``cluster_min_distance_m``).

4. **Objective Function Evaluation**: The assembled trial sequence is scored against the group's target metrics using the Weighted Relative Squared Error objective :math:`F`:

.. math::

   F = \sum_{m} w_m \left(\frac{\hat{h}_m - \tau_{g, m}}{\tau_{g, m}}\right)^2

where :math:`\hat{h}_m` is the sequence's weighted metric, :math:`\tau_{g, m}` is the group target, and :math:`w_m` is the weight of metric :math:`m` (from ``SynthesisSelectionConfig``).

5. **Selection**: The trial sequence with the lowest objective value :math:`F` is selected. The search terminates early if any trial yields :math:`F < f_{\text{threshold}}` (default 0.05).

7. Assembly and Junction Smoothing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Once the best microtrip sequence is selected for each group, the groups are assembled in order (Low :math:`\to` Med :math:`\to` High :math:`\to` xHigh for WLTP; sorted group ID order for clusters):

* An idle gap (defined by config) is added between groups.
* Adjacent microtrips inside each group are concatenated.
* To avoid physical speed jumps at microtrip junctions, a **linear velocity ramp** is applied over a window of :math:`\text{ramp\_s}` (default 3 seconds):

.. math::

   v_{\text{smooth}}(t) = (1 - \alpha) \cdot v_A(t) + \alpha \cdot v_B(t)

where :math:`\alpha` increases linearly from :math:`0.0` to :math:`1.0` across the junction.

The final consolidated 1 Hz speed profile is returned, containing columns ``t_s`` (elapsed seconds), ``speed_kmh``, and ``group`` (or ``cluster_id``).
