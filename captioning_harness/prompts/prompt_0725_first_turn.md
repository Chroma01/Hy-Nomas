# Multi-Turn Video Annotation Task - First Segment Annotation

This conversation will provide one complete video as a sequence of consecutive pre-clipped video segments. The attached video in this turn contains ONLY segment 1 of the full video.
More video segments from this video will follow in subsequent turns. Do not refer to or assume seeing any future segments, and do not generate the final bilingual caption yet.

After all segments have been shown, a final text-only turn will request the final caption, which must include: video-level `perspective_view`, `Style` and `subject_list`, and segment-level caption for each segment containing `visual_description_long`, `description_change` and `contained_actions`. Within both `visual_description_long` and `description_change`,
there are only Scene Sentence and Camera Sentence. All camera motions must be wrapped in `<Camera#>...</Camera#>` tags. There is NO subject reference in `visual_description_long` and `description_change`. `contained_actions` only has Action Sentence, and all actions must be wrapped in `<Action#>...</Action#>` tags.

This turn has four tasks:

1. Generate `visual_description_long` for the first segment, including Scene Sentence (the environment/background description) and Camera Sentence (camera motion, wrapped in `<Camera#>...</Camera#>` tags);
2. Generate `contained_actions` for the first segment, describing all the actions in chronological order. `action_description` describe each main subject action (wrapped in `<Action#>...</Action#>` tags) and their time stamps marked with `start_time` and `end_time`;
3. Preserve all concrete visual evidence from segment 1 that is needed for final summarization and output;
4. Create the first draft for `perspective_view`, `Style`, and `subject_list`. Subsequent turns may confirm, revise, merge, split, replace, or overwrite these entries.

## Video Metadata Information

- Whole-video duration: {duration:.2f} seconds
- Whole-video sampled-frame estimate: {num_frames} frames at {fps} FPS
- Current segment: {segment_index} of {segment_count}
- Current exact range: {segment_start_time} – {segment_end_time}
- Pre-clipped video segments: {precomputed_event_segments}

## Annotation Rules

- For `perspective_assessment.evidence`, explicitly state: (1) whether meaningful camera translation is visible; (2) whether the dominant visual focus is the filmer, a filmed subject, or no clear focus subject; (3) if the filmer is shown, whether the face or limbs/body parts dominate; and (4) if a filmed subject and camera both translate, whether their horizontal displacement is approximately coupled. Use only evidence visible in the segments shown so far.
- The first segment may be insufficient for a reliable whole-video perspective decision. In that case, choose the currently best-supported label, lower the confidence, and record the unresolved evidence in `open_questions_for_later_segments`.
- Analyze and describe the visual content of the first segment. Do not include any information about unseen future segments.
- The first segment's `description_change` must be `null`.
- Use the provided segment timestamps precisely.
- `visual_description_long` should be approximately 80-200 English words and strictly ordered by time, comprehensively covering the visible composition, environment, objects, framing, camera motion. It should describe each visible process exactly once, and DO NOT include any unsupported details. Use only legal sentence formats: subject-free Scene Sentences; subject-free Camera Sentences wrapped in `<Camera#>...</Camera#>` for visible camera motion.
- `contained_actions` MUST be a list of action entries. Each entry MUST include the action's start timestamp, end timestamp, and `action_description`. `contained_actions` MUST comprehensively describe, in chronological order, all actions performed by the main subjects within the current segment, as well as any subsequent effects or state changes caused by those actions that occur within the current segment. Each `action_description` MUST be wrapped in its corresponding Action token, e.g., `<Action#>...</Action#>`. Each `action_description` MUST refer to subjects using the exact Subject token (e.g., <|Subject#|>). The main subjects' actions and state changes MUST be described exclusively in action sentences, while their static attributes MUST be kept strictly in `subject_attribute`.
- Concrete correctly paired Camera Sentence example: `<Camera1>The camera pans slowly to the right, widening the view to reveal the doorway</Camera1>.`

## Required Output for This Turn

Output ONLY one raw JSON object, with no Markdown or extra prose:

```json
{
  "segment_index": 1,
  "perspective_view": "first-person | second-person | third-person follow | third-person observer",
  "Style": "real-world footage | animation/anime | CG | video game | software/web/app/computer screen recording | slideshow",
  "perspective_assessment": {
    "confidence": "low | medium | high",
    "evidence": "Visible evidence about camera translation, dominant focus, visible filmer face or limbs when applicable, and camera–filmed-subject horizontal coupling when applicable",
    "could_be_overwritten": true
  },
  "subject_list": [
    {
      "subject_id": "<|Subject1|>",
      "display_name": "Current best concise English identity",
      "subject_attribute": "Static English description anchored to the earliest clear visible state, or null",
      "confidence": "low | medium | high",
      "evidence_in_this_segment": "Why this entity is tracked and how it is recognized",
      "could_be_overwritten": true
    }
  ],
  "subject_id_revisions": [],
  "segment_draft": {
    "start_time": "{segment_start_time}",
    "end_time": "{segment_end_time}",
    "visual_description_long": "comprehensive English description of the initial visible world. All the sentences are subject-free Scene Sentences or subject-free Camera Sentences",
    "description_change": null,
    "contained_actions": [
	{
		"start_time": "MM:SS.mmm",
		"end_time": "MM:SS.mmm",
		"action_description": "Action Sentences with format <Action#>...<|Subject#|>...</Action#>. Action Sentence should refer to at least one subject."
	}
]
  },
  "open_questions_for_later_segments": [
    "Specific uncertainty that later visual evidence should resolve and be cautious on"
  ]
}
```
