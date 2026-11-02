"""Calcul d'un prix et contrôle des marges de manœuvre."""
from __future__ import annotations

from dataclasses import dataclass

from .grille import Bareme, Grille, Tarif


def arrondi(x: float) -> float:
    return round(x + 1e-9, 2)


def appliquer_bareme(bareme: Bareme, montant: float) -> float:
    if montant <= 0:
        return 0.0
    if bareme.mode == "tranches":
        total = 0.0
        for t in bareme.tranches:
            haut = montant if t.borne_sup is None else min(montant, t.borne_sup)
            if haut > t.borne_inf:
                total += (haut - t.borne_inf) * (t.taux_pct or 0) / 100
        return total
    # palier : le montant entier est tarifé au palier dans lequel il tombe (bornes hautes incluses)
    for t in bareme.tranches:
        if t.borne_sup is None or montant <= t.borne_sup:
            prix = (t.fixe_eur or 0) + montant * (t.taux_pct or 0) / 100
            return max(prix, t.minimum_eur or 0)
    raise AssertionError("barème sans tranche ouverte")


def prix_brut(grille: Grille, tarif: Tarif, assiette: float = 0.0, performance_pct: float = 0.0) -> float:
    """Prix grille, avant remise, pour une unité de la périodicité du tarif.

    assiette : montant de référence pour les tarifs proportionnels (encours, montant d'ordre...).
    performance_pct : performance annuelle du mandat, pour les options « à la performance ».
    """
    t = tarif
    if t.type_tarif == "fixe":
        prix = t.valeur
    elif t.type_tarif == "taux":
        prix = assiette * t.valeur / 100
    elif t.type_tarif == "taux_plus_fixe":
        prix = assiette * t.valeur / 100 + t.fixe_eur
    elif t.type_tarif == "bareme":
        prix = appliquer_bareme(grille.baremes[t.bareme_id], assiette)
    else:  # sur_devis : pas de prix calculable, on prend le minimum du devis
        prix = t.minimum or 0.0
    if t.perf_pct and performance_pct > 0:
        prix += assiette * performance_pct / 100 * t.perf_pct / 100
    if t.minimum is not None and t.type_tarif != "sur_devis":
        prix = max(prix, t.minimum)
    if t.maximum is not None:
        prix = min(prix, t.maximum)
    return prix


@dataclass(frozen=True)
class Controle:
    statut: str  # "grille", "dans_delegation", "hors_delegation", "verrouille", "invalide"
    niveau: str | None  # code de la délégation qui suffit
    message: str


def controler_remise(grille: Grille, tarif: Tarif, remise_pct: float) -> Controle:
    """Qui peut accorder cette remise ? Renvoie le premier niveau suffisant."""
    if remise_pct < 0:
        return Controle("invalide", None, "Remise négative : non appliquée")
    if remise_pct == 0:
        return Controle("grille", None, "Prix grille")
    if not tarif.negociable:
        return Controle("verrouille", None, f"Non négociable : {tarif.motif_verrou}")
    for d in grille.delegations:
        if remise_pct <= tarif.remises_max[d["code"]] + 1e-9:
            return Controle("dans_delegation", d["code"], f"Accordable par : {d['libelle']}")
    plafond = max(tarif.remises_max.values())
    return Controle(
        "hors_delegation",
        None,
        f"Au-delà de la remise maximale autorisée ({plafond:g} %)",
    )


def taux_effectif(tarif: Tarif, remise_pct: float) -> float | None:
    """Taux après remise, pour afficher « 1,20 % → 0,96 % »."""
    if tarif.type_tarif in {"taux", "taux_plus_fixe"} and tarif.valeur is not None:
        return tarif.valeur * (1 - remise_pct / 100)
    return None
