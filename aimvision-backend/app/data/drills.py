"""Canonical drill catalog — the single source of truth for the global
drill library.

Seeded into the `drills` table idempotently at app startup
(`app.services.drills.ensure_drills_seeded`). The LLM coaching note's
`recommended_drills` reference these ids; the verifier rejects any id
not in this catalog, so the model cannot invent drills.

`target_categories` entries are `DiagnosticCategory` values
(docs/diagnostic-taxonomy.md). The set below covers all 15 atoms so
every diagnosis maps to at least one drill.
"""

from __future__ import annotations

from typing import TypedDict


class DrillSeed(TypedDict):
    id: str
    name: str
    description: str
    discipline: str
    target_categories: list[str]


DRILL_CATALOG: list[DrillSeed] = [
    {
        "id": "drill_bead_stare",
        "name": "Bead stare",
        "description": (
            "Mount on a fixed point and hold cheek to stock through the break; stare at "
            "the bead, not the target, to stop the head coming up."
        ),
        "discipline": "all",
        "target_categories": ["head_lift", "head_off_stock"],
    },
    {
        "id": "drill_cheek_weld_holds",
        "name": "Cheek-weld holds",
        "description": (
            "Slow-mount reps holding a firm cheek weld for three seconds before dismount; "
            "builds consistent head position."
        ),
        "discipline": "all",
        "target_categories": ["head_off_stock", "head_lift"],
    },
    {
        "id": "drill_dominant_eye_check",
        "name": "Dominant-eye check",
        "description": (
            "Triangle test before each string; confirm sighting eye and adjust bead "
            "alignment or occlude when cross-dominant."
        ),
        "discipline": "all",
        "target_categories": ["eye_dominance_failure"],
    },
    {
        "id": "drill_low_gun_mount_reps",
        "name": "Low-gun mount reps",
        "description": (
            "Repeat the low-mount-to-cheek motion to a smooth, repeatable break point "
            "without rushing the mount."
        ),
        "discipline": "all",
        "target_categories": ["low_mount_break"],
    },
    {
        "id": "drill_stance_alignment",
        "name": "Stance alignment",
        "description": (
            "Set feet to the break point and rehearse weight-forward balance so the swing "
            "stays on plane."
        ),
        "discipline": "all",
        "target_categories": ["foot_position", "body_alignment_off"],
    },
    {
        "id": "drill_swing_through",
        "name": "Swing-through",
        "description": (
            "Come from behind the target, swing through, and fire without stopping the "
            "gun; cures the stopped/checked swing."
        ),
        "discipline": "all",
        "target_categories": ["stopped_gun", "off_line"],
    },
    {
        "id": "drill_maintained_lead",
        "name": "Maintained lead",
        "description": (
            "Hold a constant gap ahead of the target through the break to calibrate lead "
            "and stop over/under-leading."
        ),
        "discipline": "all",
        "target_categories": ["under_lead", "over_lead"],
    },
    {
        "id": "drill_follow_through_holds",
        "name": "Follow-through holds",
        "description": (
            "Keep the gun moving and mounted for a beat after the shot; stops the early "
            "dismount and dropped gun."
        ),
        "discipline": "all",
        "target_categories": ["short_follow_through", "dropped_gun_post_shot"],
    },
    {
        "id": "drill_pattern_plate_check",
        "name": "Pattern-plate check",
        "description": (
            "Shoot a static plate to verify the gun prints where you look; isolates "
            "off-line point of impact."
        ),
        "discipline": "all",
        "target_categories": ["off_line"],
    },
    {
        "id": "drill_mount_consistency",
        "name": "Mount consistency",
        "description": (
            "Mirror-mount reps for an identical gun mount every time; reduces mount-break "
            "and alignment variance."
        ),
        "discipline": "all",
        "target_categories": ["low_mount_break", "body_alignment_off"],
    },
    {
        "id": "drill_pair_timing",
        "name": "Pair timing",
        "description": (
            "Doubles-timing drill to set a rhythm across the pair when multiple faults "
            "compound under time pressure."
        ),
        "discipline": "skeet",
        "target_categories": ["multi_factor", "in_session_pattern_flag"],
    },
    {
        "id": "drill_video_review",
        "name": "Video review",
        "description": (
            "Slow-motion review of the mount-swing-break sequence to surface the cause "
            "when the diagnosis is unclear."
        ),
        "discipline": "all",
        "target_categories": ["cause_unclear", "multi_factor"],
    },
]
