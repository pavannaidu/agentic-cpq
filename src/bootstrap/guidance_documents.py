"""Reviewed seller-guidance documents attached to the CPQ Genie Agent."""

from __future__ import annotations


SOURCE_MARKDOWN_NAMES = (
    "financing-and-approval-guide.md",
    "imaging-upgrade-guide.md",
    "operatory-expansion-playbook.md",
    "software-onboarding-and-adoption.md",
    "zero-friction-quoting.md",
)

GUIDANCE_DOCUMENT_NAMES = tuple(
    name.removesuffix(".md") + ".docx" for name in SOURCE_MARKDOWN_NAMES
)
