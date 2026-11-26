"""Feature dataset for the listing availability model .

Pure functions and a thin builder. Nothing in this package imports SQLAlchemy: the builder
talks to the database through the small `FrameReader` protocol (see build.py).
"""
