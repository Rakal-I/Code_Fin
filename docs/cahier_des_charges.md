# Cahier des charges fonctionnel et technique

## Application personnelle de suivi patrimonial et financier

| | |
|---|---|
| **Version** | 1.0 |
| **Date** | Octobre 2026 |
| **Statut** | Version de référence |

---

## 1. Objet du projet

Le projet consiste à concevoir une application personnelle permettant de
suivre, centraliser, analyser et valoriser un patrimoine financier détenu au
travers de plusieurs enveloppes d'investissement.

L'application doit constituer une source unique d'information patrimoniale et
financière, capable de regrouper :

- données de marché ;
- données fondamentales ;
- positions détenues ;
- revenus ;
- performances ;
- qualité et provenance des données.

L'application est exclusivement destinée à un usage personnel.

L'application n'est pas un outil de conseil en investissement et ne doit
formuler aucune recommandation d'achat ou de vente.

## 2. Objectifs

L'application doit permettre :

- le suivi des actifs détenus ;
- le suivi d'une liste de surveillance ;
- le suivi de plusieurs enveloppes ;
- la valorisation consolidée du patrimoine ;
- l'analyse des performances ;
- le suivi des revenus financiers ;
- la consultation de données fondamentales ;
- la traçabilité de toutes les données affichées ;
- la gestion des données manquantes ou obsolètes.

## 3. Périmètre fonctionnel MVP

### Actifs couverts

**Actions**

- États-Unis
- Europe

**ETF**

- capitalisants
- distribuants

**Fonds**

- OPCVM
- SICAV
- FCP

**Unités de compte**

- assurance-vie
- PER

**Indices**

- CAC 40
- Euro Stoxx 50
- S&P 500
- Nasdaq
- MSCI World
- MSCI Emerging Markets
- autres indices paramétrables

## 4. Hors périmètre MVP

Prévu pour les versions ultérieures :

- obligations
- fonds euros
- produits structurés
- private equity
- immobilier non coté
- cryptomonnaies

## 5. Gestion des enveloppes

Les enveloppes suivantes doivent être gérées :

- PEA
- PEA-PME
- Assurance-vie
- PER
- CTO
- Autres enveloppes

Informations stockées :

- nom
- établissement
- contrat
- devise de référence
- commentaire

## 6. Données instrument

### Identité

Chaque instrument doit conserver :

- identifiant interne
- nom
- type
- ticker
- ISIN
- place de cotation
- devise
- pays
- société ou gestionnaire

Le ticker seul ne doit jamais être utilisé comme identifiant unique.

### Données de marché

- dernier cours ou VL
- devise
- source
- date de référence
- date de collecte

### Performances

- 1 semaine
- 1 mois
- 6 mois
- 1 an
- 5 ans
- 10 ans

Règles :

- aucune extrapolation
- aucune estimation
- N/A si l'historique est insuffisant

## 7. Données fondamentales

### Dividendes

Lorsque applicables :

- dividende N
- dividende N+1
- nombre d'analystes
- date de détachement
- date de paiement

### Bénéfice Net par Action

- Y-3
- Y-2
- Y-1
- Y
- Y+1

Chaque donnée doit être associée à son exercice fiscal réel.

### Consensus analystes

Lorsque disponible :

- objectif moyen
- objectif bas
- objectif haut
- nombre d'analystes

### Potentiel

Calcul :

```text
(Objectif moyen / cours actuel - 1) × 100
```

## 8. Qualité des données

Chaque information doit conserver :

- valeur
- source
- date de référence
- date de collecte
- statut

### Statuts

- Réelle
- Estimée
- Calculée
- Manuelle
- Non disponible
- Non applicable
- Obsolète
- Erreur

### Règles

Une donnée absente ne doit jamais être remplacée par :

- 0
- une estimation automatique
- une valeur calculée arbitrairement

## 9. Positions initiales

L'utilisateur doit pouvoir créer une position existante sans historique de
transactions.

Champs obligatoires :

- instrument
- quantité
- PRU
- devise
- date de reprise
- enveloppe
- établissement
- contrat

## 10. Opérations futures

Types d'opérations :

- achat
- vente
- dividende
- distribution
- coupon
- apport
- retrait
- frais
- correction

Informations stockées :

- date
- instrument
- montant
- quantité
- prix unitaire
- devise
- frais
- commentaire

## 11. Calculs patrimoniaux

### Valorisation

```text
Quantité × cours actuel
```

### Plus-value latente

```text
Valeur actuelle − coût d'acquisition
```

### Plus-value latente %

```text
(Valeur actuelle / coût d'acquisition - 1) × 100
```

### PRU

Méthode : prix de revient moyen pondéré.

### Règle de vente

Une vente :

- diminue la quantité détenue ;
- ne modifie pas le PRU de la quantité restante ;
- génère une plus-value ou moins-value réalisée.

## 12. Gestion multi-devises

Devise de consolidation :

```text
EUR
```

Conserver :

- devise de l'actif
- devise de transaction
- devise de consolidation
- taux de change
- date du taux
- source du taux

L'application doit distinguer :

- performance de marché
- effet de change

## 13. Actualisation

### Actualisation manuelle

- tous les instruments
- instrument individuel

### Démarrage

Au démarrage :

- utilisation immédiate des données locales
- vérification de la fraîcheur
- actualisation à la demande

L'interface ne doit jamais être bloquée par un fournisseur externe
indisponible.

## 14. Tableaux de bord

### Tableau de bord global

- valorisation totale
- plus-value totale
- répartition par enveloppe
- répartition par type d'actifs

### Marchés

- liste des instruments suivis
- cours
- performances
- fondamentaux

### Portefeuille

- positions
- valorisation
- gains/pertes

### Enveloppes

- vue par contrat
- vue par enveloppe

### Revenus

- dividendes
- distributions
- coupons

### Qualité des données

- origine
- fraîcheur
- erreurs
- historique

### Administration

- ajout
- archivage
- actualisation
- sauvegarde
- paramètres

## 15. Archivage

Un instrument ne doit jamais être supprimé physiquement lorsqu'il possède :

- une position ;
- une opération ;
- un historique.

Dans ce cas il doit être **archivé** et rester disponible à la consultation
historique.

## 16. Interface utilisateur

L'interface doit être :

- simple
- lisible
- orientée tableaux
- adaptée à un investisseur particulier

### Codes visuels

| Code | Signification |
|---|---|
| 🟢 | Valide |
| 🔵 | Estimation |
| 🟠 | Obsolète |
| ⚪ | Non disponible |
| ⚫ | Non applicable |
| 🔴 | Erreur |

La couleur ne doit jamais être l'unique moyen de transmettre l'information.

## 17. Sauvegarde et restauration

Fonctionnalités obligatoires :

- sauvegarde complète
- restauration
- vérification d'intégrité
- historique des sauvegardes

## 18. Sécurité et confidentialité

Exigences :

- stockage local uniquement
- protection des clés API
- aucune transmission des positions aux fournisseurs
- masquage possible des montants
- aucune donnée sensible dans les logs

## 19. Architecture technique

Technologies cibles :

- Python
- Streamlit
- SQLite
- SQLAlchemy
- Alembic
- Pandas
- Pydantic
- Plotly

Architecture :

```text
/app
/pages
/domain
/services
/connectors
/models
/database
/config
/tests
/migrations
```

## 20. Contraintes de qualité logicielle

Le système doit :

- journaliser les erreurs ;
- conserver les données même après fermeture ;
- permettre les migrations futures ;
- être maintenable ;
- être documenté ;
- être testable automatiquement.

## 21. Limitations connues

Certaines données ne peuvent être garanties gratuitement pour tous les
marchés :

- consensus analystes
- objectifs de cours
- nombre d'analystes
- dividendes futurs
- estimations de BNA

Lorsque ces données sont indisponibles, **« Non disponible »** doit être
affiché.

## 22. Roadmap

### Version 1

- instruments
- portefeuille
- valorisation
- performances
- sauvegarde

### Version 2

- obligations
- fonds euros
- produits structurés

### Version 3

- import CSV
- import Excel

### Version 4

- tablette
- smartphone
- synchronisation cloud

### Version 5

- assistant IA
- requêtes en langage naturel

## 23. Critères de recette

Le projet sera considéré conforme lorsque :

- ✅ un instrument peut être créé et suivi
- ✅ une position initiale peut être créée
- ✅ une opération peut être enregistrée
- ✅ les performances sont calculées correctement
- ✅ la valorisation est correcte
- ✅ les devises sont correctement converties
- ✅ les erreurs sont visibles
- ✅ les sources sont consultables
- ✅ les sauvegardes fonctionnent
- ✅ la restauration fonctionne
- ✅ les données persistent après redémarrage
- ✅ aucune donnée n'est inventée
- ✅ un instrument archivé reste consultable

---

## Annexe A — Matrice d'applicabilité des données

| Donnée | Action | ETF | Fonds / UC | Indice |
|---|---|---|---|---|
| Cours / VL | Oui | Oui | Oui | Oui |
| Performance | Oui | Oui | Oui | Oui |
| Dividende historique | Oui | Variable | Variable | Non |
| Dividende futur | Oui | Rare | Rare | Non |
| Date détachement | Oui | Variable | Non | Non |
| Date paiement | Oui | Variable | Non | Non |
| BNA historique | Oui | Non applicable | Non applicable | Non applicable |
| BNA futur | Oui | Non applicable | Non applicable | Non applicable |
| Objectif de cours | Oui | Rare | Non applicable | Non applicable |
| Nombre d'analystes | Oui | Rare | Non applicable | Non applicable |
| TER | Non applicable | Oui | Oui | Non applicable |
| Encours | Non applicable | Oui | Oui | Non applicable |
| Société de gestion | Non applicable | Oui | Oui | Non applicable |

## Annexe B — Sources de données envisagées

| Source | Actions | ETF | Fonds | Consensus | Gratuité |
|---|---|---|---|---|---|
| Yahoo Finance / yfinance | Oui | Oui | Partiel | Limité | Oui |
| Finnhub | Oui | Oui | Partiel | Oui | Partiel |
| Financial Modeling Prep | Oui | Oui | Partiel | Oui | Partiel |
| SEC EDGAR | USA | Non | Non | Non | Oui |
| Saisie manuelle | Oui | Oui | Oui | Oui | Oui |

### Stratégie retenue

| Rôle | Source |
|---|---|
| Source principale | Yahoo Finance / yfinance |
| Source secondaire | Finnhub |
| Source réglementaire | SEC EDGAR |
| Source de secours | Saisie manuelle |
