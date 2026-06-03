Similarity Measures
===================

Pluggable similarity measures used by
:py:meth:`~drive_cycle_calculator.TripCollection.similarity_scores` and
:py:meth:`~drive_cycle_calculator.TripCollection.find_representative`.

Any callable that satisfies the :py:class:`~drive_cycle_calculator.similarity.SimilarityMeasure`
protocol can be passed as the ``measure`` argument.

Seven kinematic metrics are compared across trips:

1. ``duration`` — total trip duration (s)
2. ``mean_speed`` — mean speed including stops (km/h)
3. ``mean_speed_no_stops`` — mean speed excluding stops (km/h)
4. ``stop_count`` — number of stops
5. ``stop_pct`` — fraction of time spent stopped
6. ``mean_acceleration`` — mean positive acceleration (m/s²)
7. ``mean_deceleration`` — mean negative acceleration magnitude (m/s²)

Available Measures
------------------

.. automodule:: drive_cycle_calculator.similarity
   :members: SimilarityMeasure, pct_deviation, cosine_similarity, z_score_distance
   :undoc-members: False
