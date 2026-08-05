"""
GeoMatchingService - Geographic matching for competitions and players.

Provides functionality to:
- Find gare in a user's province
- Find players in a user's area
- Suggest nearby venues
"""

from __future__ import annotations
from typing import List, Optional, Set, TYPE_CHECKING


from models.location.models import BilliardHall, UserLocationAvailability
from models.competition.models import Gara
from models.status_enum import GaraStatus
from models.base import utc_now

if TYPE_CHECKING:
    from models.user.models import User


class GeoMatchingService:
    """Service for geographic matching of competitions and players."""

    @staticmethod
    def get_user_provinces(user_id: int) -> Set[str]:
        """
        Get provinces where a user has availability set.

        Args:
            user_id: User ID to check

        Returns:
            Set of province codes (e.g., {"RM", "VT"})
        """
        # Get all BilliardHalls where user has availability
        availabilities = UserLocationAvailability.query.filter_by(
            user_id=user_id, is_available=True
        ).all()

        provinces = set()
        for avail in availabilities:
            if avail.billiard_hall and avail.billiard_hall.province:
                provinces.add(avail.billiard_hall.province.upper())

        return provinces

    @staticmethod
    def get_gare_in_provinces(
        provinces: Set[str], status: Optional[str] = None, limit: int = 20
    ) -> List[Gara]:
        """
        Find gare in specified provinces.

        Args:
            provinces: Set of province codes to search
            status: Optional status filter (e.g., 'inscription')
            limit: Maximum number of results

        Returns:
            List of Gara objects in the specified provinces
        """
        if not provinces:
            return []

        # Query gare with billiard_hall in provinces
        query = Gara.query.join(
            BilliardHall, Gara.billiard_hall_id == BilliardHall.id
        ).filter(BilliardHall.province.in_([p.upper() for p in provinces]))

        if status:
            query = query.filter(Gara.status == status)

        # Order by date, most recent first
        query = query.order_by(Gara.date.desc())

        return query.limit(limit).all()

    @staticmethod
    def get_nearby_gare_for_user(
        user_id: int, status: Optional[str] = None, limit: int = 10
    ) -> List[Gara]:
        """
        Get gare near a user based on their availability locations.

        Args:
            user_id: User ID
            status: Optional status filter
            limit: Maximum results

        Returns:
            List of nearby Gara objects
        """
        provinces = GeoMatchingService.get_user_provinces(user_id)
        return GeoMatchingService.get_gare_in_provinces(provinces, status, limit)

    @staticmethod
    def get_open_gare_nearby(user_id: int, limit: int = 5) -> List[Gara]:
        """
        Get gare with open inscriptions near a user.

        Convenience method for dashboard display.

        Args:
            user_id: User ID
            limit: Maximum results

        Returns:
            List of Gara with inscription status in user's area
        """
        provinces = GeoMatchingService.get_user_provinces(user_id)
        if not provinces:
            return []

        now = utc_now()

        # Query gare in inscription period
        query = (
            Gara.query.join(BilliardHall, Gara.billiard_hall_id == BilliardHall.id)
            .filter(
                BilliardHall.province.in_([p.upper() for p in provinces]),
                Gara.status == GaraStatus.INSCRIPTION.value,
                Gara.inscription_start <= now,
                Gara.inscription_end >= now,
            )
            .order_by(Gara.date.asc())
        )

        return query.limit(limit).all()

    @staticmethod
    def get_players_in_province(
        province: str, exclude_user_id: Optional[int] = None
    ) -> List["User"]:
        """
        Find players who have availability in a specific province.

        Args:
            province: Province code (e.g., "RM")
            exclude_user_id: Optional user ID to exclude from results

        Returns:
            List of User objects with availability in province
        """
        from models.user.models import User

        query = (
            User.query.join(
                UserLocationAvailability, User.id == UserLocationAvailability.user_id
            )
            .join(
                BilliardHall,
                UserLocationAvailability.billiard_hall_id == BilliardHall.id,
            )
            .filter(
                BilliardHall.province == province.upper(),
                UserLocationAvailability.is_available.is_(True),
                User.deleted_at.is_(None),
            )
        )

        if exclude_user_id:
            query = query.filter(User.id != exclude_user_id)

        return query.distinct().all()

    @staticmethod
    def get_venues_in_province(
        province: str, verified_only: bool = False
    ) -> List[BilliardHall]:
        """
        Get billiard halls in a specific province.

        Args:
            province: Province code (e.g., "RM")
            verified_only: If True, only return verified venues

        Returns:
            List of BilliardHall objects in province
        """
        query = BilliardHall.query.filter(
            BilliardHall.province == province.upper(), BilliardHall.is_active.is_(True)
        )

        if verified_only:
            query = query.filter(BilliardHall.verified.is_(True))

        return query.order_by(BilliardHall.name).all()


# Italian province codes for reference/validation
ITALIAN_PROVINCES = {
    "AG": "Agrigento",
    "AL": "Alessandria",
    "AN": "Ancona",
    "AO": "Aosta",
    "AR": "Arezzo",
    "AP": "Ascoli Piceno",
    "AT": "Asti",
    "AV": "Avellino",
    "BA": "Bari",
    "BT": "Barletta-Andria-Trani",
    "BL": "Belluno",
    "BN": "Benevento",
    "BG": "Bergamo",
    "BI": "Biella",
    "BO": "Bologna",
    "BZ": "Bolzano",
    "BS": "Brescia",
    "BR": "Brindisi",
    "CA": "Cagliari",
    "CL": "Caltanissetta",
    "CB": "Campobasso",
    "CE": "Caserta",
    "CT": "Catania",
    "CZ": "Catanzaro",
    "CH": "Chieti",
    "CO": "Como",
    "CS": "Cosenza",
    "CR": "Cremona",
    "KR": "Crotone",
    "CN": "Cuneo",
    "EN": "Enna",
    "FM": "Fermo",
    "FE": "Ferrara",
    "FI": "Firenze",
    "FG": "Foggia",
    "FC": "Forlì-Cesena",
    "FR": "Frosinone",
    "GE": "Genova",
    "GO": "Gorizia",
    "GR": "Grosseto",
    "IM": "Imperia",
    "IS": "Isernia",
    "SP": "La Spezia",
    "AQ": "L'Aquila",
    "LT": "Latina",
    "LE": "Lecce",
    "LC": "Lecco",
    "LI": "Livorno",
    "LO": "Lodi",
    "LU": "Lucca",
    "MC": "Macerata",
    "MN": "Mantova",
    "MS": "Massa-Carrara",
    "MT": "Matera",
    "ME": "Messina",
    "MI": "Milano",
    "MO": "Modena",
    "MB": "Monza e Brianza",
    "NA": "Napoli",
    "NO": "Novara",
    "NU": "Nuoro",
    "OR": "Oristano",
    "PD": "Padova",
    "PA": "Palermo",
    "PR": "Parma",
    "PV": "Pavia",
    "PG": "Perugia",
    "PU": "Pesaro e Urbino",
    "PE": "Pescara",
    "PC": "Piacenza",
    "PI": "Pisa",
    "PT": "Pistoia",
    "PN": "Pordenone",
    "PZ": "Potenza",
    "PO": "Prato",
    "RG": "Ragusa",
    "RA": "Ravenna",
    "RC": "Reggio Calabria",
    "RE": "Reggio Emilia",
    "RI": "Rieti",
    "RN": "Rimini",
    "RM": "Roma",
    "RO": "Rovigo",
    "SA": "Salerno",
    "SS": "Sassari",
    "SV": "Savona",
    "SI": "Siena",
    "SR": "Siracusa",
    "SO": "Sondrio",
    "SU": "Sud Sardegna",
    "TA": "Taranto",
    "TE": "Teramo",
    "TR": "Terni",
    "TO": "Torino",
    "TP": "Trapani",
    "TN": "Trento",
    "TV": "Treviso",
    "TS": "Trieste",
    "UD": "Udine",
    "VA": "Varese",
    "VE": "Venezia",
    "VB": "Verbano-Cusio-Ossola",
    "VC": "Vercelli",
    "VR": "Verona",
    "VV": "Vibo Valentia",
    "VI": "Vicenza",
    "VT": "Viterbo",
}


def get_province_name(code: str) -> str:
    """Get full province name from code."""
    return ITALIAN_PROVINCES.get(code.upper(), code)


def is_valid_province(code: str) -> bool:
    """Check if province code is valid."""
    return code.upper() in ITALIAN_PROVINCES
