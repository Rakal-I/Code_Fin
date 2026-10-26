# Feuille de route

Cochez une case (`- [x]`) quand une étape est terminée : le tableau
d'avancement du README est recalculé automatiquement à chaque push.

Référence : [cahier des charges](cahier_des_charges.md), §22 et §23.

## Version 1 — MVP

- [x] Initialisation du projet (Streamlit, SQLite, SQLAlchemy, Alembic)
- [x] Référentiel des instruments (actions, ETF, fonds, UC, indices)
- [x] Gestion des enveloppes (PEA, PEA-PME, assurance-vie, PER, CTO, autres)
- [x] Positions initiales sans historique de transactions
- [x] Saisie des opérations (achat, vente, dividende, distribution, coupon, apport, retrait, frais, correction)
- [x] Calcul du PRU (prix de revient moyen pondéré) et des plus-values réalisées
- [x] Valorisation et plus-values latentes
- [x] Gestion multi-devises (consolidation en EUR, effet de change)
- [x] Performances (1 sem., 1 mois, 6 mois, 1 an, 5 ans, 10 ans)
- [x] Données fondamentales (dividendes, BNA, consensus, potentiel)
- [x] Qualité et provenance des données (source, dates, statut)
- [x] Connecteurs : yfinance, Finnhub, SEC EDGAR, saisie manuelle
- [x] Actualisation manuelle non bloquante
- [x] Tableaux de bord (global, marchés, portefeuille, enveloppes, revenus, qualité, administration)
- [x] Archivage des instruments (aucune suppression physique)
- [x] Sauvegarde, restauration et vérification d'intégrité
- [x] Masquage des montants et protection des clés API

## Critères de recette

- [x] Un instrument peut être créé et suivi
- [x] Une position initiale peut être créée
- [x] Une opération peut être enregistrée
- [x] Les performances sont calculées correctement
- [x] La valorisation est correcte
- [x] Les devises sont correctement converties
- [x] Les erreurs sont visibles
- [x] Les sources sont consultables
- [x] Les sauvegardes fonctionnent
- [x] La restauration fonctionne
- [x] Les données persistent après redémarrage
- [x] Aucune donnée n'est inventée
- [x] Un instrument archivé reste consultable

## Comptes et sécurité

- [x] Connexion obligatoire (ordinateur et téléphone)
- [x] Plusieurs comptes, données séparées
- [x] Connexion avec Google et Apple
- [x] Données de chaque compte chiffrées avec sa propre clé
- [ ] Suppression d'un compte depuis l'interface

## Version 2 — Nouveaux actifs

- [ ] Obligations
- [ ] Fonds euros
- [ ] Produits structurés

## Version 3 — Imports

- [ ] Import CSV
- [ ] Import Excel

## Version 4 — Mobilité

- [x] Smartphone : web-app installable sur l'écran d'accueil (consultation, actualisation, masquage)
- [ ] Tablette : mise en page dédiée (la version téléphone fonctionne, centrée)
- [ ] Synchronisation cloud

## Application iOS native (App Store)

- [ ] Choisir la technologie : SwiftUI (natif) ou multiplateforme (Flutter, React Native)
- [ ] Porter les règles de calcul (les tests actuels servent de cahier de vérification)
- [ ] Stockage local sur l'iPhone, sauvegarde iCloud facultative
- [ ] Fournisseur de cours sous licence et petit serveur intermédiaire pour protéger sa clé
- [ ] Compte Apple Developer, politique de confidentialité, fiche « App Privacy »
- [ ] Bêta TestFlight, puis soumission à l'App Store

## Version 5 — Assistant

- [ ] Assistant IA
- [ ] Requêtes en langage naturel
