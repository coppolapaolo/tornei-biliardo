"""Utility module for managing image paths consistently across the application."""

import os
from typing import Optional
from flask import current_app


class ImagePathManager:
    """Centralized manager for image path operations."""

    # Challenge-specific methods
    @staticmethod
    def get_challenge_upload_dir() -> str:
        """Get the absolute filesystem path for challenge uploads."""
        return ImagePathManager._get_upload_dir("CHALLENGE_UPLOAD_FOLDER", "challenges")

    @staticmethod
    def get_challenge_db_path(filename: str) -> str:
        """Get the database path for a challenge image (relative to static folder)."""
        return ImagePathManager._get_db_path(
            "CHALLENGE_UPLOAD_FOLDER", "challenges", filename
        )

    @staticmethod
    def get_challenge_url_path(filename: str) -> str:
        """Get the URL path for a challenge image (for use in templates)."""
        return ImagePathManager._get_url_path(
            "CHALLENGE_UPLOAD_FOLDER", "challenges", filename
        )

    @staticmethod
    def get_challenge_url_path_from_db_path(db_path: str) -> str:
        """Convert database path to URL path for templates."""
        if db_path.startswith("/"):
            return db_path
        # If path already starts with static/, just add the leading slash
        if db_path.startswith("static/"):
            return f"/{db_path}"
        # Otherwise, assume it's a legacy format without static/ prefix
        return f"/static/{db_path}"

    @staticmethod
    def ensure_challenge_upload_dir() -> None:
        """Ensure the challenge upload directory exists."""
        upload_dir = ImagePathManager.get_challenge_upload_dir()
        os.makedirs(upload_dir, exist_ok=True)

    # Venue-specific methods
    @staticmethod
    def get_venue_upload_dir() -> str:
        """Get the absolute filesystem path for venue uploads."""
        return ImagePathManager._get_upload_dir("VENUE_UPLOAD_FOLDER", "venues")

    @staticmethod
    def get_venue_db_path(filename: str) -> str:
        """Get the database path for a venue image (relative to static folder)."""
        return ImagePathManager._get_db_path("VENUE_UPLOAD_FOLDER", "venues", filename)

    @staticmethod
    def get_venue_url_path(filename: str) -> str:
        """Get the URL path for a venue image (for use in templates)."""
        return ImagePathManager._get_url_path("VENUE_UPLOAD_FOLDER", "venues", filename)

    @staticmethod
    def ensure_venue_upload_dir() -> None:
        """Ensure the venue upload directory exists."""
        upload_dir = ImagePathManager.get_venue_upload_dir()
        os.makedirs(upload_dir, exist_ok=True)

    # Private helper methods
    @staticmethod
    def _get_upload_dir(config_key: str, default_folder: str) -> str:
        """Get the absolute filesystem path for uploads."""
        upload_base = current_app.config.get("UPLOAD_BASE_PATH", "static/uploads")
        # Remove static/ if present since current_app.static_folder already points to static/
        if upload_base.startswith("static/"):
            upload_base = upload_base.replace("static/", "")

        static_folder = current_app.static_folder
        if static_folder is None:
            raise ValueError("Flask app static_folder is not configured")

        return os.path.join(
            static_folder,
            upload_base,
            current_app.config.get(config_key, default_folder),
        )

    @staticmethod
    def _get_db_path(config_key: str, default_folder: str, filename: str) -> str:
        """Get the database path for an image (includes static/ prefix for consistency)."""
        upload_base = current_app.config.get("UPLOAD_BASE_PATH", "static/uploads")
        subfolder = current_app.config.get(config_key, default_folder)
        return f"{upload_base}/{subfolder}/{filename}"

    @staticmethod
    def _get_url_path(config_key: str, default_folder: str, filename: str) -> str:
        """Get the URL path for an image (for use in templates)."""
        upload_base = current_app.config.get("UPLOAD_BASE_PATH", "static/uploads")
        subfolder = current_app.config.get(config_key, default_folder)
        return f"/{upload_base}/{subfolder}/{filename}"

    @staticmethod
    def get_allowed_extensions() -> set:
        """Get allowed file extensions for uploads."""
        return current_app.config.get(
            "ALLOWED_EXTENSIONS", {"png", "jpg", "jpeg", "gif"}
        )

    @staticmethod
    def is_allowed_file(filename: str) -> bool:
        """Check if filename has an allowed extension."""
        allowed_extensions = ImagePathManager.get_allowed_extensions()
        return (
            "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions
        )

    @staticmethod
    def extract_filename_from_path(image_path: Optional[str]) -> Optional[str]:
        """Extract filename from database image path."""
        if not image_path:
            return None
        return os.path.basename(image_path)


# Template functions for Jinja2
def challenge_image_url(challenge) -> str:
    """Jinja2 template function to get challenge image URL."""
    if not challenge or not challenge.image_path:
        return ""
    return ImagePathManager.get_challenge_url_path_from_db_path(challenge.image_path)


def challenge_image_filename(challenge) -> str:
    """Jinja2 template function to get challenge image filename."""
    if not challenge or not challenge.image_path:
        return ""
    filename = ImagePathManager.extract_filename_from_path(challenge.image_path)
    return filename or ""
