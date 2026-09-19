"""Utility module for managing image paths consistently across the application."""

import os
import shutil
import uuid
from typing import Optional
from flask import current_app
from PIL import Image


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

    # Banner-specific methods (vetrina social, issue #235)
    @staticmethod
    def get_banner_upload_dir() -> str:
        """Get the absolute filesystem path for banner uploads."""
        return ImagePathManager._get_upload_dir("BANNER_UPLOAD_FOLDER", "banners")

    @staticmethod
    def get_banner_db_path(filename: str) -> str:
        """Get the database path for a banner image (relative to static folder)."""
        return ImagePathManager._get_db_path(
            "BANNER_UPLOAD_FOLDER", "banners", filename
        )

    @staticmethod
    def get_banner_url_path(filename: str) -> str:
        """Get the URL path for a banner image (for use in templates)."""
        return ImagePathManager._get_url_path(
            "BANNER_UPLOAD_FOLDER", "banners", filename
        )

    @staticmethod
    def ensure_banner_upload_dir() -> None:
        """Ensure the banner upload directory exists."""
        os.makedirs(ImagePathManager.get_banner_upload_dir(), exist_ok=True)

    @staticmethod
    def url_from_db_path(db_path: str) -> str:
        """Da percorso salvato su DB a URL, per qualsiasi tipo di immagine.

        La conversione non dipende dal tipo: è la stessa normalizzazione dei
        tre formati storici (assoluto, `static/…`, nudo) che
        `get_challenge_url_path_from_db_path` faceva già, con un nome che non
        promette di riguardare solo gli esercizi.
        """
        return ImagePathManager.get_challenge_url_path_from_db_path(db_path)

    # Private helper methods
    @staticmethod
    def _get_upload_dir(config_key: str, default_folder: str) -> str:
        """Get the absolute filesystem path for uploads."""
        upload_base = current_app.config.get("UPLOAD_BASE_PATH", "static/uploads")
        # Remove static/ if present since current_app.static_folder already points to
        # static/
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
        """
        Get the database path for an image (includes static/ prefix for consistency).
        """
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
    def save_challenge_image(  # type: ignore[no-untyped-def]
        image_file,
    ) -> Optional[str]:
        """Save an uploaded challenge image with resizing and JPEG optimization.

        Returns the generated filename on success, or None on failure.
        """
        if not image_file or not ImagePathManager.is_allowed_file(image_file.filename):
            return None

        filename = f"{uuid.uuid4().hex}.jpg"
        ImagePathManager.ensure_challenge_upload_dir()
        upload_dir = ImagePathManager.get_challenge_upload_dir()
        filepath = os.path.join(upload_dir, filename)

        try:
            with Image.open(image_file) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.thumbnail((800, 600), Image.Resampling.LANCZOS)
                img.save(filepath, "JPEG", quality=85, optimize=True, progressive=True)
            return filename
        except Exception as e:
            if os.path.exists(filepath):
                os.remove(filepath)
            current_app.logger.error(f"Failed to process challenge image: {e}")
            return None

    @staticmethod
    def copy_challenge_image(image_filename: Optional[str]) -> Optional[str]:
        """Duplica il file di un'immagine e restituisce il nome della copia.

        Una copia di un esercizio vuole un file **suo**: risalvare un disegno
        cancella l'immagine di prima, quindi due esercizi sullo stesso file
        vuol dire che ritoccando l'uno si spegne l'altro (#253).

        ``None`` se l'originale non c'è sul disco: chi chiama decide il ripiego.
        """
        if not image_filename:
            return None
        upload_dir = ImagePathManager.get_challenge_upload_dir()
        source = os.path.join(upload_dir, os.path.basename(image_filename))
        if not os.path.isfile(source):
            return None
        estensione = os.path.splitext(source)[1] or ".jpg"
        filename = f"{uuid.uuid4().hex}{estensione}"
        try:
            shutil.copyfile(source, os.path.join(upload_dir, filename))
        except OSError as e:
            current_app.logger.error(f"Failed to copy challenge image: {e}")
            return None
        return filename

    @staticmethod
    def delete_challenge_image(image_filename: Optional[str]) -> None:
        """Delete a challenge image file from disk."""
        if not image_filename:
            return
        upload_dir = ImagePathManager.get_challenge_upload_dir()
        filepath = os.path.join(upload_dir, image_filename)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                current_app.logger.info(f"Deleted challenge image: {image_filename}")
        except Exception as e:
            current_app.logger.error(
                f"Failed to delete challenge image {image_filename}: {e}"
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
