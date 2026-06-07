# -*- coding: utf-8 -*-
"""llm_router — cost-aware multi-provider LLM router with role tiers."""
from .client import (
    active_provider,
    call,
    estimate_cost,
    model_for,
    usage_dict,
)

__all__ = ["call", "model_for", "estimate_cost", "usage_dict", "active_provider"]
__version__ = "0.1.0"
