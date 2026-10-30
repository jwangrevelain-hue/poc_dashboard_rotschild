"""Cas de référence tirés du document tarifaire : si un test casse après une
modification de la grille, c'est qu'un prix a changé – volontairement ou non."""
import pytest

from tarification import appliquer_bareme, charger_grille, controler_remise, prix_brut, simuler


@pytest.fixture(scope="module")
def grille():
    return charger_grille()


def test_grille_sans_erreur(grille):
    assert grille.erreurs == []


@pytest.mark.parametrize("valorisation, attendu", [
    (40_000, 160.0),          # 0,40 % sur la 1re tranche
    (50_000, 200.0),
    (150_000, 400.0),         # 200 + 100 000 × 0,20 %
    (500_000, 750.0),         # 200 + 200 + 350 000 × 0,10 %
])
def test_droits_de_garde_par_tranches(grille, valorisation, attendu):
    assert appliquer_bareme(grille.baremes["DROITS_GARDE"], valorisation) == pytest.approx(attendu)


@pytest.mark.parametrize("montant, attendu", [
    (1_000, 5.0),     # « jusqu'à 1 000 € inclus »
    (1_200, 10.0),    # exemple p. 38 : 10 € sur un CIF offre Start
    (3_000, 10.0),
    (10_000, 50.0),   # 0,50 %
    (100_000, 350.0), # 0,35 %
])
def test_ordres_offre_start(grille, montant, attendu):
    assert prix_brut(grille, grille.tarif("BRS-001"), montant) == pytest.approx(attendu)


def test_exemple_p38_plafond_pea(grille):
    profil = {"compte_titres": {"valorisation": 10_000, "enveloppe": "PEA", "offre": "Start",
                                "ordres_en_ligne": 1, "montant_moyen_ordre": 1_200}}
    lignes = {l["tarif_id"]: l for l in simuler(grille, profil)["lignes"]}
    assert lignes["BRS-001"]["brut"] == pytest.approx(6.0)  # 10 € plafonnés à 0,5 % de 1 200 €


def test_change_au_comptant_minimum_et_tranches(grille):
    t = grille.tarif("CPT-014")
    assert prix_brut(grille, t, 10_000) == pytest.approx(18.0)          # 5 € < minimum 18 €
    assert prix_brut(grille, t, 100_000) == pytest.approx(37.5 + 6.25)  # 75 000 × 0,05 % + 25 000 × 0,025 %


def test_minimums_et_maximums(grille):
    assert prix_brut(grille, grille.tarif("CRE-007"), 50_000) == pytest.approx(650.0)     # min. 650 €
    assert prix_brut(grille, grille.tarif("CRE-008"), 200_000) == pytest.approx(2_100.0)  # max. 2 100 €
    assert prix_brut(grille, grille.tarif("PAT-001"), 2_000_000) == pytest.approx(5_000.0)
    assert prix_brut(grille, grille.tarif("INC-003"), 5_000) == pytest.approx(100.0)      # plafond légal 100 €


def test_commission_de_performance(grille):
    t = grille.tarif("GSM-112")  # 0,90 % + 5 % de la performance positive
    assert prix_brut(grille, t, 1_000_000, 8.0) == pytest.approx(9_000 + 4_000)
    assert prix_brut(grille, t, 1_000_000, -3.0) == pytest.approx(9_000)


def test_delegations(grille):
    t = grille.tarif("GSM-103")  # 10 / 25 / 40 %
    assert controler_remise(grille, t, 0).statut == "grille"
    assert controler_remise(grille, t, 10).niveau == "banquier"
    assert controler_remise(grille, t, 15).niveau == "directeur"
    assert controler_remise(grille, t, 40).niveau == "comite"
    assert controler_remise(grille, t, 45).statut == "hors_delegation"
    assert controler_remise(grille, grille.tarif("INC-001"), 50).statut == "verrouille"


def test_remise_sur_tarif_verrouille_non_appliquee(grille):
    s = simuler(grille, {"incidents": {"INC-001": 2}, "remises": {"INC-001": 100}})
    assert s["total_net"] == pytest.approx(16.0)
    assert s["alertes"] == 1


def test_cartes_convention_et_deuxieme_carte(grille):
    avec = simuler(grille, {"convention_bp": True, "cartes": ["CAR-001", "CAR-002"]})
    assert avec["total_brut"] == pytest.approx(1_000.0)  # cartes incluses dans le forfait
    sans = simuler(grille, {"cartes": ["CAR-002", "CAR-003"]})
    assert sans["total_brut"] == pytest.approx(144 + 49.5 / 2)


def test_offre_active_gratuite_au_dela_de_50_ordres(grille):
    base = {"valorisation": 300_000, "enveloppe": "CIF", "offre": "Active", "lignes_porteur": 10,
            "montant_moyen_ordre": 2_000}
    peu = simuler(grille, {"compte_titres": {**base, "ordres_en_ligne": 20}})
    beaucoup = simuler(grille, {"compte_titres": {**base, "ordres_en_ligne": 60}})
    garde = lambda s: sum(l["brut"] for l in s["lignes"] if l["tarif_id"] in {"BRS-010", "BRS-011", "BRS-013"})
    assert garde(peu) == pytest.approx(550 + 50 + 150)  # 200 + 200 + 150 de garde, 10 lignes, abonnement
    assert garde(beaucoup) == 0
