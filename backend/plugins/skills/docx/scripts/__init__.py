"""
DOCX processing scripts.

This package provides scripts for creating, editing, and manipulating Word documents.
"""

from . import accept_changes, comment, create_docx, edit_docx
from .office import pack, soffice, unpack, validate
from .office.helpers import merge_runs, simplify_redlines
from .office.validators import (
    BaseSchemaValidator,
    DOCXSchemaValidator,
    PPTXSchemaValidator,
    RedliningValidator,
)

__all__ = [
    # Main scripts
    "accept_changes",
    "comment",
    "create_docx",
    "edit_docx",
    "pack",
    "soffice",
    "unpack",
    "validate",
    # Helper modules
    "merge_runs",
    "simplify_redlines",
    # Validators
    "BaseSchemaValidator",
    "DOCXSchemaValidator",
    "PPTXSchemaValidator",
    "RedliningValidator",
]
