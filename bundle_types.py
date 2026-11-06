"""Bundle types accepted when creating inventory or manual job cards."""

BUNDLE_TYPE_CHOICES = (
    ("lump", "Lump"),
    ("good_cut", "Good Cut"),
    ("fent", "Fent"),
    ("goodCUT 20 picset", "goodCUT 20 picset"),
    ("fent 20 picset", "fent 20 picset"),
    ("un_cut", "Un Cut"),
)

BUNDLE_TYPE_VALUES = frozenset(value for value, _ in BUNDLE_TYPE_CHOICES)
