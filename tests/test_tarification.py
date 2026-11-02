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


def test_remise_negative_signalee_et_non_appliquee(grille):
    s = simuler(grille, {"convention_bp": True, "remises": {"CBP-001": -20}})
    assert s["total_net"] == pytest.approx(s["total_brut"])  # pas de surfacturation
    assert s["lignes"][0]["controle"]["statut"] == "invalide"
    assert s["alertes"] == 1


def _garde(s):
    return {l["tarif_id"]: l for l in s["lignes"] if l["tarif_id"] in {"BRS-010", "BRS-011", "BRS-012", "BRS-013"}}


def test_plafond_pea_garde_et_frais_de_gestion(grille):
    # p. 38 : garde + frais de gestion plafonnés ensemble à 0,40 % de la valorisation + 5 € par ligne
    base = {"valorisation": 100_000, "offre": "Active", "lignes_porteur": 10, "ordres_en_ligne": 30, "montant_moyen_ordre": 2_000}
    pea = _garde(simuler(grille, {"compte_titres": {**base, "enveloppe": "PEA"}}))
    assert sum(l["brut"] for l in pea.values()) == pytest.approx(400 + 50)  # 300 + 50 + 150 = 500, plafonné à 450
    assert pea["BRS-013"]["brut"] == pytest.approx(100)
    assert "plafond PEA" in pea["BRS-013"]["detail"]
    cif = _garde(simuler(grille, {"compte_titres": {**base, "enveloppe": "CIF"}}))
    assert cif["BRS-013"]["brut"] == pytest.approx(150)


def test_plafond_pea_pas_declenche_au_plafond_exact(grille):
    s = _garde(simuler(grille, {"compte_titres": {"valorisation": 10_000, "enveloppe": "PEA", "offre": "Start", "lignes_porteur": 20}}))
    assert sum(l["brut"] for l in s.values()) == pytest.approx(40 + 100)
    assert not any("plafond PEA" in l["detail"] for l in s.values())


def test_libelles_tires_de_la_grille(grille):
    from dataclasses import replace
    from tarification.grille import Grille

    tarifs = {**grille.tarifs, "BRS-011": replace(grille.tarif("BRS-011"), valeur=6.0),
              "CRE-007": replace(grille.tarif("CRE-007"), minimum=700.0)}
    politique = {**grille.politique, "regles": {**grille.politique["regles"], "offre_active_seuil_ordres_gratuite": 40}}
    g = Grille(tarifs=tarifs, baremes=grille.baremes, politique=politique)
    details = lambda p: {l["tarif_id"]: l["detail"] for l in simuler(g, p)["lignes"]}
    ct = {"valorisation": 50_000, "enveloppe": "CIF", "offre": "Start", "lignes_porteur": 3}
    assert details({"compte_titres": ct})["BRS-011"] == "3 lignes × 6 €"
    assert details({"compte_titres": {**ct, "offre": "Active", "ordres_en_ligne": 45}})["BRS-013"] == "Offert (≥ 40 ordres)"
    assert details({"credit_immo": 50_000})["CRE-007"].endswith("(min. 700 €)")


def test_build_sans_modification_ne_change_pas_les_sorties(grille, tmp_path):
    from tarification.export import donnees_dashboard, ecrire_excel, ecrire_json, reprendre_horodatage

    def construire(g, horodatage):
        d = donnees_dashboard(g, 20)
        d["meta"]["genere_le"] = horodatage
        reprendre_horodatage(d, tmp_path / "donnees.json")
        ecrire_json(d, tmp_path / "donnees.json")
        ecrire_excel(g, d, tmp_path / "grille.xlsx")
        return d["meta"]["genere_le"], (tmp_path / "grille.xlsx").read_bytes()

    premier = construire(grille, "2026-07-01 09:00")
    assert construire(grille, "2026-07-02 10:00") == premier  # rien n'a changé : horodatage et classeur repris

    from dataclasses import replace
    from tarification.grille import Grille
    modifiee = Grille(tarifs={**grille.tarifs, "BRS-011": replace(grille.tarif("BRS-011"), valeur=6.0)},
                      baremes=grille.baremes, politique=grille.politique)
    assert construire(modifiee, "2026-07-03 11:00")[0] == "2026-07-03 11:00"


def test_chaque_ligne_rattachee_a_son_poste(grille):
    from tarification.simulation import POSTES, PROFILS_EXEMPLES

    ordre = list(POSTES)
    for profil in PROFILS_EXEMPLES.values():
        postes = [l["poste"] for l in simuler(grille, profil)["lignes"]]
        assert postes == sorted(postes, key=ordre.index)  # un bloc par poste, dans l'ordre d'affichage
    lignes = simuler(grille, PROFILS_EXEMPLES["dirigeant"])["lignes"]
    par_tarif = {l["tarif_id"]: l["poste"] for l in lignes}
    assert par_tarif["CBP-001"] == "relation"
    assert par_tarif[PROFILS_EXEMPLES["dirigeant"]["mandat_titres"]["offre"]] == "mandat_titres"
    assert par_tarif["BRS-010"] == "compte_titres"
