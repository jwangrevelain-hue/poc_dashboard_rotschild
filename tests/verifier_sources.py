"""Contrôle croisé grille <-> PDF : chaque valeur doit figurer sur la page citée.

    python tests/verifier_sources.py conditions-juillet-2026.pdf
"""
import re
import subprocess
import sys

sys.path.insert(0, ".")
from tarification import charger_grille  # noqa: E402


def texte_page(pdf, page):
    t = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-layout", pdf, "-"],
                       capture_output=True, text=True, check=True).stdout
    return re.sub(r"\s+", "", t).replace(" ", "")


def pour_mille(v):
    x = v * 10
    return {f"{x:.2f}".replace(".", ",") + "‰", f"{x:.2f}".replace(".", ",").rstrip("0").rstrip(",") + "‰"}


def formes(v, unite):
    """Écritures possibles d'une valeur dans le document (« 4,80€ », « 0,50 % », « 1% »…)."""
    s = f"{v:.2f}".replace(".", ",")
    s4 = f"{v:.4f}".replace(".", ",").rstrip("0").rstrip(",")
    variantes = {s, s4, s.rstrip("0").rstrip(","), f"{v:,.0f}".replace(",", "") if v == int(v) else s}
    if v >= 1000 and v == int(v):
        variantes.add(f"{int(v):,}".replace(",", ""))
    suffixe = "€" if unite == "EUR" else "%"
    return {x + suffixe for x in variantes}


def main(pdf):
    grille = charger_grille()
    cache, manquants, verifies = {}, [], 0
    for t in grille.tarifs.values():
        if t.valeur is None:
            continue
        page = cache.setdefault(t.page, texte_page(pdf, t.page))
        candidats = formes(t.valeur, t.unite)
        if t.unite == "PCT" and t.valeur < 1:  # le document écrit parfois les pour-mille
            candidats |= pour_mille(t.valeur)
        verifies += 1
        if not any(c in page for c in candidats):
            manquants.append(f"{t.id} p.{t.page} : {sorted(candidats)} introuvable – {t.libelle}")
    for b in grille.baremes.values():
        page = cache.setdefault(b.page, texte_page(pdf, b.page))
        for tr in b.tranches:
            for v, u in ((tr.taux_pct, "PCT"), (tr.fixe_eur, "EUR"), (tr.minimum_eur, "EUR")):
                if v is None:
                    continue
                c = formes(v, u) | pour_mille(v)
                verifies += 1
                if not any(x in page for x in c):
                    manquants.append(f"barème {b.id} p.{b.page} : {v} {u} introuvable")
    print(f"{verifies} valeurs contrôlées, {len(manquants)} introuvable(s) à vérifier à l'œil :")
    for m in manquants:
        print("  -", m)


if __name__ == "__main__":
    main(sys.argv[1])
