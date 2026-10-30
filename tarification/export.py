"""Exports : JSON pour le dashboard, classeur Excel pour l'existant."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .grille import Grille
from .portefeuille import agreger, generer_clients
from .simulation import PROFILS_EXEMPLES, simuler


def donnees_dashboard(grille: Grille, nb_clients: int = 240) -> dict:
    clients = generer_clients(grille, nb_clients)
    return {
        "meta": {
            "source": grille.politique["document"]["source"],
            "date_effet": grille.politique["document"]["date_effet"],
            "genere_le": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "nb_tarifs": len(grille.tarifs),
            "nb_baremes": len(grille.baremes),
        },
        "delegations": grille.delegations,
        "regles": grille.politique["regles"],
        "tarifs": [asdict(t) for t in grille.tarifs.values()],
        "baremes": {b.id: asdict(b) for b in grille.baremes.values()},
        "exemples": {k: {"profil": p, "resultat": simuler(grille, p)} for k, p in PROFILS_EXEMPLES.items()},
        "portefeuille": agreger(grille, clients),
        "profils_portefeuille": clients,
    }


def ecrire_json(donnees: dict, chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")


_ENTETE = Font(bold=True, color="FFFFFF")
_FOND = PatternFill("solid", fgColor="1F4E46")
_AVERT = Font(italic=True, color="7A5C00")


def _feuille(wb: Workbook, titre: str, colonnes: list[tuple[str, int]], lignes: list[list], avertissement: str):
    ws = wb.create_sheet(titre)
    ws.append([avertissement])
    ws["A1"].font = _AVERT
    ws.append([c for c, _ in colonnes])
    for i, (_, largeur) in enumerate(colonnes, start=1):
        cell = ws.cell(row=2, column=i)
        cell.font, cell.fill = _ENTETE, _FOND
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = largeur
    for l in lignes:
        ws.append(l)
    ws.freeze_panes = "B3"
    ws.auto_filter.ref = f"A2:{get_column_letter(len(colonnes))}{ws.max_row}"
    return ws


def ecrire_excel(grille: Grille, donnees: dict, chemin: Path) -> None:
    avert = (
        f"Généré automatiquement le {donnees['meta']['genere_le']} depuis data/grille_tarifaire.csv – "
        "ne pas modifier ce fichier : modifier la grille puis relancer « python construire.py »."
    )
    wb = Workbook()
    wb.remove(wb.active)
    codes = [d["code"] for d in grille.delegations]
    libelles = {d["code"]: d["libelle"] for d in grille.delegations}

    lignes = []
    for t in grille.tarifs.values():
        lignes.append([
            t.id, t.famille, t.rubrique, t.libelle, t.type_tarif, t.valeur, t.fixe_eur, t.perf_pct, t.unite,
            t.assiette, t.periodicite, t.minimum, t.maximum, t.bareme_id, t.canal, t.statut, t.page,
            "oui" if t.negociable else "non", *[t.remises_max[c] if t.negociable else None for c in codes],
            t.motif_verrou, t.note,
        ])
    _feuille(wb, "Grille", [
        ("ID", 10), ("Famille", 22), ("Rubrique", 26), ("Libellé", 52), ("Type", 13), ("Valeur", 9), ("Fixe €", 8),
        ("Perf. %", 8), ("Unité", 7), ("Assiette", 16), ("Périodicité", 11), ("Min.", 8), ("Max.", 8), ("Barème", 20),
        ("Canal", 10), ("Statut", 13), ("Page", 6), ("Négociable", 10),
        *[(f"Remise max {libelles[c]} (%)", 14) for c in codes], ("Motif de verrouillage", 34), ("Note", 46),
    ], lignes, avert)

    lignes = []
    for b in grille.baremes.values():
        for tr in b.tranches:
            lignes.append([b.id, b.mode, tr.borne_inf, tr.borne_sup, tr.taux_pct, tr.fixe_eur, tr.minimum_eur, b.page, tr.libelle])
    _feuille(wb, "Barèmes", [("Barème", 24), ("Mode", 10), ("De (€)", 10), ("À (€)", 10), ("Taux %", 8), ("Fixe €", 8),
                              ("Minimum €", 10), ("Page", 6), ("Libellé", 50)], lignes, avert)

    lignes = []
    for t in grille.tarifs.values():
        if not t.negociable or t.valeur is None:
            continue
        unite = "%" if t.unite == "PCT" else "€"
        lignes.append([t.id, t.libelle, f"{t.valeur:g} {unite}",
                       *[f"{t.valeur * (1 - t.remises_max[c] / 100):.4g} {unite}" for c in codes]])
    _feuille(wb, "Délégations", [("ID", 10), ("Libellé", 52), ("Prix grille", 12),
                                  *[(f"Plancher {libelles[c]}", 18) for c in codes]], lignes, avert)

    lignes = []
    for cle, ex in donnees["exemples"].items():
        for l in ex["resultat"]["lignes"]:
            lignes.append([ex["profil"]["nom"], l["tarif_id"], l["libelle"], l["detail"], l["brut"], l["remise_pct"],
                           l["net"], l["controle"]["message"]])
        lignes.append([ex["profil"]["nom"], "TOTAL", "", "", ex["resultat"]["total_brut"], None, ex["resultat"]["total_net"], ""])
    _feuille(wb, "Simulations", [("Client", 36), ("ID", 10), ("Libellé", 48), ("Détail", 46), ("Brut €", 12),
                                  ("Remise %", 9), ("Net €", 12), ("Contrôle de délégation", 36)], lignes, avert)

    lignes = [[c["id"], c["centre"], c["patrimoine"], c["encours"], c["brut"], c["net"], c["remise"],
               c["taux_global_pct"], libelles.get(c["niveau_requis"], "–"), c["alertes"]]
              for c in donnees["portefeuille"]["clients"]]
    ws = _feuille(wb, "Portefeuille fictif", [("Client", 10), ("Centre", 18), ("Patrimoine €", 14), ("Encours tarifé €", 16),
                                               ("Revenu grille €", 14), ("Revenu net €", 14), ("Remises €", 12), ("Taux global %", 12),
                                               ("Niveau requis", 18), ("Alertes", 8)], lignes, avert)
    for row in ws.iter_rows(min_row=3, min_col=3, max_col=7):
        for cell in row:
            cell.number_format = "# ##0"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    wb.save(chemin)
