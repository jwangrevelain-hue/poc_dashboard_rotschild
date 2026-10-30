/* Moteur de calcul côté navigateur : miroir de tarification/calcul.py et simulation.py.
   La parité avec Python est vérifiée par tests/parite.mjs sur tout le portefeuille fictif. */
(function (racine) {
  "use strict";

  const arrondi = (x) => Math.round((x + 1e-9) * 100) / 100;
  const eur = (x) => Math.round(x).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " €";
  const pct = (x) => x.toFixed(2).replace(".", ",") + " %";
  const deux = (x) => x.toFixed(2).replace(".", ",");
  const g = (x) => String(+x.toPrecision(12)).replace(".", ",");
  const CARTES_INCLUSES = ["CAR-001", "CAR-002"];

  function creerMoteur(donnees) {
    const tarifs = Object.fromEntries(donnees.tarifs.map((t) => [t.id, t]));
    const baremes = donnees.baremes;
    const delegations = donnees.delegations;
    const regles = donnees.regles;
    const tarif = (id) => {
      if (!tarifs[id]) throw new Error("Tarif inconnu : " + id);
      return tarifs[id];
    };

    function appliquerBareme(b, montant) {
      if (montant <= 0) return 0;
      if (b.mode === "tranches") {
        let total = 0;
        for (const t of b.tranches) {
          const haut = t.borne_sup == null ? montant : Math.min(montant, t.borne_sup);
          if (haut > t.borne_inf) total += ((haut - t.borne_inf) * (t.taux_pct || 0)) / 100;
        }
        return total;
      }
      for (const t of b.tranches) {
        if (t.borne_sup == null || montant <= t.borne_sup) {
          const prix = (t.fixe_eur || 0) + (montant * (t.taux_pct || 0)) / 100;
          return Math.max(prix, t.minimum_eur || 0);
        }
      }
      throw new Error("barème sans tranche ouverte");
    }

    function prixBrut(t, assiette = 0, perf = 0) {
      let prix;
      if (t.type_tarif === "fixe") prix = t.valeur;
      else if (t.type_tarif === "taux") prix = (assiette * t.valeur) / 100;
      else if (t.type_tarif === "taux_plus_fixe") prix = (assiette * t.valeur) / 100 + t.fixe_eur;
      else if (t.type_tarif === "bareme") prix = appliquerBareme(baremes[t.bareme_id], assiette);
      else prix = t.minimum || 0;
      if (t.perf_pct && perf > 0) prix += (((assiette * perf) / 100) * t.perf_pct) / 100;
      if (t.minimum != null && t.type_tarif !== "sur_devis") prix = Math.max(prix, t.minimum);
      if (t.maximum != null) prix = Math.min(prix, t.maximum);
      return prix;
    }

    function controlerRemise(t, r) {
      if (r <= 0) return { statut: "grille", niveau: null, message: "Prix grille" };
      if (!t.negociable) return { statut: "verrouille", niveau: null, message: "Non négociable : " + t.motif_verrou };
      for (const d of delegations) {
        if (r <= t.remises_max[d.code] + 1e-9)
          return { statut: "dans_delegation", niveau: d.code, message: "Accordable par : " + d.libelle };
      }
      const plafond = Math.max(...Object.values(t.remises_max));
      return { statut: "hors_delegation", niveau: null, message: `Au-delà de la remise maximale autorisée (${g(plafond)} %)` };
    }

    function simuler(profil) {
      const remises = profil.remises || {};
      const lignes = [];
      const ajouter = (id, detail, brutTotal, quantite = 1) => {
        const t = tarif(id);
        const r = remises[id] || 0;
        const rApp = t.negociable ? Math.min(r, 100) : 0;
        lignes.push({
          tarif_id: t.id, famille: t.famille, libelle: t.libelle, detail, quantite,
          brut: arrondi(brutTotal), remise_pct: r, net: arrondi(brutTotal * (1 - rApp / 100)),
          controle: controlerRemise(t, r), page: t.page,
        });
      };
      const convention = !!profil.convention_bp;
      if (convention) ajouter("CBP-001", "Forfait annuel", prixBrut(tarif("CBP-001")));

      let cartes = [...(profil.cartes || [])];
      if (convention) for (const c of CARTES_INCLUSES) { const i = cartes.indexOf(c); if (i >= 0) cartes.splice(i, 1); }
      cartes.sort((a, b) => tarif(b).valeur - tarif(a).valeur);
      cartes.forEach((c, i) => {
        const prix = tarif(c).valeur;
        if (!convention && i === 1) {
          const red = regles.reduction_deuxieme_carte_pct;
          ajouter(c, `Cotisation annuelle – 2e carte −${g(red)} %`, prix * (1 - red / 100));
        } else ajouter(c, "Cotisation annuelle", prix);
      });

      const m1 = profil.mandat_titres;
      if (m1 && m1.encours) {
        const t = tarif(m1.offre);
        const perf = m1.premiere_annee ? 0 : m1.performance_pct || 0;
        let detail = `${eur(m1.encours)} × ${pct(t.valeur)}`;
        if (t.perf_pct) detail += perf > 0 ? ` + ${g(t.perf_pct)} % de la performance (${pct(perf)})` : " (pas de commission de performance)";
        ajouter(t.id, detail, prixBrut(t, m1.encours, perf));
      }
      const m2 = profil.mandat_assurance;
      if (m2 && m2.encours) {
        const t = tarif(m2.offre);
        const perf = m2.premiere_annee ? 0 : m2.performance_pct || 0;
        let detail = `${eur(m2.encours)} × ${pct(t.valeur)}`;
        if (t.perf_pct && perf > 0) detail += ` + ${g(t.perf_pct)} % de la performance (${pct(perf)})`;
        ajouter(t.id, detail, prixBrut(t, m2.encours, perf));
      }
      const m3 = profil.conseil;
      if (m3 && m3.encours) {
        const t = tarif(m3.offre);
        ajouter(t.id, `${eur(m3.encours)} × ${pct(t.valeur)}`, prixBrut(t, m3.encours));
      }

      const ct = profil.compte_titres;
      if (ct && ct.valorisation) {
        const pea = ct.enveloppe === "PEA";
        const active = ct.offre === "Active";
        const nbOrdres = (ct.ordres_en_ligne || 0) + (ct.ordres_agence || 0);
        const seuil = regles.offre_active_seuil_ordres_gratuite;
        const gratuite = active && nbOrdres >= seuil;
        if (gratuite) ajouter("BRS-010", `Offerts : ${nbOrdres} ordres ≥ ${seuil}`, 0);
        else {
          ajouter("BRS-010", `Barème par tranches sur ${eur(ct.valorisation)}`, prixBrut(tarif("BRS-010"), ct.valorisation));
          let n = ct.lignes_porteur || 0;
          if (n) ajouter("BRS-011", `${n} lignes × 5 €`, n * tarif("BRS-011").valeur, n);
          n = ct.lignes_nominatif || 0;
          if (n) {
            let u = tarif("BRS-012").valeur;
            const plaf = pea && u > regles.pea_plafond_garde_par_ligne_eur;
            if (plaf) u = regles.pea_plafond_garde_par_ligne_eur;
            ajouter("BRS-012", `${n} lignes × ${g(u)} €` + (plaf ? " (plafond PEA)" : ""), n * u, n);
          }
        }
        if (active) ajouter("BRS-013", gratuite ? "Offert (≥ 50 ordres)" : "Abonnement annuel", gratuite ? 0 : tarif("BRS-013").valeur);
        let n = ct.ordres_en_ligne || 0;
        if (n) {
          const id = active ? "BRS-002" : "BRS-001";
          const montant = ct.montant_moyen_ordre || 0;
          let u = prixBrut(tarif(id), montant);
          const plafond = (montant * regles.pea_plafond_transaction_en_ligne_pct) / 100;
          const plaf = pea && u > plafond;
          if (plaf) u = plafond;
          ajouter(id, `${n} ordres de ${eur(montant)} × ${deux(u)} €` + (plaf ? " (plafond PEA)" : ""), n * u, n);
        }
        n = ct.ordres_agence || 0;
        if (n) {
          const montant = ct.montant_moyen_ordre_agence != null ? ct.montant_moyen_ordre_agence : ct.montant_moyen_ordre || 0;
          let u = prixBrut(tarif("BRS-007"), montant);
          const plafond = (montant * regles.pea_plafond_transaction_autre_pct) / 100;
          const plaf = pea && u > plafond;
          if (plaf) u = plafond;
          ajouter("BRS-007", `${n} ordres de ${eur(montant)} × ${deux(u)} €` + (plaf ? " (plafond PEA)" : ""), n * u, n);
        }
      }

      for (const [cle, id] of [["versements_av", "AVI-001"], ["versements_per", "AVI-002"]]) {
        const montant = profil[cle] || 0;
        if (montant) { const t = tarif(id); ajouter(id, `${eur(montant)} versés × ${pct(t.valeur)}`, prixBrut(t, montant)); }
      }
      for (const [cle, id] of [["virements_non_sepa_en_ligne", "VIR-007"], ["virements_non_sepa_agence", "VIR-009"]]) {
        const n = profil[cle] || 0;
        if (n) { const t = tarif(id); ajouter(id, `${n} virements × ${g(t.valeur)} €`, n * t.valeur, n); }
      }
      const dep = profil.depenses_hors_zone_euro || 0;
      if (dep) {
        const nb = Math.max(profil.nb_paiements_hors_zone_euro || 1, 1);
        const id = (profil.cartes || []).includes("CAR-001") ? "CAR-014" : "CAR-015";
        const t = tarif(id);
        ajouter(id, `${eur(dep)} en ${nb} paiements : ${pct(t.valeur)} + ${deux(t.fixe_eur)} €/paiement`, (dep * t.valeur) / 100 + nb * t.fixe_eur, nb);
      }
      if (profil.coffre) ajouter("CPT-012", "Cotisation annuelle", tarif("CPT-012").valeur);
      const nAtt = profil.attestations || 0;
      if (nAtt) ajouter("CPT-010", `${nAtt} attestations`, nAtt * tarif("CPT-010").valeur, nAtt);
      const immo = profil.credit_immo || 0;
      if (immo) { const t = tarif("CRE-007"); ajouter("CRE-007", `${eur(immo)} × ${pct(t.valeur)} (min. 650 €)`, prixBrut(t, immo)); }
      for (const [id, n] of Object.entries(profil.incidents || {})) {
        if (n) { const t = tarif(id); ajouter(id, `${n} × ${g(t.valeur)} €`, n * t.valeur, n); }
      }

      const encours = ["mandat_titres", "mandat_assurance", "conseil"].reduce((s, k) => s + ((profil[k] || {}).encours || 0), 0)
        + ((profil.compte_titres || {}).valorisation || 0);
      const totalBrut = arrondi(lignes.reduce((s, l) => s + l.brut, 0));
      const totalNet = arrondi(lignes.reduce((s, l) => s + l.net, 0));
      const ordre = delegations.map((d) => d.code);
      const niveaux = lignes.map((l) => l.controle.niveau).filter(Boolean);
      const niveauRequis = niveaux.length ? niveaux.reduce((a, b) => (ordre.indexOf(b) > ordre.indexOf(a) ? b : a)) : null;
      return {
        lignes, total_brut: totalBrut, total_net: totalNet, remise_totale: arrondi(totalBrut - totalNet), encours,
        taux_global_pct: encours ? Math.round((totalNet / encours) * 100 * 1e4) / 1e4 : null,
        niveau_requis: niveauRequis,
        alertes: lignes.filter((l) => l.controle.statut === "hors_delegation" || l.controle.statut === "verrouille").length,
      };
    }

    return { tarif, tarifs, appliquerBareme, prixBrut, controlerRemise, simuler };
  }

  const api = { creerMoteur, arrondi };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else racine.Moteur = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
