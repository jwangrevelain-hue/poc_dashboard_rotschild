"""Portefeuille fictif pour la vue pilotage : revenus, remises et dérogations.

Les clients sont générés aléatoirement (graine fixe) : aucun client réel.
"""
from __future__ import annotations

import random

from .grille import Grille
from .simulation import simuler

CENTRES = ["Paris Étoile", "Paris Rive Gauche", "Neuilly", "Lyon", "Bordeaux", "Strasbourg"]
MANDATS_TITRES = ["GSM-101", "GSM-102", "GSM-103", "GSM-104", "GSM-105", "GSM-106", "GSM-112", "GSM-113", "GSM-115"]
MANDATS_ASSURANCE = ["GSA-001", "GSA-002", "GSA-003", "GSA-004", "GSA-005", "GSA-007", "GSA-012"]


def _tirer_remise(rng: random.Random, grille: Grille, tarif_id: str) -> float:
    """Distribution plausible : la plupart au prix grille, quelques dépassements de délégation."""
    t = grille.tarif(tarif_id)
    if not t.negociable:
        return 0.0
    r = [t.remises_max[d["code"]] for d in grille.delegations]
    u = rng.random()
    if u < 0.50:
        return 0.0
    if u < 0.78:
        return round(rng.uniform(0.3, 1.0) * r[0]) if r[0] else 0.0
    if u < 0.92:
        return round(rng.uniform(r[0], r[1])) if r[1] > r[0] else float(r[1])
    if u < 0.97:
        return round(rng.uniform(r[1], r[2])) if r[2] > r[1] else float(r[2])
    return min(100.0, round(r[2] + rng.uniform(5, 15)))  # dérogation hors délégation


def generer_clients(grille: Grille, n: int = 240, graine: int = 2026) -> list[dict]:
    rng = random.Random(graine)
    clients = []
    for i in range(1, n + 1):
        patrimoine = rng.lognormvariate(14.4, 0.75)  # médiane ≈ 1,8 M€
        patrimoine = min(max(patrimoine, 300_000), 40_000_000)
        p: dict = {
            "id": f"CLI-{i:04d}",
            "centre": rng.choice(CENTRES),
            "convention_bp": patrimoine >= 750_000 or rng.random() < 0.3,
            "remises": {},
        }
        p["cartes"] = ["CAR-001", "CAR-002"] if p["convention_bp"] else rng.choice([["CAR-002"], ["CAR-002", "CAR-003"], ["CAR-001"]])
        reste = patrimoine
        if rng.random() < 0.65:
            part = rng.uniform(0.25, 0.55)
            p["mandat_titres"] = {
                "offre": rng.choice(MANDATS_TITRES),
                "encours": round(patrimoine * part, -3),
                "performance_pct": round(rng.uniform(-4, 11), 1),
            }
            reste -= p["mandat_titres"]["encours"]
        if rng.random() < 0.55:
            part = rng.uniform(0.2, 0.45)
            p["mandat_assurance"] = {"offre": rng.choice(MANDATS_ASSURANCE), "encours": round(patrimoine * part, -3)}
            reste -= p["mandat_assurance"]["encours"]
        if rng.random() < 0.25:
            p["conseil"] = {"offre": rng.choice(["GCO-001", "GCO-002"]), "encours": round(max(reste, 0) * 0.5, -3)}
            reste -= p["conseil"]["encours"]
        if reste > 20_000 and rng.random() < 0.8:
            active = rng.random() < 0.3
            p["compte_titres"] = {
                "valorisation": round(reste * rng.uniform(0.4, 0.9), -3),
                "enveloppe": "PEA" if rng.random() < 0.25 else "CIF",
                "offre": "Active" if active else "Start",
                "lignes_porteur": rng.randint(4, 40),
                "lignes_nominatif": rng.randint(0, 3),
                "ordres_en_ligne": rng.randint(30, 120) if active else rng.randint(0, 25),
                "montant_moyen_ordre": round(rng.uniform(1_500, 25_000), -2),
                "ordres_agence": rng.randint(0, 4),
                "montant_moyen_ordre_agence": round(rng.uniform(5_000, 60_000), -3),
            }
        if rng.random() < 0.45:
            p["versements_av"] = round(patrimoine * rng.uniform(0.02, 0.12), -3)
        if rng.random() < 0.3:
            p["virements_non_sepa_agence"] = rng.randint(1, 12)
        if rng.random() < 0.5:
            p["depenses_hors_zone_euro"] = round(rng.uniform(2_000, 40_000), -2)
            p["nb_paiements_hors_zone_euro"] = rng.randint(5, 80)
        p["coffre"] = rng.random() < 0.2
        if rng.random() < 0.08:
            p["credit_immo"] = round(rng.uniform(200_000, 2_000_000), -4)

        # Remises négociées sur les lignes qui pèsent dans la facture
        brute = simuler(grille, {**p, "remises": {}})
        for l in brute["lignes"]:
            if l["brut"] >= 100:
                r = _tirer_remise(rng, grille, l["tarif_id"])
                if r:
                    p["remises"][l["tarif_id"]] = r
        p["patrimoine"] = round(patrimoine, -3)
        clients.append(p)
    return clients


def agreger(grille: Grille, clients: list[dict]) -> dict:
    codes = [d["code"] for d in grille.delegations]
    par_famille: dict[str, dict] = {}
    par_niveau = {c: {"lignes": 0, "remise": 0.0} for c in [*codes, "hors_delegation"]}
    par_centre: dict[str, dict] = {}
    derogations = []
    lignes_clients = []
    for c in clients:
        s = simuler(grille, c)
        lignes_clients.append({
            "id": c["id"], "centre": c["centre"], "patrimoine": c["patrimoine"],
            "encours": s["encours"], "brut": s["total_brut"], "net": s["total_net"],
            "remise": s["remise_totale"], "taux_global_pct": s["taux_global_pct"],
            "niveau_requis": s["niveau_requis"], "alertes": s["alertes"],
        })
        pc = par_centre.setdefault(c["centre"], {"clients": 0, "brut": 0.0, "net": 0.0, "alertes": 0})
        pc["clients"] += 1
        pc["brut"] += s["total_brut"]
        pc["net"] += s["total_net"]
        pc["alertes"] += s["alertes"]
        for l in s["lignes"]:
            pf = par_famille.setdefault(l["famille"], {"brut": 0.0, "net": 0.0})
            pf["brut"] += l["brut"]
            pf["net"] += l["net"]
            ctl = l["controle"]
            remise = l["brut"] - l["net"]
            if ctl["statut"] == "dans_delegation":
                par_niveau[ctl["niveau"]]["lignes"] += 1
                par_niveau[ctl["niveau"]]["remise"] += remise
            elif ctl["statut"] == "hors_delegation":
                par_niveau["hors_delegation"]["lignes"] += 1
                par_niveau["hors_delegation"]["remise"] += remise
                derogations.append({
                    "client": c["id"], "centre": c["centre"], "tarif_id": l["tarif_id"], "libelle": l["libelle"],
                    "remise_pct": l["remise_pct"], "manque_a_gagner": round(remise, 2),
                    "plafond_pct": max(grille.tarif(l["tarif_id"]).remises_max.values()),
                })
    derogations.sort(key=lambda d: -d["manque_a_gagner"])
    total_brut = sum(x["brut"] for x in lignes_clients)
    total_net = sum(x["net"] for x in lignes_clients)
    return {
        "nb_clients": len(clients),
        "encours_total": sum(x["encours"] for x in lignes_clients),
        "revenu_brut": round(total_brut, 2),
        "revenu_net": round(total_net, 2),
        "remise_totale": round(total_brut - total_net, 2),
        "par_famille": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in sorted(par_famille.items(), key=lambda kv: -kv[1]["brut"])},
        "par_niveau": {k: {"lignes": v["lignes"], "remise": round(v["remise"], 2)} for k, v in par_niveau.items()},
        "par_centre": {k: {**v, "brut": round(v["brut"], 2), "net": round(v["net"], 2)} for k, v in sorted(par_centre.items())},
        "derogations_hors_delegation": derogations,
        "clients": lignes_clients,
    }
