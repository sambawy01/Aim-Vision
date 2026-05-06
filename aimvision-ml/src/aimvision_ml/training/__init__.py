"""Training entry points (heavy: torch + mmpose + mmengine + mmcv).

These modules import torch lazily so the lightweight install path (which
runs the unit tests + eval gates) does not require GPU images.
"""
