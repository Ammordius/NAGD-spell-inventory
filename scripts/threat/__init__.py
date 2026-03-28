"""Server-aligned spell hate (CheckAggroAmount) and melee/proc TPS helpers."""

from .check_aggro_amount import check_aggro_amount
from .melee_proc import (
    client_damage_bonus_primary,
    dual_wield_chance_pct,
    get_proc_chance_fraction,
    is_two_hander_skill,
    warrior_aa_map,
)

__all__ = [
    "check_aggro_amount",
    "client_damage_bonus_primary",
    "dual_wield_chance_pct",
    "get_proc_chance_fraction",
    "is_two_hander_skill",
    "warrior_aa_map",
]
