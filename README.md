# Pilote de tarification Banque Privée (POC)

Montrer qu'un tableau de bord alimenté par une grille de données peut remplacer le classeur Excel de tarification d'une banque, sans perdre la souplesse des marges de manœuvre.

La grille reprend les prix publics de **BNP Paribas Banque Privée – Conditions et tarifs au 1er juillet 2026** (`conditions-juillet-2026.pdf`). Les remises maximales par niveau de délégation et le portefeuille de 240 clients sont **fictifs**, pour la démonstration.

## Démarrer

```bash
pip install -r requirements.txt
python construire.py              # valide la grille puis régénère sortie/
open sortie/dashboard.html        # le tableau de bord, autonome, sans serveur
```

## Organisation

```
data/
  grille_tarifaire.csv   179 tarifs : prix, assiette, min/max, page source, remises max par niveau
  baremes.csv            7 barèmes (droits de garde, ordres de Bourse, change, chèques étrangers…)
  politique.toml         niveaux de délégation et règles transverses (2e carte, plafonds PEA, offre Active)
tarification/
  grille.py              chargement + contrôles de cohérence
  calcul.py              prix d'un tarif, barèmes, contrôle d'une remise contre les délégations
  simulation.py          facture annuelle d'un profil client
  portefeuille.py        portefeuille fictif et agrégats de pilotage
  export.py              JSON du dashboard, classeur Excel
dashboard/
  gabarit.html           la page (pilotage, simulateur, grille, méthode)
  moteur.js              le même moteur de calcul, côté navigateur
tests/
  test_tarification.py   cas de référence tirés du document (exemple p. 38, barèmes, minimums…)
  parite.cjs             vérifie que le navigateur calcule exactement comme Python
  verifier_sources.py    vérifie que chaque valeur de la grille figure sur la page citée du PDF
construire.py            point d'entrée unique
sortie/                  fichiers générés : ne pas modifier à la main
```

## Modifier un tarif

1. Changer la valeur dans `data/grille_tarifaire.csv`.
2. `python construire.py` : si la grille est incohérente (unité inconnue, barème troué, délégations décroissantes, tarif verrouillé sans motif…), la liste des erreurs s'affiche et rien n'est régénéré.
3. Le dashboard et l'export Excel sont à jour.

Contrôles complets :

```bash
python -m pytest tests                                   # cas de référence
node tests/parite.cjs                                    # parité Python / navigateur
python tests/verifier_sources.py conditions-juillet-2026.pdf   # valeurs vs PDF (nécessite pdftotext)
```

## Marges de manœuvre

Chaque tarif négociable porte trois colonnes `remise_banquier_pct`, `remise_directeur_pct`, `remise_comite_pct` : la remise maximale, en % du prix grille, que chaque niveau peut accorder. Une remise saisie est rattachée au premier niveau suffisant ; au-delà du comité, elle est signalée « hors délégation ». Les tarifs réglementés ou d'incident sont `negociable = non` avec un motif obligatoire : une remise saisie dessus est signalée et non appliquée.

## Limites du POC

- Les délégations et le portefeuille sont inventés.
- La simulation couvre les postes qui pèsent dans une facture Banque Privée (convention, mandats, conseil, conservation, ordres, assurance vie, flux internationaux, crédit) ; les frais ponctuels sont dans la grille mais pas dans le formulaire.
- Les droits de garde ne distinguent pas les valeurs du groupe BNP Paribas (exonérées).
