<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <img src="assets/logo.svg" alt="Ancora — suivi patrimonial et financier" height="72">
  </picture>
</h1>

<p align="center"><em>Un point d'ancrage pour tout son patrimoine, sans jamais inventer une donnée.</em></p>

**Ancora** est une application **personnelle** pour suivre, regrouper, analyser et valoriser
un patrimoine financier réparti entre plusieurs enveloppes
(PEA, assurance-vie, PER, CTO…) et plusieurs types d'actifs
(actions, ETF, OPCVM / SICAV / FCP, unités de compte, indices).

> ⚠️ **Usage strictement personnel.** Cette application n'est pas un outil
> de conseil en investissement et ne formule aucune recommandation d'achat
> ou de vente.

<!-- AUTO:META:START -->
> 🔄 **Dernière mise à jour :** 26/10/2026 00:11 (heure de Paris) · commit `3ec2ab1` · 6 commits au total
<!-- AUTO:META:END -->

---

## Sommaire

1. [Avancement](#-avancement)
2. [Fonctionnalités](#-fonctionnalités)
3. [Règles de calcul](#-règles-de-calcul)
4. [Qualité des données](#-qualité-des-données)
5. [Stack technique et architecture](#-stack-technique-et-architecture)
6. [Installation](#-installation)
7. [Structure du dépôt](#-structure-du-dépôt)
8. [Statistiques du code](#-statistiques-du-code)
9. [Derniers changements](#-derniers-changements)
10. [Sources de données et limitations](#-sources-de-données-et-limitations)
11. [Sécurité et confidentialité](#-sécurité-et-confidentialité)
12. [Mise à jour automatique de ce README](#-mise-à-jour-automatique-de-ce-readme)
13. [Identité visuelle](#-identité-visuelle)
14. [Documentation](#-documentation)

---

## 📈 Avancement

Calculé à partir des cases cochées dans [`docs/ROADMAP.md`](docs/ROADMAP.md).

<!-- AUTO:PROGRESS:START -->
| Étape | Avancement | Fait |
|---|---|---|
| Version 1 — MVP | `░░░░░░░░░░` 0 % | 0/17 |
| Critères de recette | `░░░░░░░░░░` 0 % | 0/13 |
| Version 2 — Nouveaux actifs | `░░░░░░░░░░` 0 % | 0/3 |
| Version 3 — Imports | `░░░░░░░░░░` 0 % | 0/2 |
| Version 4 — Mobilité | `░░░░░░░░░░` 0 % | 0/3 |
| Version 5 — Assistant | `░░░░░░░░░░` 0 % | 0/2 |
| **Total** | `░░░░░░░░░░` 0 % | **0/40** |
<!-- AUTO:PROGRESS:END -->

---

## ✨ Fonctionnalités

### Actifs couverts (MVP)

| Catégorie | Détail |
|---|---|
| Actions | États-Unis, Europe |
| ETF | Capitalisants, distribuants |
| Fonds | OPCVM, SICAV, FCP |
| Unités de compte | Assurance-vie, PER |
| Indices | CAC 40, Euro Stoxx 50, S&P 500, Nasdaq, MSCI World, MSCI EM, autres indices paramétrables |

**Prévus après le MVP :** obligations, fonds euros, produits structurés,
private equity, immobilier non coté (SCPI…), cryptomonnaies.

### Enveloppes

PEA · PEA-PME · Assurance-vie · PER · CTO · Autres enveloppes.
Pour chacune : nom, établissement, contrat, devise de référence, commentaire.

### Positions et opérations

- **Positions initiales** créées sans historique de transactions :
  instrument, quantité, PRU, devise, date de reprise, enveloppe,
  établissement, contrat.
- **Opérations** : achat, vente, dividende, distribution, coupon, apport,
  retrait, frais, correction (date, instrument, montant, quantité,
  prix unitaire, devise, frais, commentaire).

### Tableaux de bord

| Vue | Contenu |
|---|---|
| Global | Valorisation totale, plus-value totale, répartition par enveloppe et par type d'actif |
| Marchés | Instruments suivis, cours, performances, fondamentaux |
| Portefeuille | Positions, valorisation, gains / pertes |
| Enveloppes | Vue par contrat et par enveloppe |
| Revenus | Dividendes, distributions, coupons |
| Qualité des données | Origine, fraîcheur, erreurs, historique |
| Administration | Ajout, archivage, actualisation, sauvegarde, paramètres |

### Autres fonctions

- Données fondamentales : dividendes N / N+1, BNA de Y-3 à Y+1 (avec
  l'exercice fiscal réel), consensus des analystes, potentiel.
- Performances sur 1 semaine, 1 mois, 6 mois, 1 an, 5 ans, 10 ans.
- Actualisation manuelle (tous les instruments ou un seul), sans jamais
  bloquer l'interface si un fournisseur est indisponible.
- Archivage plutôt que suppression : un instrument qui a une position,
  une opération ou un historique reste consultable.
- Sauvegarde complète, restauration, vérification d'intégrité, historique
  des sauvegardes.

---

## 🧮 Règles de calcul

| Indicateur | Formule |
|---|---|
| Valorisation | `Quantité × cours actuel` |
| Plus-value latente | `Valeur actuelle − coût d'acquisition` |
| Plus-value latente % | `(Valeur actuelle / coût d'acquisition − 1) × 100` |
| Potentiel | `(Objectif moyen / cours actuel − 1) × 100` |
| PRU | Prix de revient moyen pondéré |

- **Vente** : diminue la quantité détenue, **ne modifie pas** le PRU de la
  quantité restante et génère une plus-value ou moins-value réalisée.
- **Devises** : consolidation en **EUR**. On conserve la devise de l'actif,
  celle de la transaction, le taux de change, sa date et sa source.
  L'application distingue la performance de marché de l'effet de change.
- **Performances** : aucune extrapolation ni estimation. Si l'historique ne
  suffit pas, la valeur affichée est `N/A`.

---

## 🔎 Qualité des données

Chaque donnée conserve sa **valeur**, sa **source**, sa **date de référence**,
sa **date de collecte** et son **statut**.

| Code | Statut |
|---|---|
| 🟢 | Valide (réelle) |
| 🔵 | Estimation |
| 🟠 | Obsolète |
| ⚪ | Non disponible |
| ⚫ | Non applicable |
| 🔴 | Erreur |

Les données calculées et manuelles portent aussi leur propre statut.
La couleur n'est jamais le seul moyen de transmettre l'information : le
libellé du statut est toujours affiché.

> 🚫 Une donnée absente n'est **jamais** remplacée par `0`, par une estimation
> automatique ou par une valeur calculée arbitrairement.
> Le ticker seul n'est **jamais** utilisé comme identifiant unique
> (on utilise un identifiant interne, avec l'ISIN et la place de cotation).

---

## 🏗️ Stack technique et architecture

**Technologies :** Python · Streamlit · SQLite · SQLAlchemy · Alembic ·
Pandas · Pydantic · Plotly.

État de l'architecture cible (§19 du cahier des charges), recalculé à chaque push :

<!-- AUTO:ARCHITECTURE:START -->
| Dossier | Rôle | État | Fichiers Python |
|---|---|---|---|
| `app/` | Point d'entrée de l'application Streamlit | ⬜ À créer | — |
| `pages/` | Pages et tableaux de bord Streamlit | ⬜ À créer | — |
| `domain/` | Règles métier : PRU, valorisation, plus-values, devises | ⬜ À créer | — |
| `services/` | Orchestration : actualisation, sauvegarde, archivage | ⬜ À créer | — |
| `connectors/` | Fournisseurs de données : yfinance, Finnhub, SEC EDGAR, saisie manuelle | ⬜ À créer | — |
| `models/` | Modèles SQLAlchemy et schémas Pydantic | ⬜ À créer | — |
| `database/` | Accès SQLite et gestion des sessions | ⬜ À créer | — |
| `config/` | Paramètres de l'application (clés API hors dépôt) | ⬜ À créer | — |
| `tests/` | Tests automatisés | ⬜ À créer | — |
| `migrations/` | Migrations de schéma Alembic | ⬜ À créer | — |
<!-- AUTO:ARCHITECTURE:END -->

---

## 🚀 Installation

> Ces commandes fonctionneront une fois l'application initialisée
> (première étape de la [feuille de route](docs/ROADMAP.md)).

```bash
git clone https://github.com/Rakal-I/Code_Fin.git
cd Code_Fin
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head             # crée ou met à jour la base SQLite locale
streamlit run app/main.py
```

---

## 🗂️ Structure du dépôt

<!-- AUTO:STRUCTURE:START -->
```text
Code_Fin/
├── .github/
│   └── workflows/
│       └── update-readme.yml
├── assets/
│   ├── icon.svg
│   ├── logo-dark.svg
│   └── logo.svg
├── docs/
│   ├── cahier_des_charges.md
│   └── ROADMAP.md
├── scripts/
│   ├── generate_logo.py
│   └── update_readme.py
├── .gitignore
└── README.md
```
<!-- AUTO:STRUCTURE:END -->

---

## 📊 Statistiques du code

<!-- AUTO:STATS:START -->
| Langage | Fichiers | Lignes (hors vides) |
|---|---|---|
| Autres | 4 | 57 |
| Markdown | 3 | 671 |
| Python | 2 | 417 |
| YAML | 1 | 43 |
| **Total** | **10** | **1188** |

**Tests automatisés détectés :** 0

**Stack cible** (dépendances lues dans `requirements*.txt` / `pyproject.toml`) :

| Brique | Paquet | Déclaré |
|---|---|---|
| Streamlit | `streamlit` | ⬜ |
| SQLAlchemy | `sqlalchemy` | ⬜ |
| Alembic | `alembic` | ⬜ |
| Pandas | `pandas` | ⬜ |
| Pydantic | `pydantic` | ⬜ |
| Plotly | `plotly` | ⬜ |
| yfinance | `yfinance` | ⬜ |
| Finnhub | `finnhub-python` | ⬜ |
<!-- AUTO:STATS:END -->

---

## 📝 Derniers changements

<!-- AUTO:COMMITS:START -->
| Commit | Date | Auteur | Message |
|---|---|---|---|
| `3ec2ab1` | 26/10/2026 | Claude | Remplace l'ancre par un logo abstrait « sommet » |
| `37b926f` | 26/10/2026 | Claude | Renomme l'application en « Ancora » avec un logo en forme d'ancre |
| `0a47799` | 26/10/2026 | Claude | Refait le logo Vigie dans un style minimaliste façon Apple |
| `6be385f` | 26/10/2026 | Claude | Nomme l'application « Vigie » et ajoute son logo |
| `9057d72` | 26/10/2026 | Claude | Ignore les commits du bot dans l'en-tête du README |
| `af4a092` | 26/10/2026 | Claude | Ajoute un README auto-mis à jour et le cahier des charges |
<!-- AUTO:COMMITS:END -->

---

## 🌐 Sources de données et limitations

| Rôle | Source |
|---|---|
| Principale | Yahoo Finance / `yfinance` |
| Secondaire | Finnhub |
| Réglementaire | SEC EDGAR (sociétés américaines) |
| Secours | Saisie manuelle |

Certaines données ne sont pas garanties gratuitement pour tous les marchés :
consensus des analystes, objectifs de cours, nombre d'analystes, dividendes
futurs, estimations de BNA. Quand elles manquent, l'application affiche
**« Non disponible »**.

---

## 🔒 Sécurité et confidentialité

- Données stockées **uniquement en local** (base SQLite).
- Clés API protégées et jamais versionnées (voir [`.gitignore`](.gitignore)).
- **Aucune** transmission des positions aux fournisseurs de données.
- Possibilité de masquer les montants à l'écran.
- Aucune donnée sensible dans les logs.

---

## 🤖 Mise à jour automatique de ce README

Les sections encadrées par des marqueurs `<!-- AUTO:…:START -->` /
`<!-- AUTO:…:END -->` sont régénérées après **chaque push**, sur toutes les
branches, par le workflow
[`.github/workflows/update-readme.yml`](.github/workflows/update-readme.yml) :

1. GitHub Actions lance [`scripts/update_readme.py`](scripts/update_readme.py)
   (bibliothèque standard Python uniquement).
2. Le script recalcule l'en-tête, l'avancement, l'architecture, la structure,
   les statistiques et les derniers commits à partir des fichiers suivis par git.
3. Si le README a changé, le bot crée un commit
   `docs(readme): mise à jour automatique [readme-bot] [skip ci]`.

**Tout le reste du fichier est rédigé à la main et n'est jamais modifié par le script.**

Pour mettre à jour le README en local :

```bash
python scripts/update_readme.py          # régénère les sections
python scripts/update_readme.py --check  # vérifie seulement (code retour 1 si pas à jour)
```

> 💡 Comme le bot ajoute un commit après vos pushs, pensez à faire un
> `git pull` avant de recommencer à travailler sur une branche.

Pour ajouter une section automatique : placez une paire de marqueurs dans le
README, puis ajoutez la fonction correspondante dans `render()` du script.

---

## 🎨 Identité visuelle

**Ancora** signifie « ancre » en italien et en portugais, et se prononce de la
même façon dans la plupart des langues. Le nom porte l'idée d'un point
d'ancrage : une source unique et stable de référence pour tout le patrimoine,
qui tient bon quand les marchés bougent.

L'identité est **noir et blanc, minimaliste et abstraite**, dans l'esprit des
icônes Apple. L'icône est une superellipse noire (coins continus). Elle porte un
**anneau de répartition** en trois segments d'un même blanc, de plus en plus
transparents : c'est le patrimoine vu comme un tout, réparti entre ses
enveloppes. Sur fond sombre, l'icône du logo s'inverse (fond blanc, anneau noir).

| Fichier | Usage |
|---|---|
| [`assets/logo.svg`](assets/logo.svg) | Logo complet, fond clair |
| [`assets/logo-dark.svg`](assets/logo-dark.svg) | Logo complet, fond sombre (icône inversée) |
| [`assets/icon.svg`](assets/icon.svg) | Icône seule (favicon Streamlit, avatar) |

| Rôle | Valeur |
|---|---|
| Couleurs | noir `#000000` · blanc `#FFFFFF` · gris `#8E8E93` (texte secondaire) |
| Anneau | segments de 50 %, 30 % et 20 %, opacités 100 %, 62 % et 34 % |
| Typographie | Inter Display Light en minuscules, convertie en tracés (rendu identique partout) |

Les SVG sont produits par [`scripts/generate_logo.py`](scripts/generate_logo.py)
(nécessite `pip install fonttools` et la police Inter Display).

---

## 📚 Documentation

- [Cahier des charges fonctionnel et technique](docs/cahier_des_charges.md) (version 1.0, octobre 2026)
- [Feuille de route et critères de recette](docs/ROADMAP.md)
