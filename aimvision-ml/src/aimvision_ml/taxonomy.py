"""Diagnostic taxonomy enums + tone variants.

Mirrors `docs/diagnostic-taxonomy.md`. The canonical tokens here are the
working_canonical values from the v0.9 draft; final tokens get pinned at
the Sprint 9 card-sort lock with 20 coaches + 20 athletes across
US/UK/IT/EG. Until lock, the model trains on these working tokens; on lock,
this module bumps `TAXONOMY_VERSION` and the registry migration script
rewrites historical labels.
"""

from __future__ import annotations

from enum import StrEnum

# Bumps on every taxonomy lock or rename.
TAXONOMY_VERSION: str = "0.9-draft"


class Branch(StrEnum):
    """The four branch experts plus Meta layer.

    Cite docs/diagnostic-taxonomy.md §Branch structure and
    docs/ml-architecture.md §8.
    """

    HEAD_EYE = "head_eye"
    MOUNT_STANCE = "mount_stance"
    SWING_LEAD = "swing_lead"
    FOLLOW_THROUGH = "follow_through"
    META = "meta"


class DiagnosticCategory(StrEnum):
    """Working-canonical atom names. Source of truth: diagnostic-taxonomy.md."""

    # Head/Eye
    HEAD_LIFT = "head_lift"
    HEAD_OFF_STOCK = "head_off_stock"
    EYE_DOMINANCE_FAILURE = "eye_dominance_failure"
    # Mount/Stance
    LOW_MOUNT_BREAK = "low_mount_break"
    FOOT_POSITION = "foot_position"
    BODY_ALIGNMENT_OFF = "body_alignment_off"
    # Swing/Lead
    STOPPED_GUN = "stopped_gun"  # canonical TBD per Sprint 9 card-sort
    UNDER_LEAD = "under_lead"
    OVER_LEAD = "over_lead"
    OFF_LINE = "off_line"
    # Follow-through
    SHORT_FOLLOW_THROUGH = "short_follow_through"
    DROPPED_GUN_POST_SHOT = "dropped_gun_post_shot"
    # Meta
    CAUSE_UNCLEAR = "cause_unclear"
    MULTI_FACTOR = "multi_factor"
    IN_SESSION_PATTERN_FLAG = "in_session_pattern_flag"


# Branch membership. Used by the multi-task head and stratified eval.
BRANCH_OF: dict[DiagnosticCategory, Branch] = {
    DiagnosticCategory.HEAD_LIFT: Branch.HEAD_EYE,
    DiagnosticCategory.HEAD_OFF_STOCK: Branch.HEAD_EYE,
    DiagnosticCategory.EYE_DOMINANCE_FAILURE: Branch.HEAD_EYE,
    DiagnosticCategory.LOW_MOUNT_BREAK: Branch.MOUNT_STANCE,
    DiagnosticCategory.FOOT_POSITION: Branch.MOUNT_STANCE,
    DiagnosticCategory.BODY_ALIGNMENT_OFF: Branch.MOUNT_STANCE,
    DiagnosticCategory.STOPPED_GUN: Branch.SWING_LEAD,
    DiagnosticCategory.UNDER_LEAD: Branch.SWING_LEAD,
    DiagnosticCategory.OVER_LEAD: Branch.SWING_LEAD,
    DiagnosticCategory.OFF_LINE: Branch.SWING_LEAD,
    DiagnosticCategory.SHORT_FOLLOW_THROUGH: Branch.FOLLOW_THROUGH,
    DiagnosticCategory.DROPPED_GUN_POST_SHOT: Branch.FOLLOW_THROUGH,
    DiagnosticCategory.CAUSE_UNCLEAR: Branch.META,
    DiagnosticCategory.MULTI_FACTOR: Branch.META,
    DiagnosticCategory.IN_SESSION_PATTERN_FLAG: Branch.META,
}


# Per-class default abstention thresholds. Sourced from diagnostic-taxonomy.md
# atom-level confidence_threshold fields. These are defaults; the registry
# tunes them on stratified validation per ml-architecture.md §8.
DEFAULT_ABSTENTION_THRESHOLDS: dict[DiagnosticCategory, float] = {
    DiagnosticCategory.HEAD_LIFT: 0.55,
    DiagnosticCategory.HEAD_OFF_STOCK: 0.60,
    DiagnosticCategory.EYE_DOMINANCE_FAILURE: 0.70,
    DiagnosticCategory.LOW_MOUNT_BREAK: 0.60,
    DiagnosticCategory.FOOT_POSITION: 0.65,
    DiagnosticCategory.BODY_ALIGNMENT_OFF: 0.60,
    DiagnosticCategory.STOPPED_GUN: 0.55,
    DiagnosticCategory.UNDER_LEAD: 0.60,
    DiagnosticCategory.OVER_LEAD: 0.60,
    DiagnosticCategory.OFF_LINE: 0.60,
    DiagnosticCategory.SHORT_FOLLOW_THROUGH: 0.60,
    DiagnosticCategory.DROPPED_GUN_POST_SHOT: 0.65,
}


# Coach-mode tones. These are the working canonical strings from the
# taxonomy doc; final wording is locked post-card-sort. Each line is the
# coach-tone phrasing modulo per-shot id substitution.
_COACH_TONES: dict[DiagnosticCategory, str] = {
    DiagnosticCategory.HEAD_LIFT: "Head came off at break. Cheek-weld first.",
    DiagnosticCategory.HEAD_OFF_STOCK: "Cheek-weld breaking before mount completes.",
    DiagnosticCategory.EYE_DOMINANCE_FAILURE: "Cross-dominance creeping back.",
    DiagnosticCategory.LOW_MOUNT_BREAK: "Mount finishing at the shot — gun's still moving up.",
    DiagnosticCategory.FOOT_POSITION: "Stance is closing too early on the high stations.",
    DiagnosticCategory.BODY_ALIGNMENT_OFF: "Address bearing short of break point.",
    DiagnosticCategory.STOPPED_GUN: "Gun's stopping at break — through the bird, not at it.",
    DiagnosticCategory.UNDER_LEAD: "Behind on crossers. Build more lead.",
    DiagnosticCategory.OVER_LEAD: "Pushing past the clay. Slow the swing.",
    DiagnosticCategory.OFF_LINE: "Off the line of the bird.",
    DiagnosticCategory.SHORT_FOLLOW_THROUGH: "Swing's dying right at the shot.",
    DiagnosticCategory.DROPPED_GUN_POST_SHOT: "Gun's coming out of the pocket at the shot.",
    DiagnosticCategory.CAUSE_UNCLEAR: "Couldn't tell on this one — review video together.",
    DiagnosticCategory.MULTI_FACTOR: "Compound fault: address, then mount, then swing. Address fixes the chain.",
    DiagnosticCategory.IN_SESSION_PATTERN_FLAG: "Pattern detected — three in a row.",
}


# Athlete-mode tones. Directive, plain language. Lock with native-speaker
# coach review per locale post-card-sort; do not machine-translate.
_ATHLETE_TONES: dict[DiagnosticCategory, str] = {
    DiagnosticCategory.HEAD_LIFT: "You peeked. Stay on the gun until the clay breaks.",
    DiagnosticCategory.HEAD_OFF_STOCK: "Press your cheek to the stock before you swing.",
    DiagnosticCategory.EYE_DOMINANCE_FAILURE: "Check your dominant-eye discipline.",
    DiagnosticCategory.LOW_MOUNT_BREAK: "Get the gun up earlier. Mount before you call.",
    DiagnosticCategory.FOOT_POSITION: "Open your front foot a touch on the high stations.",
    DiagnosticCategory.BODY_ALIGNMENT_OFF: "Set up so you finish where the bird breaks, not where you call.",
    DiagnosticCategory.STOPPED_GUN: "Keep swinging through the clay. Don't aim — swing.",
    DiagnosticCategory.UNDER_LEAD: "More lead on the crossers.",
    DiagnosticCategory.OVER_LEAD: "Less lead on the outgoers.",
    DiagnosticCategory.OFF_LINE: "Get on the line of the bird, not under it.",
    DiagnosticCategory.SHORT_FOLLOW_THROUGH: "Keep swinging after the shot.",
    DiagnosticCategory.DROPPED_GUN_POST_SHOT: "Stay in the gun a beat longer.",
    DiagnosticCategory.CAUSE_UNCLEAR: "We're not sure on a few shots; check the replay.",
    DiagnosticCategory.MULTI_FACTOR: "Fix your set-up first; the rest will follow.",
    DiagnosticCategory.IN_SESSION_PATTERN_FLAG: "Pattern: same fault three shots in a row.",
}


def to_coach_tone(cat: DiagnosticCategory) -> str:
    """Coach-mode phrasing — technical, evidence-cited."""
    return _COACH_TONES[cat]


def to_athlete_tone(cat: DiagnosticCategory) -> str:
    """Athlete-mode phrasing — directive, plain language."""
    return _ATHLETE_TONES[cat]


def all_categories() -> list[DiagnosticCategory]:
    """Stable ordering for label-vector construction."""
    return list(DiagnosticCategory)


def categories_for(branch: Branch) -> list[DiagnosticCategory]:
    """All atoms in a given branch, in declaration order."""
    return [c for c, b in BRANCH_OF.items() if b == branch]
