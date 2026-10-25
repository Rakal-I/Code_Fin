# Feuille de route

Cochez une case (`- [x]`) quand une étape est terminée : le tableau
d'avancement du README est recalculé automatiquement à chaque push.

Référence : [cahier des charges](cahier_des_charges.md), §22 et §23.

## Version 1 — MVP

- [ ] Initialisation du projet (Streamlit, SQLite, SQLAlchemy, Alembic)
- [ ] Référentiel des instruments (actions, ETF, fonds, UC, indices)
- [ ] Gestion des enveloppes (PEA, PEA-PME, assurance-vie, PER, CTO, autres)
- [ ] Positions initiales sans historique de transactions
- [ ] Saisie des opérations (achat, vente, dividende, distribution, coupon, apport, retrait, frais, correction)
- [ ] Calcul du PRU (prix de revient moyen pondéré) et des plus-values réalisées
- [ ] Valorisation et plus-values latentes
- [ ] Gestion multi-devises (consolidation en EUR, effet de change)
- [ ] Performances (1 sem., 1 mois, 6 mois, 1 an, 5 ans, 10 ans)
- [ ] Données fondamentales (dividendes, BNA, consensus, potentiel)
- [ ] Qualité et provenance des données (source, dates, statut)
- [ ] Connecteurs : yfinance, Finnhub, SEC EDGAR, saisie manuelle
- [ ] Actualisation manuelle non bloquante
- [ ] Tableaux de bord (global, marchés, portefeuille, enveloppes, revenus, qualité, administration)
- [ ] Archivage des instruments (aucune suppression physique)
- [ ] Sauvegarde, restauration et vérification d'intégrité
- [ ] Masquage des montants et protection des clés API

## Critères de recette

- [ ] Un instrument peut être créé et suivi
- [ ] Une position initiale peut être créée
- [ ] Une opération peut être enregistrée
- [ ] Les performances sont calculées correctement
- [ ] La valorisation est correcte
- [ ] Les devises sont correctement converties
- [ ] Les erreurs sont visibles
- [ ] Les sources sont consultables
- [ ] Les sauvegardes fonctionnent
- [ ] La restauration fonctionne
- [ ] Les données persistent après redémarrage
- [ ] Aucune donnée n'est inventée
- [ ] Un instrument archivé reste consultable

## Version 2 — Nouveaux actifs

- [ ] Obligations
- [ ] Fonds euros
- [ ] Produits structurés

## Version 3 — Imports

- [ ] Import CSV
- [ ] Import Excel

## Version 4 — Mobilité

- [ ] Tablette
- [ ] Smartphone
- [ ] Synchronisation cloud

## Version 5 — Assistant

- [ ] Assistant IA
- [ ] Requêtes en langage naturel
