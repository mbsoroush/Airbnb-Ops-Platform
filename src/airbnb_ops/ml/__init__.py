"""Experiment tracking for the listing availability model (stage 5).

Everything here is split so that the training logic can be tested without an MLflow server:
the run helper talks to a small `Tracker` protocol (tracking.py), and only `mlflow_tracker.py`
imports MLflow.
"""
