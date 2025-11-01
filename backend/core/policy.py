from __future__ import annotations

from dataclasses import dataclass


TH_LOW: float = 0.15
TH_HIGH: float = 0.35


@dataclass
class PolicyHint:
    label: str
    note: str


def policy_from_p(p_crash: float) -> PolicyHint:
    if p_crash >= TH_HIGH:
        return PolicyHint("DEFENSIVE", "Risque eleve: reduire l'exposition, proteger le capital.")
    if p_crash >= TH_LOW:
        return PolicyHint("NEUTRE", "Risque modere: gestion prudente, taille reduite.")
    return PolicyHint("OPPORTUNISTE", "Risque faible: rester expose avec prudence.")

