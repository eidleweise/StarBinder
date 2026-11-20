"""StarBinder desktop application."""

from .profile import (
    Action,
    ActionMap,
    CustomisationUIHeader,
    Profile,
    ProfileParseError,
    ProfileStore,
    ProfileWarning,
    Rebind,
    parse_profile,
    parse_profile_file,
    parse_profile_text,
)
from .catalog import ActionCatalog, ResolvedText, neutral_name
from .input import InputPart, ParsedInput, normalize_input, parse_input
from .presentation import BindingEntry, ProfileBrowser

__version__ = "0.1.0"

__all__ = [
    "Action",
    "ActionMap",
    "CustomisationUIHeader",
    "Profile",
    "ProfileParseError",
    "ProfileStore",
    "ProfileWarning",
    "Rebind",
    "parse_profile",
    "parse_profile_file",
    "parse_profile_text",
    "ActionCatalog",
    "ResolvedText",
    "neutral_name",
    "InputPart",
    "ParsedInput",
    "normalize_input",
    "parse_input",
    "BindingEntry",
    "ProfileBrowser",
]
