"""Data-driven screening of candidate river reaches for Sentinel-2 turbidity monitoring.

Stage 1 reads only the scene classification layer (SCL) to measure how often each reach can be
observed; stage 2 computes the Normalized Difference Turbidity Index (NDTI, a relative index) on
the best reaches and checks documented events against it. The method is pre-registered in
``docs/site-screening/method.md``; every threshold lives in ``pipeline/screening.yaml`` and every
site in ``pipeline/sites/``.
"""
