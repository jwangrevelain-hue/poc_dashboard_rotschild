# Pilote de tarification Banque Privée : présentation du projet

Ce POC montre qu'une banque privée peut remplacer son classeur Excel de tarification par une **grille de données unique**, un **moteur de calcul** et un **tableau de bord**, sans perdre la souplesse des remises négociées.

## Le problème

Dans beaucoup d'établissements, la tarification vit dans un classeur Excel :

- **Plusieurs copies circulent par mail**, et personne ne sait laquelle fait foi.
- **Aucune saisie n'est vérifiée.** Une virgule mal placée ou une cellule écrasée passe inaperçue.
- **Les marges de manœuvre sont rarement écrites.** Combien un banquier peut-il accorder de remise, et à partir de quand faut-il le directeur ou le comité ? Ce sont surtout les seniors qui le savent.
- **La facture d'un client est recalculée à la main**, barèmes et plafonds réglementaires compris.
- **Les dérogations sont consolidées en fin de trimestre**, quand il est trop tard pour réagir.

## La réponse du POC

```
   data/                          tarification/                     sortie/
┌──────────────────────┐   ┌──────────────────────────┐   ┌──────────────────────────┐
│ grille_tarifaire.csv │   │ 1. contrôle la grille    │   │ dashboard.html           │
│ baremes.csv          │──▶│ 2. calcule les factures  │──▶│ grille_tarifaire.xlsx    │
│ politique.toml       │   │ 3. agrège le portefeuille│   │ donnees.json             │
└──────────────────────┘   └──────────────────────────┘   └──────────────────────────┘
     source unique              python construire.py            livrables régénérés
```

1. **Une seule source** : trois fichiers texte dans `data/`, versionnés avec Git. Chaque changement de prix est daté, attribué et réversible.
2. **Des contrôles avant toute publication.** Si la grille est incohérente, la liste des erreurs s'affiche et rien n'est régénéré.
3. **Des remises encadrées** : pour chaque tarif, la remise maximale de chaque niveau de délégation est écrite dans la grille et appliquée au calcul.
4. **Trois livrables issus des mêmes données** :
   - un tableau de bord HTML autonome, qui s'ouvre sans serveur ;
   - un export Excel pour ceux qui restent sur le tableur ;
   - un fichier JSON pour d'autres outils.

## Ce qui est réel, ce qui est inventé

| Origine | Contenu |
|---|---|
| **Document public** | Prix, taux, minimums, maximums et barèmes, repris de *BNP Paribas Banque Privée – Conditions et tarifs au 1er juillet 2026* (`conditions-juillet-2026.pdf`). Chaque tarif renvoie à sa page. |
| **Réglementé** | Plafonds légaux : frais d'incident, compte inactif, transfert de PEA, successions… Ces 24 tarifs sont marqués non négociables, avec leur motif. |
| **Hypothèse de démonstration** | Les remises maximales par niveau de délégation, et le portefeuille de 240 clients, généré aléatoirement. Aucun client réel. |

## Les données

### La grille : `data/grille_tarifaire.csv`

Elle compte 179 tarifs, répartis en 17 familles. Les plus fournies sont la gestion sous mandat (30), la Bourse et la conservation (27) et les cartes (18). Viennent ensuite quatre familles de 14 tarifs : compte et services, virements, incidents, découverts et crédits.

Chaque ligne décrit un tarif :

| Colonnes | Rôle |
|---|---|
| `id`, `famille`, `rubrique`, `libelle` | identification (`BRS-011`, « Droit fixe par ligne au porteur ») |
| `type_tarif` | comment se calcule le prix (voir ci-dessous) |
| `valeur`, `fixe_eur`, `perf_pct`, `unite` | le prix : montant en euros ou taux en %, part fixe, commission de performance |
| `assiette`, `periodicite` | sur quoi porte le taux (encours, montant d'ordre…) et à quelle fréquence |
| `minimum`, `maximum`, `bareme_id` | bornes du prix, ou renvoi à un barème |
| `canal`, `statut`, `page` | canal (en ligne, agence…), offre commercialisée ou en stock, page du PDF |
| `negociable`, `motif_verrou` | si le tarif est verrouillé, le motif est obligatoire |
| `remise_banquier_pct`, `remise_directeur_pct`, `remise_comite_pct` | remise maximale accordable à chaque niveau |
| `note` | précision libre |

Il existe cinq types de tarif :

| Type | Calcul | Nombre |
|---|---|---|
| `fixe` | un montant en euros | 103 |
| `taux` | assiette × taux | 58 |
| `taux_plus_fixe` | assiette × taux + partie fixe | 10 |
| `bareme` | renvoi à un barème de `baremes.csv` | 7 |
| `sur_devis` | pas de prix calculable : le minimum sert de référence | 1 |

Les minimums et maximums s'appliquent ensuite. Les mandats « à la performance » ajoutent une commission sur la performance annuelle.

### Les barèmes : `data/baremes.csv`

Les 7 barèmes couvrent les droits de garde, les ordres de Bourse (offres Start et Active), le change, les chèques étrangers et l'usufruit temporaire. Ils fonctionnent selon deux modes :

- **Par tranches**, comme un impôt progressif : chaque tranche est facturée à son taux. Par exemple, les droits de garde sur 150 000 € valent 0,40 % × 50 000 € + 0,20 % × 100 000 €, soit 400 €.
- **Par palier** : tout le montant est facturé au taux du palier atteint. Par exemple, un ordre en ligne de 2 000 € coûte 10 € en offre Start, et un ordre de 10 000 € coûte 0,50 %, soit 50 €.

### La politique : `data/politique.toml`

- **Les niveaux de délégation**, par ordre croissant de pouvoir : banquier privé, directeur de centre, comité tarifaire.
- **Les règles transverses** :
  - 50 % de réduction sur la deuxième carte ;
  - plafonds légaux du PEA : 0,50 % par transaction en ligne et 1,20 % par les autres canaux, et 0,40 % de la valorisation + 5 € par ligne pour la garde et les frais de gestion ;
  - offre Active : abonnement et droits de garde offerts dès 50 ordres par an.

## Le moteur de calcul : `tarification/`

| Module | Rôle |
|---|---|
| `grille.py` | charge les trois fichiers et contrôle leur cohérence |
| `calcul.py` | prix d'un tarif, application d'un barème, contrôle d'une remise |
| `simulation.py` | facture annuelle d'un client |
| `portefeuille.py` | génération du portefeuille fictif et agrégats de pilotage |
| `export.py` | JSON du dashboard et classeur Excel |

### Contrôles de la grille

Une grille est refusée dans les cas suivants :

- un type, une unité, une périodicité, un canal ou un statut inconnu ;
- une valeur manquante, ou un tarif proportionnel sans assiette ;
- un tarif fixe qui n'est pas en euros, ou un taux hors de ]0 ; 100] % ;
- un minimum supérieur au maximum ;
- une remise hors de [0 ; 100] %, ou un niveau supérieur qui accorde moins que le précédent ;
- un tarif verrouillé sans motif, ou qui porte quand même des remises ;
- un barème troué, qui se chevauche ou dont la dernière tranche n'est pas ouverte ;
- un identifiant en double.

### Contrôle d'une remise

Une remise est rattachée au **premier niveau de délégation suffisant**. Chaque ligne de facture reçoit l'un de ces statuts :

| Statut | Signification | Remise appliquée ? |
|---|---|---|
| `grille` | aucune remise | – |
| `dans_delegation` | dans le pouvoir du banquier, du directeur ou du comité | oui |
| `hors_delegation` | au-delà de ce que le comité peut accorder | oui, mais signalée |
| `verrouille` | tarif non négociable | non, et signalée |
| `invalide` | remise négative | non, et signalée |

### Facture annuelle d'un client

`simuler(grille, profil)` produit la facture d'une année. Elle couvre les postes qui pèsent dans une facture Banque Privée :

- la convention Banque Privée et les cartes, avec la réduction sur la deuxième carte ;
- les mandats de gestion, titres et assurance vie (encours × taux, plus la performance éventuelle) ;
- la convention de conseil ;
- le compte-titres ou le PEA : droits de garde, frais par ligne, abonnement de l'offre Active, ordres en ligne et en agence, plafonds PEA ;
- les versements en assurance vie et en PER ;
- les virements et paiements hors zone euro ;
- le coffre-fort, les attestations, le crédit immobilier et les incidents.

Pour chaque ligne, la facture donne le prix grille, la remise, le net, le contrôle de délégation et le poste, c'est-à-dire le contrat auquel la ligne appartient (`POSTES` dans `simulation.py`). Elle donne aussi les totaux, le coût rapporté à l'encours, le niveau de validation requis et le nombre d'alertes.

### Portefeuille fictif

`portefeuille.py` génère 240 clients, toujours les mêmes grâce à une graine fixe :

- répartis dans 6 centres ;
- avec un patrimoine médian d'environ 1,8 M€ ;
- avec des mandats, un compte-titres et des flux tirés au hasard.

Les remises sont tirées ligne par ligne :

| Part des lignes négociables | Remise tirée |
|---|---|
| 50 % | aucune, prix grille |
| 28 % | dans le pouvoir du banquier |
| 14 % | du ressort du directeur |
| 5 % | du ressort du comité |
| 3 % | au-delà, hors délégation |

Le portefeuille est ensuite agrégé par famille de tarifs, par niveau de délégation et par centre, avec la liste des dérogations.

## Le tableau de bord

`sortie/dashboard.html` est un fichier unique, qui embarque les données et le moteur. Il s'ouvre par double-clic, sans serveur ni connexion. Le moteur JavaScript (`dashboard/moteur.js`) reproduit le moteur Python, ce qui permet de recalculer en direct dans le navigateur.

### Pilotage

C'est la vue d'ensemble du portefeuille :

| Indicateur | Valeur |
|---|---|
| Revenu au prix grille | 4,70 M€ |
| Revenu net facturé | 4,20 M€, soit 0,90 % des 468 M€ d'encours tarifé |
| Remises accordées | 500 k€, soit 10,7 % du prix grille |
| Dérogations hors délégation | 17, soit 5 684 € au-delà des plafonds |

On y trouve aussi :

- les revenus par famille de tarifs ;
- les remises par niveau de délégation ;
- le tableau des dérogations à régulariser ;
- le détail par centre : un clic sur une ligne filtre tout le tableau de bord.

Un scénario, « Ramener les dérogations au plafond autorisé », chiffre ce que rapporterait une remise en conformité.

### Simulateur client

Il calcule la facture annuelle d'un client à partir de trois profils d'exemple :

| Profil | Prix grille | Négocié | Validation requise |
|---|---|---|---|
| Dirigeant cédant, 4,2 M€ | 63 084 € | 49 084 € | directeur |
| Investisseur actif, PEA + compte-titres, 900 k€ | 6 150 € | 5 190 € | comité |
| Jeune actif, mandat 350 k€, crédit immobilier | 9 505 € | 6 832 € | comité |

La facture est présentée **contrat par contrat** : relation bancaire, mandat de gestion titres, mandat d'arbitrage assurance vie, gestion conseillée, compte-titres, versements, flux internationaux, puis services. Chaque bloc s'ouvre sur son sous-total (prix grille, remise, net) et sur le niveau de validation qu'il requiert. Pour un mandat, un conseil ou un compte-titres, il affiche aussi le taux net rapporté à l'encours, par exemple « 1,19 % net sur 2,50 M€ · grille 1,40 % ». La demande de validation reprend le même découpage.

Chaque encours et chaque option se modifie. Sur chaque ligne négociable, la remise se saisit au clavier ou avec un curseur. La piste du curseur est colorée par zone, chacune allant jusqu'au plafond d'un niveau : banquier, directeur, comité, puis hors délégation. Pendant le glissement, le net, le niveau de validation requis, la synthèse et la demande se recalculent en direct. Les dépassements et les tarifs verrouillés sont signalés.

Un texte de **demande de validation** est généré, prêt à coller dans un mail au directeur ou au comité.

### Grille tarifaire

C'est la grille telle que chargée, avec sa page source pour chaque tarif. On peut la filtrer par recherche, par famille, sur les seuls tarifs négociables, ou inclure les 7 offres qui ne sont plus commercialisées. Les barèmes sont détaillés tranche par tranche.

### Comment ça marche

Cet onglet explique la méthode, distingue ce qui vient du document de ce qui est supposé, et compare Excel et la grille de données.

## Utiliser le projet

Prérequis : Python ≥ 3.11. Pour les contrôles complets, il faut aussi Node.js ≥ 18 et `pdftotext` (poppler).

```bash
pip install -r requirements.txt
python construire.py          # valide la grille puis régénère sortie/
open sortie/dashboard.html
```

Pour **modifier un tarif** :

1. Changer la valeur dans `data/grille_tarifaire.csv`, avec un tableur ou un éditeur de texte.
2. Lancer `python construire.py`.
   - Si la grille est valide, le dashboard, l'Excel et le JSON sont régénérés.
   - Sinon, chaque erreur indique le tarif et la règle enfreinte, et rien n'est publié.
3. Commiter : la modification est tracée dans Git.

Pour **changer la politique de délégation**, modifier les colonnes `remise_*_pct` de la grille ou les niveaux de `politique.toml`. Les contrôles vérifient qu'un niveau supérieur accorde toujours au moins autant que le précédent.

`python construire.py --valider` contrôle la grille sans rien régénérer.

## Garanties de qualité

| Contrôle | Commande | Ce qu'il garantit |
|---|---|---|
| Cohérence de la grille | `python construire.py --valider` | aucune grille incohérente n'est publiée |
| Cas de référence | `python -m pytest tests` | 23 tests, dont les exemples du document (p. 38), les barèmes, les minimums, les plafonds PEA, les remises et les libellés |
| Parité Python / navigateur | `node tests/parite.cjs` | le dashboard calcule exactement comme Python : 1 280 comparaisons sur les exemples, les cas limites et les 240 clients |
| Conformité au PDF | `python tests/verifier_sources.py conditions-juillet-2026.pdf` | les 192 valeurs de la grille figurent sur la page citée |
| Sorties à jour | intégration continue | `sortie/` correspond aux données commitées |

Un build sans modification laisse `sortie/` intact : l'horodatage n'est renouvelé que si les données changent. L'intégration continue (`.github/workflows/ci.yml`) lance tous ces contrôles à chaque push.

## Organisation du dépôt

```
data/                        la grille en données (source de vérité)
  grille_tarifaire.csv       179 tarifs
  baremes.csv                7 barèmes
  politique.toml             délégations et règles transverses
tarification/                moteur Python
dashboard/
  gabarit.html               la page : styles, vues, interactions
  moteur.js                  le même moteur, côté navigateur
tests/                       cas de référence, parité, conformité au PDF
construire.py                point d'entrée unique
sortie/                      fichiers générés : ne pas modifier à la main
conditions-juillet-2026.pdf  document source
.github/workflows/ci.yml     intégration continue
```

## Limites

- Les délégations et le portefeuille sont inventés. Il faudra les remplacer par la politique de dérogation réelle et par des données clients.
- La simulation couvre les postes récurrents. Les frais ponctuels sont dans la grille, mais pas dans le formulaire.
- Les droits de garde ne distinguent pas les valeurs du groupe BNP Paribas, qui en sont exonérées.
- Le plafond PEA de 25 € par ligne non cotée n'est pas appliqué : la simulation ne distingue pas ces lignes.

## Prochaines étapes

- Comparer le portefeuille ligne par ligne dans le test de parité, et pas seulement les totaux par client.
- Tester qu'une grille volontairement cassée produit les bonnes erreurs.
- Distinguer les lignes non cotées pour appliquer le plafond PEA correspondant.
- Remplacer les hypothèses (délégations, portefeuille) par les données de l'établissement.
