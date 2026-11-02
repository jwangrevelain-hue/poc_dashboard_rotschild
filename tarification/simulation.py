"""Facture annuelle estimée d'un client à partir de son profil.

Le profil est un simple dictionnaire (voir PROFILS_EXEMPLES) ; les remises
négociées sont passées dans profil["remises"] = {id_tarif: remise en %}.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .calcul import Controle, arrondi, controler_remise, prix_brut
from .grille import Grille

CARTES_INCLUSES_CONVENTION = ("CAR-001", "CAR-002")  # Visa Infinite + Visa Premier (p. 25)

# Postes de la facture, contrat par contrat, dans l'ordre d'affichage
POSTES = {
    "relation": "Relation bancaire : convention et cartes",
    "mandat_titres": "Mandat de gestion titres",
    "mandat_assurance": "Mandat d'arbitrage assurance vie",
    "conseil": "Gestion conseillée",
    "compte_titres": "Compte-titres en gestion libre",
    "versements": "Versements assurance vie et PER",
    "flux": "Flux internationaux",
    "services": "Services, crédit et incidents",
}


@dataclass
class Ligne:
    tarif_id: str
    famille: str
    libelle: str
    detail: str
    quantite: float
    brut: float
    remise_pct: float
    net: float
    controle: Controle
    page: int
    poste: str

    def en_dict(self) -> dict:
        d = asdict(self)
        d["controle"] = asdict(self.controle)
        return d


def _eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", " ")


def _pct(x: float) -> str:
    return f"{x:.2f} %".replace(".", ",")


class _Facture:
    def __init__(self, grille: Grille, remises: dict[str, float]):
        self.grille = grille
        self.remises = remises
        self.lignes: list[Ligne] = []
        self.poste = ""  # poste en cours, attribué aux lignes ajoutées

    def ajouter(self, tarif_id: str, detail: str, brut_total: float, quantite: float = 1, remise: float | None = None):
        t = self.grille.tarif(tarif_id)
        r = self.remises.get(tarif_id, 0.0) if remise is None else remise
        if not t.negociable or r < 0:
            r_appliquee = 0.0  # une remise sur un tarif verrouillé, ou négative, est signalée mais pas appliquée
        else:
            r_appliquee = min(r, 100.0)
        self.lignes.append(
            Ligne(
                tarif_id=t.id,
                famille=t.famille,
                libelle=t.libelle,
                detail=detail,
                quantite=quantite,
                brut=arrondi(brut_total),
                remise_pct=r,
                net=arrondi(brut_total * (1 - r_appliquee / 100)),
                controle=controler_remise(self.grille, t, r),
                page=t.page,
                poste=self.poste,
            )
        )


def simuler(grille: Grille, profil: dict) -> dict:
    regles = grille.politique["regles"]
    f = _Facture(grille, profil.get("remises", {}))
    convention = profil.get("convention_bp", False)

    f.poste = "relation"
    if convention:
        t = grille.tarif("CBP-001")
        f.ajouter("CBP-001", "Forfait annuel", prix_brut(grille, t))

    # Cartes : deux cartes incluses dans la convention, réduction de 50 % sur la moins chère de deux cartes sinon
    cartes = list(profil.get("cartes", []))
    if convention:
        for incl in CARTES_INCLUSES_CONVENTION:
            if incl in cartes:
                cartes.remove(incl)
    cartes.sort(key=lambda c: grille.tarif(c).valeur, reverse=True)
    for i, c in enumerate(cartes):
        prix = grille.tarif(c).valeur
        if not convention and i == 1:
            reduction = regles["reduction_deuxieme_carte_pct"]
            f.ajouter(c, f"Cotisation annuelle – 2e carte −{reduction:g} %", prix * (1 - reduction / 100))
        else:
            f.ajouter(c, "Cotisation annuelle", prix)

    # Gestion sous mandat titres
    f.poste = "mandat_titres"
    m = profil.get("mandat_titres")
    if m and m.get("encours"):
        t = grille.tarif(m["offre"])
        perf = 0.0 if m.get("premiere_annee") else m.get("performance_pct", 0.0)
        brut = prix_brut(grille, t, m["encours"], perf)
        detail = f"{_eur(m['encours'])} × {_pct(t.valeur)}"
        if t.perf_pct:
            detail += f" + {t.perf_pct:g} % de la performance ({_pct(perf)})" if perf > 0 else " (pas de commission de performance)"
        f.ajouter(t.id, detail, brut)

    # Mandat d'arbitrage assurance
    f.poste = "mandat_assurance"
    m = profil.get("mandat_assurance")
    if m and m.get("encours"):
        t = grille.tarif(m["offre"])
        perf = 0.0 if m.get("premiere_annee") else m.get("performance_pct", 0.0)
        detail = f"{_eur(m['encours'])} × {_pct(t.valeur)}"
        if t.perf_pct and perf > 0:
            detail += f" + {t.perf_pct:g} % de la performance ({_pct(perf)})"
        f.ajouter(t.id, detail, prix_brut(grille, t, m["encours"], perf))

    # Gestion conseillée
    f.poste = "conseil"
    m = profil.get("conseil")
    if m and m.get("encours"):
        t = grille.tarif(m["offre"])
        f.ajouter(t.id, f"{_eur(m['encours'])} × {_pct(t.valeur)}", prix_brut(grille, t, m["encours"]))

    # Compte-titres en gestion libre
    f.poste = "compte_titres"
    ct = profil.get("compte_titres")
    if ct and ct.get("valorisation"):
        pea = ct.get("enveloppe") == "PEA"
        active = ct.get("offre") == "Active"
        nb_ordres = ct.get("ordres_en_ligne", 0) + ct.get("ordres_agence", 0)
        seuil = regles["offre_active_seuil_ordres_gratuite"]
        gratuite_active = active and nb_ordres >= seuil

        if gratuite_active:
            f.ajouter("BRS-010", f"Offerts : {nb_ordres} ordres ≥ {seuil}", 0.0)
            f.ajouter("BRS-013", f"Offert (≥ {seuil} ordres)", 0.0)
        else:
            proportionnel = prix_brut(grille, grille.tarif("BRS-010"), ct["valorisation"])
            n_porteur = ct.get("lignes_porteur", 0)
            unitaire_porteur = grille.tarif("BRS-011").valeur
            n_nominatif = ct.get("lignes_nominatif", 0)
            unitaire_nominatif = grille.tarif("BRS-012").valeur
            nominatif_plafonne = pea and unitaire_nominatif > regles["pea_plafond_garde_par_ligne_eur"]
            if nominatif_plafonne:
                unitaire_nominatif = regles["pea_plafond_garde_par_ligne_eur"]
            abonnement = grille.tarif("BRS-013").valeur if active else 0.0
            # PEA : droits de garde et frais de gestion plafonnés dans leur ensemble à 0,40 % de la
            # valorisation + 5 € par ligne (p. 38) ; l'excédent est retiré de l'abonnement, puis de la
            # commission proportionnelle.
            abonnement_plafonne = proportionnel_plafonne = False
            if pea:
                plafond = (ct["valorisation"] * regles["pea_plafond_garde_pct"] / 100
                           + (n_porteur + n_nominatif) * regles["pea_plafond_garde_par_ligne_eur"])
                exces = proportionnel + n_porteur * unitaire_porteur + n_nominatif * unitaire_nominatif + abonnement - plafond
                if exces > 0.005 and abonnement > 0:
                    retrait = min(exces, abonnement)
                    abonnement -= retrait
                    exces -= retrait
                    abonnement_plafonne = True
                if exces > 0.005:
                    proportionnel = max(proportionnel - exces, 0.0)
                    proportionnel_plafonne = True

            f.ajouter("BRS-010", f"Barème par tranches sur {_eur(ct['valorisation'])}" + (" (plafond PEA)" if proportionnel_plafonne else ""), proportionnel)
            if n_porteur:
                f.ajouter("BRS-011", f"{n_porteur} lignes × {unitaire_porteur:g} €", n_porteur * unitaire_porteur, quantite=n_porteur)
            if n_nominatif:
                f.ajouter("BRS-012", f"{n_nominatif} lignes × {unitaire_nominatif:g} €" + (" (plafond PEA)" if nominatif_plafonne else ""), n_nominatif * unitaire_nominatif, quantite=n_nominatif)
            if active:
                f.ajouter("BRS-013", "Abonnement annuel" + (" (plafond PEA)" if abonnement_plafonne else ""), abonnement)

        n = ct.get("ordres_en_ligne", 0)
        if n:
            tid = "BRS-002" if active else "BRS-001"
            montant = ct.get("montant_moyen_ordre", 0)
            unitaire = prix_brut(grille, grille.tarif(tid), montant)
            plafonne = pea and unitaire > montant * regles["pea_plafond_transaction_en_ligne_pct"] / 100
            if plafonne:
                unitaire = montant * regles["pea_plafond_transaction_en_ligne_pct"] / 100
            f.ajouter(tid, f"{n} ordres de {_eur(montant)} × {unitaire:.2f} €".replace(".", ",") + (" (plafond PEA)" if plafonne else ""), n * unitaire, quantite=n)
        n = ct.get("ordres_agence", 0)
        if n:
            montant = ct.get("montant_moyen_ordre_agence", ct.get("montant_moyen_ordre", 0))
            unitaire = prix_brut(grille, grille.tarif("BRS-007"), montant)
            plafonne = pea and unitaire > montant * regles["pea_plafond_transaction_autre_pct"] / 100
            if plafonne:
                unitaire = montant * regles["pea_plafond_transaction_autre_pct"] / 100
            f.ajouter("BRS-007", f"{n} ordres de {_eur(montant)} × {unitaire:.2f} €".replace(".", ",") + (" (plafond PEA)" if plafonne else ""), n * unitaire, quantite=n)

    # Assurance vie / PER
    f.poste = "versements"
    for cle, tid in (("versements_av", "AVI-001"), ("versements_per", "AVI-002")):
        montant = profil.get(cle, 0)
        if montant:
            t = grille.tarif(tid)
            f.ajouter(tid, f"{_eur(montant)} versés × {_pct(t.valeur)}", prix_brut(grille, t, montant))

    # Flux internationaux
    f.poste = "flux"
    for cle, tid in (("virements_non_sepa_en_ligne", "VIR-007"), ("virements_non_sepa_agence", "VIR-009")):
        n = profil.get(cle, 0)
        if n:
            t = grille.tarif(tid)
            f.ajouter(tid, f"{n} virements × {t.valeur:g} €", n * t.valeur, quantite=n)
    depenses = profil.get("depenses_hors_zone_euro", 0)
    if depenses:
        nb = max(profil.get("nb_paiements_hors_zone_euro", 1), 1)
        infinite = "CAR-001" in profil.get("cartes", [])
        tid = "CAR-014" if infinite else "CAR-015"
        t = grille.tarif(tid)
        brut = depenses * t.valeur / 100 + nb * t.fixe_eur
        f.ajouter(tid, f"{_eur(depenses)} en {nb} paiements : {_pct(t.valeur)} + {t.fixe_eur:.2f} €/paiement".replace(".", ","), brut, quantite=nb)

    # Services
    f.poste = "services"
    if profil.get("coffre"):
        f.ajouter("CPT-012", "Cotisation annuelle", grille.tarif("CPT-012").valeur)
    n = profil.get("attestations", 0)
    if n:
        f.ajouter("CPT-010", f"{n} attestations", n * grille.tarif("CPT-010").valeur, quantite=n)
    montant = profil.get("credit_immo", 0)
    if montant:
        t = grille.tarif("CRE-007")
        minimum = f" (min. {t.minimum:g} €)" if t.minimum is not None else ""
        f.ajouter("CRE-007", f"{_eur(montant)} × {_pct(t.valeur)}{minimum}", prix_brut(grille, t, montant))
    for tid, n in profil.get("incidents", {}).items():
        if n:
            t = grille.tarif(tid)
            f.ajouter(tid, f"{n} × {t.valeur:g} €".replace(".", ","), n * t.valeur, quantite=n)

    encours = sum(
        (profil.get(k) or {}).get("encours", 0) for k in ("mandat_titres", "mandat_assurance", "conseil")
    ) + (profil.get("compte_titres") or {}).get("valorisation", 0)
    total_brut = arrondi(sum(l.brut for l in f.lignes))
    total_net = arrondi(sum(l.net for l in f.lignes))
    alertes = [l for l in f.lignes if l.controle.statut in {"hors_delegation", "verrouille", "invalide"}]
    niveaux = [l.controle.niveau for l in f.lignes if l.controle.niveau]
    ordre = [d["code"] for d in grille.delegations]
    niveau_requis = max(niveaux, key=ordre.index) if niveaux else None
    return {
        "lignes": [l.en_dict() for l in f.lignes],
        "total_brut": total_brut,
        "total_net": total_net,
        "remise_totale": arrondi(total_brut - total_net),
        "encours": encours,
        "taux_global_pct": round(total_net / encours * 100, 4) if encours else None,
        "niveau_requis": niveau_requis,
        "alertes": len(alertes),
    }


PROFILS_EXEMPLES = {
    "dirigeant": {
        "nom": "Dirigeant cédant – 4,2 M€",
        "convention_bp": True,
        "cartes": ["CAR-001", "CAR-002"],
        "mandat_titres": {"offre": "GSM-103", "encours": 2_500_000, "performance_pct": 6.5},
        "mandat_assurance": {"offre": "GSA-005", "encours": 1_200_000},
        "compte_titres": {
            "valorisation": 500_000, "enveloppe": "CIF", "offre": "Start",
            "lignes_porteur": 18, "lignes_nominatif": 2,
            "ordres_en_ligne": 24, "montant_moyen_ordre": 12_000, "ordres_agence": 3, "montant_moyen_ordre_agence": 40_000,
        },
        "versements_av": 300_000,
        "virements_non_sepa_agence": 6,
        "depenses_hors_zone_euro": 18_000, "nb_paiements_hors_zone_euro": 40,
        "coffre": True,
        "remises": {"GSM-103": 15, "AVI-001": 100, "CBP-001": 50},
    },
    "investisseur_actif": {
        "nom": "Investisseur actif – PEA + CIF 900 k€",
        "convention_bp": True,
        "cartes": ["CAR-001", "CAR-002"],
        "conseil": {"offre": "GCO-002", "encours": 400_000},
        "compte_titres": {
            "valorisation": 500_000, "enveloppe": "PEA", "offre": "Active",
            "lignes_porteur": 35, "lignes_nominatif": 4,
            "ordres_en_ligne": 80, "montant_moyen_ordre": 6_000,
        },
        "versements_per": 30_000,
        "remises": {"GCO-002": 30},
    },
    "jeune_patrimoine": {
        "nom": "Jeune actif – mandat 350 k€, crédit immobilier",
        "convention_bp": False,
        "cartes": ["CAR-002", "CAR-003"],
        "mandat_titres": {"offre": "GSM-112", "encours": 350_000, "performance_pct": 4.0, "premiere_annee": True},
        "compte_titres": {
            "valorisation": 60_000, "enveloppe": "PEA", "offre": "Start",
            "lignes_porteur": 8, "ordres_en_ligne": 12, "montant_moyen_ordre": 1_200,
        },
        "versements_av": 50_000,
        "credit_immo": 450_000,
        "incidents": {"INC-001": 3},
        "remises": {"CRE-007": 60, "INC-001": 100},
    },
}


# Cas limites rejoués par tests/parite.cjs : chemins que ni les exemples ni le portefeuille fictif n'empruntent.
CAS_LIMITES = {
    "remise_negative": {"convention_bp": True, "remises": {"CBP-001": -20}},
    "pea_active_plafond_partiel": {
        "compte_titres": {"valorisation": 100_000, "enveloppe": "PEA", "offre": "Active", "lignes_porteur": 10,
                          "ordres_en_ligne": 30, "montant_moyen_ordre": 2_000},
    },
    "pea_active_plafond_total": {
        "compte_titres": {"valorisation": 20_000, "enveloppe": "PEA", "offre": "Active", "lignes_porteur": 2,
                          "lignes_nominatif": 1, "ordres_en_ligne": 30, "montant_moyen_ordre": 1_000},
    },
    "pea_start_au_plafond": {
        "compte_titres": {"valorisation": 10_000, "enveloppe": "PEA", "offre": "Start", "lignes_porteur": 20},
    },
    "credit_immo_minimum": {"credit_immo": 50_000},
}
