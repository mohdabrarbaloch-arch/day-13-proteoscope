"""Proteoscope's structure engine.

A deterministic, explainable protein structure *analysis* pipeline. It is not
AlphaFold and does not pretend to be: there are no learned weights and no
network calls. Every number it produces comes from a published scale or a
stated heuristic, so any result can be reproduced by hand.

The pipeline, in order:

    sequence  ->  properties  ->  secondary structure  ->  contacts
              ->  3D trace + relaxation  ->  per-residue confidence

Each stage lives in its own module and is independently testable.
"""

from app.engine.predict import ENGINE_NAME, ENGINE_VERSION, predict_structure

__all__ = ["ENGINE_NAME", "ENGINE_VERSION", "predict_structure"]