"""Listes de valeurs du domaine (libellés affichés en français)."""
from enum import Enum


class LabeledEnum(str, Enum):
    """Énumération dont la valeur est le libellé affiché."""

    @property
    def label(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


class InstrumentType(LabeledEnum):
    ACTION = "Action"
    ETF = "ETF"
    FONDS = "Fonds"
    UC = "Unité de compte"
    INDICE = "Indice"


class InstrumentSubtype(LabeledEnum):
    CAPITALISANT = "Capitalisant"
    DISTRIBUANT = "Distribuant"
    OPCVM = "OPCVM"
    SICAV = "SICAV"
    FCP = "FCP"
    ASSURANCE_VIE = "Assurance-vie"
    PER = "PER"


SUBTYPES_BY_TYPE = {
    InstrumentType.ACTION: [],
    InstrumentType.ETF: [InstrumentSubtype.CAPITALISANT, InstrumentSubtype.DISTRIBUANT],
    InstrumentType.FONDS: [InstrumentSubtype.OPCVM, InstrumentSubtype.SICAV, InstrumentSubtype.FCP],
    InstrumentType.UC: [InstrumentSubtype.ASSURANCE_VIE, InstrumentSubtype.PER],
    InstrumentType.INDICE: [],
}


class EnvelopeType(LabeledEnum):
    PEA = "PEA"
    PEA_PME = "PEA-PME"
    ASSURANCE_VIE = "Assurance-vie"
    PER = "PER"
    CTO = "CTO"
    AUTRE = "Autre"


class OperationType(LabeledEnum):
    ACHAT = "Achat"
    VENTE = "Vente"
    DIVIDENDE = "Dividende"
    DISTRIBUTION = "Distribution"
    COUPON = "Coupon"
    APPORT = "Apport"
    RETRAIT = "Retrait"
    FRAIS = "Frais"
    CORRECTION = "Correction"


INCOME_OPERATIONS = (OperationType.DIVIDENDE, OperationType.DISTRIBUTION, OperationType.COUPON)
TRADE_OPERATIONS = (OperationType.ACHAT, OperationType.VENTE, OperationType.CORRECTION)


class DataStatus(LabeledEnum):
    REELLE = "Réelle"
    ESTIMEE = "Estimée"
    CALCULEE = "Calculée"
    MANUELLE = "Manuelle"
    NON_DISPONIBLE = "Non disponible"
    NON_APPLICABLE = "Non applicable"
    OBSOLETE = "Obsolète"
    ERREUR = "Erreur"


# Statuts porteurs d'une valeur exploitable.
VALUED_STATUSES = (DataStatus.REELLE, DataStatus.ESTIMEE, DataStatus.CALCULEE, DataStatus.MANUELLE)


class DataField(LabeledEnum):
    PRICE = "Cours / VL"
    DIVIDEND_N = "Dividende N"
    DIVIDEND_N1 = "Dividende N+1"
    DIVIDEND_LAST = "Dividende versé N-1"
    DIVIDEND_ANALYSTS = "Analystes (dividende)"
    EX_DATE = "Date de détachement"
    PAYMENT_DATE = "Date de paiement"
    EPS = "BNA"
    TARGET_MEAN = "Objectif moyen"
    TARGET_LOW = "Objectif bas"
    TARGET_HIGH = "Objectif haut"
    ANALYSTS = "Nombre d'analystes"
    TER = "TER"
    AUM = "Encours"
    MANAGER = "Société de gestion"


class Applicability(LabeledEnum):
    OUI = "Oui"
    VARIABLE = "Variable"
    RARE = "Rare"
    NON = "Non"
    NON_APPLICABLE = "Non applicable"
