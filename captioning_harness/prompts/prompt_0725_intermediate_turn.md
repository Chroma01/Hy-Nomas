# Multi-Turn Video Annotation — Following Segment Annotation

The newly attached video contains ONLY segment {segment_index} of the
{segment_count} total segments. It covers the exact interval from {segment_start_time} to {segment_end_time}, and it is the immediate continuation of the segment(s) previously shown in this conversation.

Analyze the current segment. Do not generate the final bilingual whole-video caption yet. Output a compact English caption JSON for this segment only, while updating the global `perspective_view`, `Style`, and `subject_list` based on all segments observed so far.

## Mandatory Revision Behavior

- Do not treat the annotation of segment 1 as finalized. If the current video segment provides clear, concrete evidence that establishes or corrects information about subject identity, display name, static attributes, subject count, or ID assignment, update `subject_list` accordingly and record the corresponding mapping and reason in `subject_id_revisions`.
- Treat `perspective_view` as a single video-level hypothesis. Re-evaluate it cumulatively using all segments observed so far and the perspective decision procedure in the system prompt. Update it only when the accumulated evidence changes the best whole-video classification. Do not change it merely because the camera temporarily stops, the focus subject briefly leaves the frame, or the current segment differs from the video's dominant pattern.
- Continue accumulating evidence about camera translation, whether the dominant focus is the filmer, a filmed subject, or no clear subject, and—when applicable—whether the camera and filmed subject have approximately coupled horizontal displacement.
- `subject_list` is the complete CURRENT global subject list, not just the subjects first introduced in this segment. Preserve subject IDs whenever continuity is supported by evidence; revise them only when stronger evidence makes it necessary.
- Even if the current segment provides evidence for correcting or revising identity, continuity, or ID, `subject_attribute` must always reconstruct that subject's static appearance, posture, orientation, held items, and scene relation at its EARLIEST clear, identifiable frames. Later appearance, posture, and spatial changes belong only in the relevant segment's `action_description` (under `contained_actions`).
- Retain evidence relevant to permanence across temporary occlusion or absence, but never infer, assume, or fabricate a subject's current action or state.
- Only describe the visual details introduced in this segment. DO NOT repeat or restate content from prior segments.

## Annotation Rules

- `visual_description_long` must be `null`.
- `description_change` must begin exactly with the required prefix: `"Compared to the previous segment, "`.
- The first complete sentence must strictly be a subject-free **scene sentence** describing only the background or scene. Since all main subject actions belong strictly to `contained_actions`, no Subject tokens or action descriptions may ever appear in `description_change`.
  - *Valid example:* `Compared to the previous segment, the background remains unchanged.`
  - *Invalid example:* `Compared to the previous segment, <|Subject1|> walks down the street.` (Do not place any Subject tokens or action descriptions inside `description_change`.)
- If only main subject behavior changes while the scene does not materially change, use this exact first sentence: `"Compared to the previous segment, the visible scene, background, and other-object layout remain materially unchanged."`
- Exhaustively describe the visible differences of this segment compared to the previous segment. Write environmental changes (such as scene, background, props, other objects, lighting, and framing) in `description_change`, and place all main subject updates (such as appearance, visibility, state changes, actions, and visible action consequences) in `action_description` under `contained_actions`.
- Every main subject-related description must use the exact Subject token `<|Subject#|>` and be fully enclosed in one `<Action#>...</Action#>` wrapper. Never use natural-language subject names, aliases, or pronouns as shortcuts, recaps, comparisons, or connectors. Every visible camera motion must be written as a complete subject-free `<Camera#>...</Camera#>` sentence.
- Concrete correctly paired Camera Sentence example: `<Camera1>The camera pans slowly to the right, widening the view to reveal the doorway</Camera1>.`

## Required Output for This Turn

Output ONLY one raw JSON object, with no Markdown or extra prose:

```json
{
  "segment_index": {segment_index},
  "perspective_view": "first-person | second-person | third-person follow | third-person observer",
  "Style": "real-world footage | animation/anime | CG | video game | software/web/app/computer screen recording | slideshow",
  "perspective_assessment": {
    "confidence": "low | medium | high",
    "evidence": "Best cumulative evidence, including what this segment changed",
    "could_be_overwritten": true
  },
  "subject_list": [
    {
      "subject_id": "<|Subject1|>",
      "display_name": "Current best concise English identity",
      "subject_attribute": "Static English description anchored to this subject's earliest clear visible state, or null",
      "confidence": "low | medium | high",
      "evidence_in_this_segment": "Recognition evidence, new evidence, temporary absence, or correction",
      "could_be_overwritten": true
    }
  ],
  "subject_id_revisions": [
    {
      "prior_subject_id": "<|SubjectN|> or null",
      "current_subject_id": "<|SubjectM|> or null",
      "revision": "added | confirmed | renamed | merged | split | removed | remapped",
      "reason": "Concrete visual reason"
    }
  ],
  "segment_draft": {
    "start_time": "{segment_start_time}",
    "end_time": "{segment_end_time}",
    "visual_description_long": null,
    "description_change": "Compared to the previous segment, ... (the first sentence is subject-free; describe subject changes in Action Sentences with the format of <Action#>...<|Subject#|>...</Action#>)",
    "contained_actions": [
      {
        "start_time": "MM:SS.mmm",
        "end_time": "MM:SS.mmm",
        "action_description": "Action Sentences with format <Action#>...<|Subject#|>...</Action#>. Action Sentence should refer to at least one subject."
      }
    ]
  },
  "open_questions_for_later_segments": [
    "Remaining uncertainty, or an empty list if none"
  ]
}
```
