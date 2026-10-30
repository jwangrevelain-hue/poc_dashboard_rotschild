"""Chargement et validation de la grille tarifaire.

La grille est la source de vérité : trois fichiers texte dans data/,
éditables dans un tableur ou un éditeur, versionnables dans Git.
"""
from __future__ import annotations

import csv
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TYPES_TARIF = {"fixe", "taux", "taux_plus_fixe", "bareme", "sur_devis"}
UNITES = {"EUR", "PCT"}
PERIODICITES = {"an", "mois", "operation", "ordre", "ligne", "dossier"}
CANAUX = {"tous", "agence", "en_ligne"}
STATUTS = {"commercialise", "stock"}
MODES_BAREME = {"tranches", "palier"}


def _num(texte: str) -> float | None:
    texte = (texte or "").strip()
    return float(texte) if texte else None


@dataclass(frozen=True)
class Tarif:
    id: str
    famille: str
    rubrique: str
    libelle: str
    type_tarif: str
    valeur: float | None
    fixe_eur: float | None
    perf_pct: float | None
    unite: str
    assiette: str
    periodicite: str
    minimum: float | None
    maximum: float | None
    bareme_id: str
    canal: str
    statut: str
    page: int
    negociable: bool
    remises_max: dict[str, float]  # code délégation -> remise max en % du prix grille
    motif_verrou: str
    note: str


@dataclass(frozen=True)
class TrancheBareme:
    borne_inf: float
    borne_sup: float | None
    taux_pct: float | None
    fixe_eur: float | None
    minimum_eur: float | None
    libelle: str


@dataclass(frozen=True)
class Bareme:
    id: str
    mode: str  # "tranches" : chaque tranche à son taux ; "palier" : tout le montant au taux du palier atteint
    tranches: tuple[TrancheBareme, ...]
    page: int


@dataclass
class Grille:
    tarifs: dict[str, Tarif]
    baremes: dict[str, Bareme]
    politique: dict
    erreurs: list[str] = field(default_factory=list)

    @property
    def delegations(self) -> list[dict]:
        return self.politique["delegations"]

    def tarif(self, tarif_id: str) -> Tarif:
        return self.tarifs[tarif_id]


def charger_grille(data_dir: Path = DATA_DIR) -> Grille:
    politique = tomllib.loads((data_dir / "politique.toml").read_text(encoding="utf-8"))
    codes = [d["code"] for d in politique["delegations"]]

    baremes: dict[str, list[dict]] = {}
    with open(data_dir / "baremes.csv", encoding="utf-8", newline="") as f:
        for ligne in csv.DictReader(f):
            baremes.setdefault(ligne["bareme_id"], []).append(ligne)

    objets_baremes = {}
    for bid, lignes in baremes.items():
        objets_baremes[bid] = Bareme(
            id=bid,
            mode=lignes[0]["mode"],
            page=int(lignes[0]["page"]),
            tranches=tuple(
                TrancheBareme(
                    borne_inf=float(l["borne_inf"]),
                    borne_sup=_num(l["borne_sup"]),
                    taux_pct=_num(l["taux_pct"]),
                    fixe_eur=_num(l["fixe_eur"]),
                    minimum_eur=_num(l["minimum_eur"]),
                    libelle=l["libelle"],
                )
                for l in sorted(lignes, key=lambda l: float(l["borne_inf"]))
            ),
        )

    tarifs: dict[str, Tarif] = {}
    erreurs: list[str] = []
    with open(data_dir / "grille_tarifaire.csv", encoding="utf-8", newline="") as f:
        for n, l in enumerate(csv.DictReader(f), start=2):
            if l["id"] in tarifs:
                erreurs.append(f"ligne {n} : identifiant {l['id']} en double")
                continue
            tarifs[l["id"]] = Tarif(
                id=l["id"],
                famille=l["famille"],
                rubrique=l["rubrique"],
                libelle=l["libelle"],
                type_tarif=l["type_tarif"],
                valeur=_num(l["valeur"]),
                fixe_eur=_num(l["fixe_eur"]),
                perf_pct=_num(l["perf_pct"]),
                unite=l["unite"],
                assiette=l["assiette"],
                periodicite=l["periodicite"],
                minimum=_num(l["minimum"]),
                maximum=_num(l["maximum"]),
                bareme_id=l["bareme_id"],
                canal=l["canal"],
                statut=l["statut"],
                page=int(l["page"]),
                negociable=l["negociable"].strip().lower() == "oui",
                remises_max={c: (_num(l.get(f"remise_{c}_pct", "")) or 0.0) for c in codes},
                motif_verrou=l["motif_verrou"],
                note=l["note"],
            )

    grille = Grille(tarifs=tarifs, baremes=objets_baremes, politique=politique, erreurs=erreurs)
    grille.erreurs.extend(valider(grille))
    return grille


def valider(grille: Grille) -> list[str]:
    """Contrôles de cohérence : ce qu'un classeur Excel ne vérifie pas tout seul."""
    erreurs = []
    codes = [d["code"] for d in grille.delegations]
    for t in grille.tarifs.values():
        p = f"{t.id} ({t.libelle})"
        if t.type_tarif not in TYPES_TARIF:
            erreurs.append(f"{p} : type de tarif inconnu « {t.type_tarif} »")
        if t.unite not in UNITES:
            erreurs.append(f"{p} : unité inconnue « {t.unite} »")
        if t.periodicite not in PERIODICITES:
            erreurs.append(f"{p} : périodicité inconnue « {t.periodicite} »")
        if t.canal not in CANAUX:
            erreurs.append(f"{p} : canal inconnu « {t.canal} »")
        if t.statut not in STATUTS:
            erreurs.append(f"{p} : statut inconnu « {t.statut} »")
        if t.type_tarif in {"fixe", "taux", "taux_plus_fixe"} and t.valeur is None:
            erreurs.append(f"{p} : valeur manquante")
        if t.type_tarif in {"taux", "taux_plus_fixe", "bareme"} and not t.assiette:
            erreurs.append(f"{p} : un tarif proportionnel doit préciser son assiette")
        if t.type_tarif == "taux_plus_fixe" and t.fixe_eur is None:
            erreurs.append(f"{p} : partie fixe manquante")
        if t.type_tarif == "bareme" and t.bareme_id not in grille.baremes:
            erreurs.append(f"{p} : barème « {t.bareme_id} » introuvable")
        if t.type_tarif == "fixe" and t.unite != "EUR":
            erreurs.append(f"{p} : un tarif fixe s'exprime en EUR")
        if t.type_tarif == "taux" and t.valeur is not None and not (0 < t.valeur <= 100):
            erreurs.append(f"{p} : taux hors de ]0 ; 100] %")
        if t.minimum is not None and t.maximum is not None and t.minimum > t.maximum:
            erreurs.append(f"{p} : minimum supérieur au maximum")
        if t.negociable:
            precedent = 0.0
            for c in codes:
                r = t.remises_max[c]
                if not 0 <= r <= 100:
                    erreurs.append(f"{p} : remise {c} hors de [0 ; 100] %")
                if r < precedent:
                    erreurs.append(f"{p} : la délégation « {c} » ne peut pas être inférieure à la précédente")
                precedent = r
        else:
            if any(t.remises_max.values()):
                erreurs.append(f"{p} : tarif non négociable mais remises renseignées")
            if not t.motif_verrou:
                erreurs.append(f"{p} : tarif non négociable sans motif de verrouillage")
    for b in grille.baremes.values():
        if b.mode not in MODES_BAREME:
            erreurs.append(f"barème {b.id} : mode inconnu « {b.mode} »")
        for avant, apres in zip(b.tranches, b.tranches[1:]):
            if avant.borne_sup != apres.borne_inf:
                erreurs.append(f"barème {b.id} : trou ou chevauchement entre {avant.borne_sup} et {apres.borne_inf}")
        if b.tranches[-1].borne_sup is not None:
            erreurs.append(f"barème {b.id} : la dernière tranche doit être ouverte")
        if b.mode == "tranches" and any(t.fixe_eur for t in b.tranches):
            erreurs.append(f"barème {b.id} : un barème par tranches ne porte que des taux")
    return erreurs
