// Vérifie que le moteur du navigateur (dashboard/moteur.js) calcule exactement
// comme le moteur Python, sur les profils d'exemple et tout le portefeuille fictif.
//   python construire.py && node tests/parite.cjs
const fs = require("fs");
const path = require("path");
const { creerMoteur } = require("../dashboard/moteur.js");

const donnees = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "sortie", "donnees.json"), "utf8"));
const moteur = creerMoteur(donnees);
let ecarts = 0;
let comparaisons = 0;

function comparer(nom, attendu, obtenu) {
  const champs = ["total_brut", "total_net", "encours", "niveau_requis", "alertes"];
  for (const c of champs) {
    comparaisons++;
    const a = attendu[c], o = obtenu[c];
    const ok = typeof a === "number" ? Math.abs(a - o) < 0.005 : a === o;
    if (!ok) { ecarts++; console.log(`✗ ${nom} – ${c} : Python ${a} / JS ${o}`); }
  }
  attendu.lignes.forEach((la, i) => {
    const lo = obtenu.lignes[i] || {};
    comparaisons++;
    if (la.tarif_id !== lo.tarif_id || Math.abs(la.net - lo.net) > 0.005 || la.detail !== lo.detail || la.controle.statut !== lo.controle.statut || la.poste !== lo.poste) {
      ecarts++;
      console.log(`✗ ${nom} – ligne ${i} : Python ${la.tarif_id} ${la.net} « ${la.detail} » [${la.poste}] / JS ${lo.tarif_id} ${lo.net} « ${lo.detail} » [${lo.poste}]`);
    }
  });
}

for (const [cle, ex] of Object.entries({ ...donnees.exemples, ...donnees.cas_limites })) comparer(cle, ex.resultat, moteur.simuler(ex.profil));
const parClient = Object.fromEntries(donnees.portefeuille.clients.map((c) => [c.id, c]));
for (const p of donnees.profils_portefeuille) {
  const s = moteur.simuler(p);
  const ref = parClient[p.id];
  for (const [cp, cj] of [["brut", "total_brut"], ["net", "total_net"], ["encours", "encours"], ["alertes", "alertes"], ["niveau_requis", "niveau_requis"]]) {
    comparaisons++;
    const ok = typeof ref[cp] === "number" ? Math.abs(ref[cp] - s[cj]) < 0.005 : ref[cp] === s[cj];
    if (!ok) { ecarts++; console.log(`✗ ${p.id} – ${cp} : Python ${ref[cp]} / JS ${s[cj]}`); }
  }
}
console.log(ecarts ? `✗ ${ecarts} écart(s) sur ${comparaisons} comparaisons` : `✓ Parité Python/JS : ${comparaisons} comparaisons, 0 écart`);
process.exit(ecarts ? 1 : 0);
