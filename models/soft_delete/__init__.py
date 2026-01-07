"""
Soft Delete module - provides unified soft delete filtering for multiple models.

Usage:
    from models.soft_delete import register_soft_delete_filters

    # In app.py during initialization
    register_soft_delete_filters(SASession)
"""

from .filter import register_soft_delete_filters

__all__ = ["register_soft_delete_filters"]
