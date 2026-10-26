"""Administration : ajout, archivage, actualisation, sauvegarde, paramètres (§14, §15, §17)."""
import pandas as pd
import streamlit as st
from pydantic import ValidationError

from app.config.settings import CONSOLIDATION_CURRENCY
from app.models.enums import SUBTYPES_BY_TYPE, EnvelopeType, InstrumentType
from app.models.schemas import EnvelopeIn, InstrumentIn
from app.services import auth, backup, market_data, oidc, referential
from app.services.referential import BusinessError, Preferences
from app.ui import context, login, theme, views
from app.web import connexion

theme.header("Administration", "Référentiel, actualisation, sauvegardes et paramètres.", kicker="Gestion")
cfg = context.config()
ws = context.workspace()


def show_errors(exc: Exception) -> None:
    if isinstance(exc, ValidationError):
        for error in exc.errors():
            st.error(str(error.get("msg", "")).removeprefix("Value error, "))
    else:
        st.error(str(exc))


tab_inst, tab_env, tab_refresh, tab_backup, tab_settings = st.tabs(
    ["Instruments", "Enveloppes", "Actualisation", "Sauvegardes", "Paramètres"])

# --------------------------------------------------------------------------
with tab_inst:
    with context.session() as s:
        instruments = referential.list_instruments(s, include_archived=True)
        has_history = {i.id: referential.instrument_has_history(s, i.id) for i in instruments}

    def instrument_form(key: str, current=None) -> InstrumentIn | None:
        types = [t.label for t in InstrumentType]
        c1, c2 = st.columns(2)
        type_label = c1.selectbox("Type", types, key=f"{key}_type",
                                  index=types.index(current.type.label) if current else 0)
        itype = next(t for t in InstrumentType if t.label == type_label)
        subtypes = ["—"] + [s.label for s in SUBTYPES_BY_TYPE[itype]]
        sub_index = subtypes.index(current.subtype.label) if current and current.subtype and \
            current.subtype.label in subtypes else 0
        sub_label = c2.selectbox("Sous-type", subtypes, index=sub_index, key=f"{key}_sub",
                                 disabled=len(subtypes) == 1)
        with st.form(f"{key}_form", border=False, clear_on_submit=current is None):
            name = st.text_input("Nom", value=current.name if current else "")
            c3, c4, c5 = st.columns(3)
            ticker = c3.text_input("Ticker", value=(current.ticker or "") if current else "")
            symbol = c4.text_input("Symbole fournisseur (ex. MC.PA)",
                                   value=(current.provider_symbol or "") if current else "",
                                   help="Symbole Yahoo Finance. Par défaut, le ticker est utilisé.")
            isin = c5.text_input("ISIN", value=(current.isin or "") if current else "")
            c6, c7, c8 = st.columns(3)
            exchange = c6.text_input("Place de cotation", value=(current.exchange or "") if current else "")
            currency = c7.text_input("Devise", value=current.currency if current else "EUR", max_chars=3)
            country = c8.text_input("Pays", value=(current.country or "") if current else "")
            issuer = st.text_input("Société ou gestionnaire", value=(current.issuer or "") if current else "")
            watch = st.checkbox("Dans la liste de surveillance", value=current.watchlist if current else True)
            submitted = st.form_submit_button("Enregistrer" if current else "Ajouter l'instrument", type="primary")
        if not submitted:
            return None
        subtype = next((s for s in SUBTYPES_BY_TYPE[itype] if s.label == sub_label), None)
        return InstrumentIn(name=name, type=itype, subtype=subtype, ticker=ticker, provider_symbol=symbol,
                            isin=isin, exchange=exchange, currency=currency, country=country, issuer=issuer,
                            watchlist=watch)

    with st.expander("Ajouter un instrument", expanded=not instruments, icon=":material/add:"):
        theme.note("Le ticker n'est jamais l'identifiant : chaque instrument reçoit un identifiant interne. "
                   "Un même ISIN peut être suivi sur plusieurs places de cotation.")
        try:
            data = instrument_form("new")
            if data:
                with context.session() as s:
                    referential.create_instrument(s, data)
                st.success(f"« {data.name} » ajouté. Actualisez-le pour récupérer ses données.")
                st.rerun()
        except (ValidationError, BusinessError) as exc:
            show_errors(exc)

    if instruments:
        frame = pd.DataFrame([{
            "#": i.id, "Nom": i.name, "Type": i.type.label, "Ticker": i.ticker or "—", "ISIN": i.isin or "—",
            "Place": i.exchange or "—", "Devise": i.currency,
            "Surveillance": "Oui" if i.watchlist else "Non",
            "État": "Archivé" if i.archived else "Actif",
        } for i in instruments])
        st.dataframe(frame, hide_index=True, width="stretch")

        st.subheader("Modifier, archiver ou supprimer")
        labels = {views.instrument_label(i): i for i in instruments}
        current = labels[st.selectbox("Instrument", list(labels), key="edit_inst")]
        try:
            data = instrument_form(f"edit{current.id}", current)
            if data:
                with context.session() as s:
                    referential.update_instrument(s, current.id, data)
                st.success("Instrument mis à jour.")
                st.rerun()
        except (ValidationError, BusinessError) as exc:
            show_errors(exc)
        c1, c2 = st.columns(2)
        if current.archived:
            if c1.button("Désarchiver", icon=":material/unarchive:", width="stretch"):
                with context.session() as s:
                    referential.unarchive_instrument(s, current.id)
                st.rerun()
        elif c1.button("Archiver", icon=":material/archive:", width="stretch"):
            with context.session() as s:
                referential.archive_instrument(s, current.id)
            st.rerun()
        label = "Supprimer (sera archivé : historique existant)" if has_history[current.id] else "Supprimer"
        if c2.button(label, icon=":material/delete:", width="stretch"):
            with context.session() as s:
                action = referential.remove_instrument(s, current.id)
            st.toast(f"Instrument {action}.")
            st.rerun()
        theme.note("Un instrument avec une position, une opération ou un historique n'est jamais supprimé : "
                   "il est archivé et reste consultable (Marchés › Archivés).")

# --------------------------------------------------------------------------
with tab_env:
    with context.session() as s:
        envelopes = referential.list_envelopes(s, include_archived=True)

    def envelope_form(key: str, current=None) -> EnvelopeIn | None:
        types = [t.label for t in EnvelopeType]
        with st.form(f"{key}_form", border=False, clear_on_submit=current is None):
            c1, c2 = st.columns(2)
            name = c1.text_input("Nom", value=current.name if current else "")
            type_label = c2.selectbox("Type", types, index=types.index(current.type.label) if current else 0)
            c3, c4, c5 = st.columns(3)
            institution = c3.text_input("Établissement", value=current.institution if current else "")
            contract = c4.text_input("Contrat", value=(current.contract or "") if current else "")
            currency = c5.text_input("Devise de référence", value=current.ref_currency if current else "EUR",
                                     max_chars=3)
            comment = st.text_area("Commentaire", value=(current.comment or "") if current else "", height=80)
            submitted = st.form_submit_button("Enregistrer" if current else "Créer l'enveloppe", type="primary")
        if not submitted:
            return None
        etype = next(t for t in EnvelopeType if t.label == type_label)
        return EnvelopeIn(name=name, type=etype, institution=institution, contract=contract,
                          ref_currency=currency, comment=comment)

    with st.expander("Créer une enveloppe", expanded=not envelopes, icon=":material/add:"):
        try:
            data = envelope_form("new_env")
            if data:
                with context.session() as s:
                    referential.create_envelope(s, data)
                st.success(f"Enveloppe « {data.name} » créée.")
                st.rerun()
        except ValidationError as exc:
            show_errors(exc)

    if envelopes:
        st.dataframe(pd.DataFrame([{
            "Nom": e.name, "Type": e.type.label, "Établissement": e.institution, "Contrat": e.contract or "—",
            "Devise": e.ref_currency, "État": "Archivée" if e.archived else "Active",
        } for e in envelopes]), hide_index=True, width="stretch")
        labels = {f"{e.name} · {e.institution}": e for e in envelopes}
        current = labels[st.selectbox("Enveloppe", list(labels), key="edit_env")]
        try:
            data = envelope_form(f"env{current.id}", current)
            if data:
                with context.session() as s:
                    referential.update_envelope(s, current.id, data)
                st.success("Enveloppe mise à jour.")
                st.rerun()
        except ValidationError as exc:
            show_errors(exc)
        toggle = "Désarchiver" if current.archived else "Archiver"
        if st.button(toggle, key="env_archive"):
            with context.session() as s:
                referential.set_envelope_archived(s, current.id, not current.archived)
            st.rerun()

# --------------------------------------------------------------------------
with tab_refresh:
    theme.note("Au démarrage, l'application affiche immédiatement les données locales. L'actualisation se fait à "
               "la demande ; si un fournisseur ne répond pas, l'erreur est enregistrée et les autres données "
               "restent disponibles.")
    with context.session() as s:
        active = [i for i in referential.list_instruments(s)]
    c1, c2 = st.columns(2)
    if c1.button("Actualiser tous les instruments", type="primary", icon=":material/refresh:", width="stretch"):
        with context.session() as s:
            bar = st.progress(0.0)
            results = market_data.refresh_all(s, context.connectors(),
                                              progress=lambda i, n, name: bar.progress(i / max(n, 1), text=name))
            bar.empty()
        ok = sum(r.ok for r in results)
        if ok == len(results):
            st.success(f"{ok} élément(s) actualisé(s).")
        else:
            st.warning(f"{ok}/{len(results)} actualisé(s). Erreurs :\n\n" +
                       "\n".join(f"- **{r.instrument}** : {' '.join(r.messages)}" for r in results if not r.ok))
    if active:
        labels = {views.instrument_label(i): i.id for i in active}
        picked = c2.selectbox("Un seul instrument", list(labels), label_visibility="collapsed")
        if c2.button("Actualiser cet instrument", icon=":material/refresh:", width="stretch"):
            with context.session() as s:
                result = market_data.refresh_instrument(s, referential.get_instrument(s, labels[picked]),
                                                        context.connectors())
            if result.ok:
                st.success("Instrument actualisé.")
            else:
                st.warning(" ".join(result.messages))

# --------------------------------------------------------------------------
with tab_backup:
    theme.note(f"Les sauvegardes sont des copies complètes de votre base, chiffrées avec la clé de votre compte, "
               f"avec empreinte SHA-256, rangées dans `{ws.backup_dir}`. Toute restauration est précédée d'une "
               "vérification d'intégrité et d'une "
               "sauvegarde automatique de la base actuelle.")
    comment = st.text_input("Commentaire (facultatif)", key="backup_comment")
    if st.button("Créer une sauvegarde", type="primary", icon=":material/backup:"):
        try:
            entry = backup.create_backup(ws.db_path, ws.backup_dir, comment=comment, key=ws.key)
            st.success(f"Sauvegarde {entry.file} créée et vérifiée.")
        except backup.BackupError as exc:
            st.error(str(exc))

    entries = backup.list_backups(ws.backup_dir)
    if entries:
        st.subheader("Historique des sauvegardes")
        st.dataframe(pd.DataFrame([{
            "Fichier": e.file, "Créée le": theme.day(e.created), "Type": e.kind,
            "Taille": f"{theme.number(e.size / 1024, 0)} Ko", "Commentaire": e.comment or "—",
            "Restaurée le": e.restored_at.replace("T", " ") if e.restored_at else "—",
            "Empreinte": e.sha256[:12] + "…",
        } for e in entries]), hide_index=True, width="stretch")
        by_file = {e.file: e for e in entries}
        picked = by_file[st.selectbox("Sauvegarde", list(by_file))]
        c1, c2 = st.columns(2)
        if c1.button("Vérifier l'intégrité", icon=":material/verified:", width="stretch"):
            ok, message = backup.verify_backup(ws.backup_dir, picked, ws.key)
            if ok:
                st.success(message)
            else:
                st.error(message)
        confirm = c2.checkbox("Je confirme vouloir remplacer la base actuelle")
        if c2.button("Restaurer", icon=":material/restore:", width="stretch", disabled=not confirm):
            try:
                safety = backup.restore_backup(ws.db_path, ws.backup_dir, picked, ws.key)
                st.success(f"Base restaurée depuis {picked.file}. Ancienne base conservée dans "
                           f"{safety.file if safety else '—'}.")
            except backup.BackupError as exc:
                st.error(str(exc))
    else:
        theme.note("Aucune sauvegarde pour l'instant.")

# --------------------------------------------------------------------------
with tab_settings:
    with context.session() as s:
        stored = referential.get_preferences(s)
    with st.form("settings", border=False):
        c1, c2 = st.columns(2)
        price_days = c1.number_input("Cours obsolète au-delà de (jours)", min_value=1, max_value=365,
                                     value=stored.price_stale_days)
        fund_days = c2.number_input("Donnée fondamentale obsolète au-delà de (jours)", min_value=1,
                                    max_value=3650, value=stored.fundamental_stale_days)
        mask = st.checkbox("Masquer les montants par défaut", value=stored.mask_amounts)
        if st.form_submit_button("Enregistrer les paramètres", type="primary"):
            with context.session() as s:
                referential.save_preferences(s, Preferences(mask_amounts=mask, price_stale_days=int(price_days),
                                                            fundamental_stale_days=int(fund_days)))
            st.session_state.pop("mask_amounts", None)
            st.success("Paramètres enregistrés.")

    st.subheader("Sécurité")
    with context.directory() as s:
        account = auth.get_account(s, ws.account_id)
        linked = {i.provider: i.email for i in account.identities}
        username, has_password = account.username, account.password_hash is not None
        phones = [(p.device or "Appareil inconnu", p.last_seen_at) for p in auth.active_sessions(s, account.id)]
    theme.note(f"Compte « {account.name} »" + (f" · identifiant « {username} »" if username else "")
               + ". Vos données sont chiffrées (AES-256, SQLCipher) avec une clé propre à ce compte.")

    st.markdown("**Moyens de connexion**")
    configured = oidc.providers(cfg)
    to_link = []
    for provider, label in auth.PROVIDERS.items():
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        if provider in linked:
            c1.markdown(f"🟢 {label} — associé" + (f" ({linked[provider]})" if linked[provider] else ""))
            if c2.button("Dissocier", key=f"unlink_{provider}", width="stretch"):
                try:
                    with context.directory() as s:
                        auth.unlink_identity(s, auth.get_account(s, ws.account_id), provider)
                    st.rerun()
                except auth.AuthError as exc:
                    st.error(str(exc))
        else:
            c1.markdown(f"⚪ {label} — non associé" + ("" if provider in configured else " (non configuré)"))
            to_link.append(provider)
    if to_link:
        login.sso_buttons("Associer", link_tokens=login.link_tokens(ws.account_id), only=tuple(to_link))

    if has_password:
        with st.form("password", border=False, clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            current = c1.text_input("Mot de passe actuel", type="password", autocomplete="current-password")
            new = c2.text_input("Nouveau mot de passe", type="password", autocomplete="new-password")
            confirmation = c3.text_input("Confirmation", type="password", autocomplete="new-password")
            if st.form_submit_button("Changer le mot de passe"):
                try:
                    with context.directory() as s:
                        auth.change_password(s, auth.get_account(s, ws.account_id), current, new, confirmation)
                    st.success("Mot de passe modifié. Les téléphones connectés devront se reconnecter.")
                except auth.AuthError as exc:
                    st.error(str(exc))
    else:
        with st.form("set_password", border=False, clear_on_submit=True):
            st.caption("Ajoutez un identifiant et un mot de passe (secours si Google ou Apple est indisponible).")
            c1, c2, c3 = st.columns(3)
            new_username = c1.text_input("Identifiant", autocomplete="username")
            new = c2.text_input("Mot de passe", type="password", autocomplete="new-password")
            confirmation = c3.text_input("Confirmation", type="password", autocomplete="new-password")
            if st.form_submit_button("Définir le mot de passe"):
                try:
                    with context.directory() as s:
                        auth.set_password(s, auth.get_account(s, ws.account_id), new_username, new, confirmation)
                    st.rerun()
                except auth.AuthError as exc:
                    st.error(str(exc))

    if phones:
        st.markdown(f"**{len(phones)} téléphone(s) connecté(s)**")
        for device, seen in phones:
            theme.note(f"{device} · dernière activité le {theme.day(seen)} (UTC)")
        if st.button("Déconnecter tous les téléphones", icon=":material/phonelink_erase:"):
            with context.directory() as s:
                auth.revoke_all_sessions(s, ws.account_id)
            st.rerun()
    else:
        theme.note("Aucun téléphone connecté.")

    st.subheader("Connexion Google et Apple")
    origin = (st.context.url or "http://localhost:8501").split("/", 3)
    desktop = "/".join(origin[:3])
    st.dataframe(pd.DataFrame([{
        "Fournisseur": label,
        "État": "🟢 Configuré" if provider in configured else "⚪ Non configuré",
        "Adresse de retour à déclarer (ordinateur)": connexion.redirect_uri(desktop, provider),
        "Adresse de retour (téléphone)": connexion.redirect_uri("https://<adresse du téléphone>", provider),
    } for provider, label in auth.PROVIDERS.items()]), hide_index=True, width="stretch")
    theme.note("Identifiants à renseigner dans `config/secrets.toml` (sections `[google]` et `[apple]`, voir "
               "`config/secrets.example.toml`). Apple exige une adresse HTTPS avec un nom de domaine. Ancora ne "
               "reçoit jamais votre mot de passe Google ou Apple : seulement un identifiant de compte vérifié.")

    st.subheader("Sources de données")
    sources = pd.DataFrame([
        {"Rôle": "Principale", "Source": "Yahoo Finance (yfinance)", "État": "🟢 Active"},
        {"Rôle": "Secondaire", "Source": "Finnhub",
         "État": "🟢 Clé configurée" if cfg.finnhub_api_key else "⚪ Non configurée"},
        {"Rôle": "Réglementaire", "Source": "SEC EDGAR (sociétés américaines)",
         "État": "🟢 Configurée" if cfg.sec_user_agent else "⚪ Non configurée"},
        {"Rôle": "Secours", "Source": "Saisie manuelle", "État": "🟢 Toujours disponible"},
    ])
    st.dataframe(sources, hide_index=True, width="stretch")
    theme.note("Les clés se configurent dans `config/secrets.toml` (jamais versionné) ou par variables "
               "d'environnement ; elles ne sont jamais affichées ni journalisées. Seuls les symboles des "
               "instruments sont transmis aux fournisseurs, jamais vos positions.")

    st.subheader("Stockage local")
    st.markdown(f"- Devise de consolidation : **{CONSOLIDATION_CURRENCY}**\n"
                f"- Base de données de votre compte (chiffrée) : `{ws.db_path}`\n"
                f"- Sauvegardes (chiffrées) : `{ws.backup_dir}`\n"
                f"- Journaux : `{cfg.log_dir}`")

    st.subheader("Version téléphone")
    theme.note("Une interface simplifiée pour consulter votre patrimoine sur iPhone. Lancez-la sur cet ordinateur "
               "avec `python -m app.mobile`, puis rendez-la accessible à votre téléphone de façon privée avec "
               "`tailscale serve --bg 8502`. Dans Safari : Partager › Sur l'écran d'accueil. Détails dans le README.")
