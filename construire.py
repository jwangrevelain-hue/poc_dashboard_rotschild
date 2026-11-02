"""Point d'entrée unique : valide la grille puis régénère le dashboard et l'export Excel.

    python construire.py            # valide + exporte
    python construire.py --valider  # contrôle seul (à brancher en CI ou avant un commit)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tarification import charger_grille
from tarification.export import donnees_dashboard, ecrire_excel, ecrire_json, reprendre_horodatage

RACINE = Path(__file__).resolve().parent
SORTIE = RACINE / "sortie"
DASHBOARD = RACINE / "dashboard"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--valider", action="store_true", help="contrôler la grille sans rien exporter")
    parser.add_argument("--clients", type=int, default=240, help="taille du portefeuille fictif")
    args = parser.parse_args()

    grille = charger_grille()
    if grille.erreurs:
        print(f"✗ {len(grille.erreurs)} erreur(s) dans la grille :")
        for e in grille.erreurs:
            print(f"  - {e}")
        return 1
    print(f"✓ Grille valide : {len(grille.tarifs)} tarifs, {len(grille.baremes)} barèmes")
    if args.valider:
        return 0

    donnees = donnees_dashboard(grille, args.clients)
    reprendre_horodatage(donnees, SORTIE / "donnees.json")
    ecrire_json(donnees, SORTIE / "donnees.json")
    ecrire_excel(grille, donnees, SORTIE / "grille_tarifaire.xlsx")
    gabarit = (DASHBOARD / "gabarit.html").read_text(encoding="utf-8")
    moteur = (DASHBOARD / "moteur.js").read_text(encoding="utf-8")
    import json
    page = gabarit.replace("/*__MOTEUR__*/", moteur).replace(
        "/*__DONNEES__*/null", json.dumps(donnees, ensure_ascii=False).replace("</", "<\\/")
    )
    (SORTIE / "dashboard.html").write_text(page, encoding="utf-8")
    p = donnees["portefeuille"]
    print(f"✓ Portefeuille fictif : {p['nb_clients']} clients, revenu grille {p['revenu_brut']:,.0f} €, "
          f"net {p['revenu_net']:,.0f} €, {len(p['derogations_hors_delegation'])} dérogations hors délégation")
    print(f"✓ Exports : {SORTIE / 'dashboard.html'}, {SORTIE / 'grille_tarifaire.xlsx'}, {SORTIE / 'donnees.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
