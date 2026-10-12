"""Calibration and climate-context validation.

Preregistered in ``docs/magdalena-validation/calibration-preregistration.md``. ``fetch`` snapshots
every raw input with SHA-256 (network); ``run`` recomputes every result from those snapshots
(offline, also in CI); ``verify`` compares a recomputation with the committed MANIFEST.
"""
