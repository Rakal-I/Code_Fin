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

Deux interfaces partagent la même base et les mêmes règles de calcul :

| | 💻 Ordinateur | 📱 Téléphone |
|---|---|---|
| Rôle | Tout : consultation, saisie, administration, sauvegardes | Consultation, simple et rapide |
| Technologie | Streamlit | Web-app au style iOS, installable sur l'écran d'accueil |
| Lancement | `streamlit run streamlit_app.py` | `python -m app.mobile` |

> ⚠️ **Usage strictement personnel.** Cette application n'est pas un outil
> de conseil en investissement et ne formule aucune recommandation d'achat
> ou de vente.

<!-- AUTO:META:START -->
> 🔄 **Dernière mise à jour :** 26/10/2026 12:05 (heure de Paris) · commit `b0679e5` · 10 commits au total
<!-- AUTO:META:END -->

---

## Sommaire

1. [Avancement](#-avancement)
2. [Fonctionnalités](#-fonctionnalités)
3. [Règles de calcul](#-règles-de-calcul)
4. [Qualité des données](#-qualité-des-données)
5. [Stack technique et architecture](#-stack-technique-et-architecture)
6. [Installation](#-installation)
7. [Version téléphone](#-version-téléphone)
8. [Structure du dépôt](#-structure-du-dépôt)
9. [Statistiques du code](#-statistiques-du-code)
10. [Derniers changements](#-derniers-changements)
11. [Sources de données et limitations](#-sources-de-données-et-limitations)
12. [Sécurité et confidentialité](#-sécurité-et-confidentialité)
13. [Mise à jour automatique de ce README](#-mise-à-jour-automatique-de-ce-readme)
14. [Identité visuelle](#-identité-visuelle)
15. [Documentation](#-documentation)

---

## 📈 Avancement

Calculé à partir des cases cochées dans [`docs/ROADMAP.md`](docs/ROADMAP.md).

<!-- AUTO:PROGRESS:START -->
| Étape | Avancement | Fait |
|---|---|---|
| Version 1 — MVP | `██████████` 100 % | 17/17 |
| Critères de recette | `██████████` 100 % | 13/13 |
| Version 2 — Nouveaux actifs | `░░░░░░░░░░` 0 % | 0/3 |
| Version 3 — Imports | `░░░░░░░░░░` 0 % | 0/2 |
| Version 4 — Mobilité | `███░░░░░░░` 33 % | 1/3 |
| Application iOS native (App Store) | `░░░░░░░░░░` 0 % | 0/6 |
| Version 5 — Assistant | `░░░░░░░░░░` 0 % | 0/2 |
| **Total** | `███████░░░` 67 % | **31/46** |
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

Conventions retenues là où le cahier des charges laisse le choix :

- **Frais d'achat** : inclus dans le PRU. Les frais de vente diminuent la plus-value réalisée.
- **Taux de change** : `1 EUR = x devise` (montant en EUR = montant / taux). Pour un achat,
  le taux saisi est prioritaire ; à défaut, le taux connu du jour (ou des 7 jours précédents) ;
  sinon le montant en EUR est indiqué indisponible.
- **Effet de change** : effet de marché = plus-value en devise convertie au taux moyen d'achat ;
  effet de change = plus-value en EUR − effet de marché.
- **Correction** : ajuste la quantité au PRU courant et/ou redéfinit le PRU de la ligne.
- **Vente supérieure au stock** : refusée à la saisie, avec un message explicite.
- **Totaux consolidés** : une ligne sans cours ou sans taux de change est exclue des totaux
  et signalée, jamais comptée pour zéro.

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

**Technologies :** Python 3.11+ · Streamlit · SQLite · SQLAlchemy · Alembic ·
Pandas · Pydantic · Plotly · yfinance · FastAPI (version téléphone).

Le point d'entrée est [`streamlit_app.py`](streamlit_app.py), à la racine. Les dossiers de
l'architecture cible sont regroupés dans le paquet `app/` ; `tests/` et `migrations/` sont à la racine.
La version téléphone vit dans `app/mobile/` : une API JSON (FastAPI) qui réutilise les services,
et une web-app statique (HTML, CSS, JavaScript sans dépendance) dans `app/mobile/static/`.
La base SQLite est en mode WAL : les deux interfaces la lisent pendant qu'une actualisation écrit.

État de l'architecture cible (§19 du cahier des charges), recalculé à chaque push :

<!-- AUTO:ARCHITECTURE:START -->
| Dossier | Rôle | État | Fichiers Python |
|---|---|---|---|
| `app/` | Paquet de l'application (point d'entrée : streamlit_app.py) | ✅ Présent | 11 |
| `app/pages/` | Pages et tableaux de bord Streamlit | ✅ Présent | 8 |
| `app/domain/` | Règles métier : PRU, valorisation, plus-values, devises | ✅ Présent | 5 |
| `app/services/` | Orchestration : actualisation, sauvegarde, archivage | ✅ Présent | 6 |
| `app/connectors/` | Fournisseurs de données : yfinance, Finnhub, SEC EDGAR, saisie manuelle | ✅ Présent | 6 |
| `app/models/` | Modèles SQLAlchemy et schémas Pydantic | ✅ Présent | 4 |
| `app/database/` | Accès SQLite et gestion des sessions | ✅ Présent | 2 |
| `config/`, `app/config/` | Paramètres de l'application (clés API hors dépôt) | ✅ Présent | 2 |
| `tests/` | Tests automatisés | ✅ Présent | 7 |
| `migrations/` | Migrations de schéma Alembic | ✅ Présent | 2 |
<!-- AUTO:ARCHITECTURE:END -->

---

## 🚀 Installation

```bash
git clone https://github.com/Rakal-I/Code_Fin.git
cd Code_Fin
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

L'application s'ouvre sur http://localhost:8501. Au premier lancement, elle crée la base
`data/ancora.db` (migrations Alembic appliquées automatiquement) et ajoute les indices de
référence (CAC 40, Euro Stoxx 50, S&P 500, Nasdaq, MSCI World, MSCI EM).

**Premiers pas**

1. *Administration › Enveloppes* : créez vos enveloppes (PEA, assurance-vie, CTO…).
2. *Administration › Instruments* : ajoutez vos instruments. Pour Yahoo Finance, le
   « symbole fournisseur » porte le suffixe de la place (`MC.PA` pour Paris, `ASML.AS`
   pour Amsterdam ; rien pour les actions américaines).
3. *Saisie › Position initiale* : reprenez vos positions existantes (quantité, PRU, date de reprise).
4. **Actualiser tout** (barre latérale) : cours, historiques, fondamentaux et taux de change.
5. *Saisie › Opération* : enregistrez ensuite vos achats, ventes, dividendes, apports…

**Essayer avec des données fictives** (base séparée, cours réels) :

```bash
python scripts/demo_data.py data/demo.db
ANCORA_DB_PATH=data/demo.db streamlit run streamlit_app.py
```

**Sources optionnelles** : copiez [`config/secrets.example.toml`](config/secrets.example.toml) en
`config/secrets.toml` (jamais versionné) pour activer Finnhub et SEC EDGAR.

**Variables d'environnement** : `ANCORA_DB_PATH`, `ANCORA_BACKUP_DIR`, `ANCORA_LOG_DIR`,
`FINNHUB_API_KEY`, `SEC_USER_AGENT`.

**Tests** (aucun appel réseau : un fournisseur simulé est utilisé) :

```bash
pip install -r requirements-dev.txt
ruff check .
pytest            # dont tests/test_recette.py : les 13 critères de recette
```

---

## 📱 Version téléphone

Une interface simplifiée, pensée comme une app iPhone au style « Liquid Glass » : grands titres,
panneaux en verre, barre d'onglets flottante, mode sombre automatique.

| Onglet | Contenu |
|---|---|
| **Patrimoine** | Valorisation totale, plus-value latente, anneau de répartition (enveloppes ou types d'actifs), positions |
| **Marchés** | Instruments suivis, détenus ou indices, cours et performance sur la période choisie ; fiche détaillée |
| **Revenus** | Revenus des 12 derniers mois, histogramme mensuel, derniers versements |
| **Réglages** | Masquer les montants, actualiser les données, qualité des données |

Gestes et détails : tirer l'écran vers le bas pour actualiser, toucher un segment de l'anneau
(ou une ligne de légende) pour l'isoler, toucher un mois pour lire son montant, parcourir le
graphique du doigt, rechercher dans Marchés. La barre d'onglets flottante se fait discrète
pendant le défilement.

La saisie et l'administration restent sur l'ordinateur, volontairement : le téléphone sert à consulter.

**Lancer** (sur l'ordinateur qui héberge Ancora) :

```bash
python -m app.mobile          # http://127.0.0.1:8502
```

**Y accéder depuis l'iPhone, en restant privé** (recommandé : [Tailscale](https://tailscale.com), gratuit
pour un usage personnel) :

1. Installez Tailscale sur l'ordinateur et sur l'iPhone, avec le même compte.
2. Sur l'ordinateur : `tailscale serve --bg 8502` (la commande affiche une adresse
   `https://<ordinateur>.<réseau>.ts.net`, accessible uniquement depuis vos appareils).
3. Sur l'iPhone, ouvrez cette adresse dans Safari, puis **Partager › Sur l'écran d'accueil** :
   Ancora s'ouvre ensuite comme une app, avec son icône.

> ⚠️ Le serveur n'écoute que sur l'ordinateur (127.0.0.1) et n'a pas d'authentification propre :
> passez par Tailscale ou Cloudflare Tunnel + Access plutôt que d'ouvrir le port sur votre réseau.
> Variables : `ANCORA_MOBILE_HOST`, `ANCORA_MOBILE_PORT`.

---

## 🗂️ Structure du dépôt

<!-- AUTO:STRUCTURE:START -->
```text
Code_Fin/
├── .github/
│   └── workflows/
│       ├── tests.yml
│       └── update-readme.yml
├── .streamlit/
│   └── config.toml
├── app/
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── finnhub.py
│   │   ├── registry.py
│   │   ├── sec_edgar.py
│   │   └── yahoo.py
│   ├── database/
│   │   ├── __init__.py
│   │   └── engine.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── fundamentals.py
│   │   ├── performance.py
│   │   ├── portfolio.py
│   │   └── quality.py
│   ├── mobile/
│   │   ├── static/  (7 fichiers)
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   └── server.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── entities.py
│   │   ├── enums.py
│   │   └── schemas.py
│   ├── pages/
│   │   ├── admin.py
│   │   ├── dashboard.py
│   │   ├── entry.py
│   │   ├── envelopes.py
│   │   ├── income.py
│   │   ├── markets.py
│   │   ├── portfolio.py
│   │   └── quality.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── backup.py
│   │   ├── logging_setup.py
│   │   ├── market_data.py
│   │   ├── portfolio.py
│   │   └── referential.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── context.py
│   │   ├── fiche.py
│   │   ├── formatting.py
│   │   ├── theme.py
│   │   └── views.py
│   ├── __init__.py
│   └── bootstrap.py
├── assets/
│   ├── icon-square.svg
│   ├── icon.svg
│   ├── logo-dark.svg
│   └── logo.svg
├── config/
│   └── secrets.example.toml
├── docs/
│   ├── cahier_des_charges.md
│   └── ROADMAP.md
├── migrations/
│   ├── versions/
│   │   └── 0001_schema_initial.py
│   ├── env.py
│   └── script.py.mako
├── scripts/
│   ├── demo_data.py
│   ├── generate_logo.py
│   └── update_readme.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_domain.py
│   ├── test_mobile.py
│   ├── test_recette.py
│   ├── test_services.py
│   └── test_ui.py
├── .gitignore
├── alembic.ini
├── pyproject.toml
├── README.md
├── requirements-dev.txt
├── requirements.txt
└── … (+1 éléments)
```
<!-- AUTO:STRUCTURE:END -->

---

## 📊 Statistiques du code

<!-- AUTO:STATS:START -->
| Langage | Fichiers | Lignes (hors vides) |
|---|---|---|
| Python | 57 | 5200 |
| Autres | 10 | 61 |
| Markdown | 3 | 772 |
| TOML | 3 | 44 |
| Texte | 2 | 18 |
| YAML | 2 | 71 |
| CSS | 1 | 288 |
| HTML | 1 | 58 |
| INI | 1 | 29 |
| JavaScript | 1 | 551 |
| **Total** | **81** | **7092** |

**Tests automatisés détectés :** 66

**Stack cible** (dépendances lues dans `requirements*.txt` / `pyproject.toml`) :

| Brique | Paquet | Déclaré |
|---|---|---|
| Streamlit | `streamlit` | ✅ |
| SQLAlchemy | `sqlalchemy` | ✅ |
| Alembic | `alembic` | ✅ |
| Pandas | `pandas` | ✅ |
| Pydantic | `pydantic` | ✅ |
| Plotly | `plotly` | ✅ |
| yfinance | `yfinance` | ✅ |
| FastAPI (téléphone) | `fastapi` | ✅ |
<!-- AUTO:STATS:END -->

---

## 📝 Derniers changements

<!-- AUTO:COMMITS:START -->
| Commit | Date | Auteur | Message |
|---|---|---|---|
| `b0679e5` | 26/10/2026 | Claude | Passe les deux interfaces au style « Liquid Glass » et aligne les graphiques sur le logo |
| `646afaf` | 26/10/2026 | Claude | Ajoute la version téléphone d'Ancora (web-app au style iOS) |
| `5846c7e` | 26/10/2026 | Claude | Crée l'application Ancora (version 1 du cahier des charges) |
| `e3439a9` | 26/10/2026 | Claude | Nouvelle identité Ancora : anneau de répartition en noir et blanc |
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

Constats lors des essais :

- **Dividende N+1** et **nombre d'analystes sur le dividende** : aucune source gratuite
  configurée ne les fournit ; ils s'affichent « Non disponible » (saisie manuelle possible).
- **Dividende N** : taux annuel prévisionnel publié par Yahoo (`dividendRate`), marqué « Estimée ».
- **MSCI Emerging Markets** : Yahoo ne fournit que le dernier cours, pas d'historique :
  les performances de cet indice restent N/A.
- **Finnhub** : selon l'abonnement, les objectifs de cours peuvent être réservés à l'offre
  payante ; un accès refusé est tracé comme erreur et Yahoo reste la source utilisée.
- **SEC EDGAR** : BNA dilués des rapports annuels 10-K, sociétés américaines uniquement.

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

**Interfaces : style « Liquid Glass ».** Panneaux en verre dépoli (flou, reflet sur le bord
supérieur, ombre douce) posés sur une lumière ambiante, contrôles en capsules, fenêtres et
barres flottantes. En mode sombre, le verre devient fumé.

**Graphiques : la règle du logo.**

| Élément | Règle |
|---|---|
| Couleur | Un seul ton : noir (blanc en mode sombre) |
| Répartitions | Anneau aux extrémités arrondies, fines ouvertures entre segments, opacités 100 %, 62 %, 34 % (puis 20 %, 12 %, 7 %) |
| Barres | Capsules ; pleines si mises en avant, sinon 34 % |
| Courbes | Trait noir arrondi, dégradé translucide dessous, point sur le dernier cours |
| Gains / pertes | Seule exception colorée : vert et rouge, pour la lisibilité |

Les SVG sont produits par [`scripts/generate_logo.py`](scripts/generate_logo.py)
(nécessite `pip install fonttools` et la police Inter Display).

---

## 📚 Documentation

- [Cahier des charges fonctionnel et technique](docs/cahier_des_charges.md) (version 1.0, octobre 2026)
- [Feuille de route et critères de recette](docs/ROADMAP.md)
