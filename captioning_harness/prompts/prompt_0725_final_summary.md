# Video Metadata Information

- Video duration: {duration:.2f} seconds
- Sampled frames: {num_frames} frames at {fps} FPS

# Precomputed Video Segments (DO NOT MODIFY)

Use these exact consecutive segments. Do not split, merge, reorder, shorten, extend, or adjust them.

{precomputed_event_segments}

# Tasks

The entire video was supplied earlier in the conversation as a sequence of segments. There is NO new video attached in this final turn. Review all previously shown video segments and the intermediate JSON objects generated in previous rounds. In this final summary turn, your task is to:

1. Compile and refine the first segment's caption and all subsequent segment captions into a single, cohesive English production caption (conforming strictly to the JSON schema);
2. Translate the entire English production caption into a faithful, structurally aligned Chinese version (yielding the `chinese_json` block);
3. Verify the formatting, segment count, and overall schema of the final JSON output;
4. Output exactly one raw JSON object with the keys `english_json` and `chinese_json`, strictly following the production schema. Do not include any Markdown code blocks, explanations, or additional text.

## Task 1: Summarize and Conclude the Final English Caption

Now, produce the single final production caption by performing the following tasks:
1. **Perspective & Style**: Recompute and finalize `perspective_view` from the complete video using the perspective decision procedure in the system prompt. Base the decision on the video's dominant visual content and complete camera–subject relationship; do not simply copy the most recent intermediate draft. Finalize `Style` from the complete video as well.
2. **Word Count**: `visual_description_long` MUST contain approximately 80-200 English words.
3. **Main Subjects**: Finalize all main subjects for the entire video. Correct inconsistent subject definitions across previous segments, merge duplicate subjects, split subjects that were mistakenly grouped, remove incidental subjects, and add any later-confirmed subjects.
4. **Consistency Check**: Coordinate continuity across segment boundaries. Use the complete video to correct omissions, hallucinations, perspective errors, subject misidentification, actions or states that improperly spill across segments, and timestamp errors introduced in previous turns.
5. **ID Renumbering**: If there are any Camera ID sequencing errors, renumber the IDs sequentially starting from 1 (with no gaps or duplicates) for each segment, based on your global understanding of the timeline.
6. **Segment Alignment**: Ensure exactly one segment entry per supplied segment. Copy every segment boundary timestamp provided in the precomputed segments into the final caption exactly as given. Never merge, split, reorder, or omit any segment.
7. **Action Alignment**: If the `contained_actions` field of a segment is non-empty, all actions within `contained_actions` MUST be ordered strictly by their temporal occurrence. Actions MUST NOT have any temporal overlap. The end time of each action MUST be less than or equal to the start time of the next action, ensuring a single chronological sequence within the segment. The Action ID must restart from 1 and increase sequentially in each segment.
8. **Clean Output**: Only this final turn must output the complete bilingual production caption. Do not include intermediate or evidence keys from previous turns, such as `segment_index`, `perspective_assessment`, `subject_id_revisions`, `segment_draft`, `confidence`, `evidence`, `could_be_overwritten`, and `open_questions_for_later_segments`.

## Task 2: Chinese Translation

Translate the English JSON into Chinese ONLY after validating the completed English caption.

- **Structural Preservation**: Preserve the schema, keys, arrays, segment/sentence order, nulls, booleans, timestamps, Subject tokens, action wrappers, camera wrappers, and action/camera IDs.
- **Fields to Translate**: Translate `display_name`, `subject_attribute`, `visual_description_long`,`description_change`, and `contained_actions`.
- **Style Enum Mapping**: Map `Style` to the exact Chinese enum defined above.
- **Non-translatable Fields**: Do not translate `perspective_view`, `subject_id`, `camera_id` (if applicable), timestamps, JSON keys, or `null`.
- **Wrapper Integrity**: Translate the words inside the action and camera wrappers, while preserving the exact wrappers around the corresponding complete Chinese action and camera sentences.
- **No Modification**: Do not independently redetect, merge, split, reorder, or renumber actions or camera motions.
- **Strict Chinese Invariant**: The Chinese translation MUST obey the same absolute token-and-wrapper invariant. It MUST not introduce natural-language main subject names, labels, roles, categories, pronouns, aliases, appositives, repeated identity descriptions, or new facts.

## Task 3: Format and Schema Check

Do not finalize the JSON until every check passes:

- **Segment Count and Timestamp Check**: Segment count and segment timestamps MUST exactly match the provided precomputed segments. The number of output segments MUST exactly equal the number of precomputed segments. Each segment caption MUST map to exactly one video segment.
- **Style Key and Value Check**: `Style` appears once per language JSON with the exact English/Chinese mapping.
- **Camera Motion Check**: Any camera-motion or viewpoint-change description MUST be enclosed within matching `<Camera#>` and `</Camera#>` wrappers. Every Camera wrapper MUST NOT contain any Subject tokens `<|Subject#|>` or main-subject references. Within each segment, camera IDs MUST start from `<Camera1>` and increment sequentially without gaps. Camera ID numbering MUST restart from `<Camera1>` in every new segment. Camera wrappers are ONLY permitted in `visual_description_long` and `description_change`. Camera wrappers MUST NOT appear in any other fields.
- **Subject Semantics and Coreference Check**: Build a semantic coreference checklist from every subject's `display_name`, identity, role, category, species, appearance, clothing, and likely pronouns. Scan both description fields sentence by sentence in both languages. No checklist item, synonym, alias, appositive, pronoun, possessive, or implicit expression may be used to refer to a main subject; replace every such reference with the exact Subject token.
- **Action Wrapper Check**: Inspect every complete action wrapper. Every main subject reference inside the action wrapper MUST be an exact Subject token, with no adjacent or repeated natural-language identity such as "the hand", "the rider", "the first subject", "he", "she", "it", "they", "identified as", or "a person wearing ...". Every `action_description` MUST begin with `<Action#>`, have a matching closing tag, and end semantically at `</Action#>`.
- **Description Check**: `visual_description_long` and `description_change` MUST NOT contain any Subject tokens or Action tokens. Only Camera tokens can be included.
- **Numerical ID Order Check**: The Action wrapper IDs MUST form a strictly sequential numerical order starting from `<Action1>` through `<ActionK>`. The Camera wrapper IDs MUST also form a strictly sequential numerical order from `<Camera1>` through `<CameraK>`.
- **Camera–Action Orthogonality Check**: Camera motion and subject actions MUST be described in separate sentences. A sentence containing a `<Camera#>...</Camera#>` wrapper MUST not contain any `<Action#>...</Action#>` wrapper, and a sentence containing an action wrapper MUST not contain any camera wrapper. Camera wrappers and action wrappers MUST never be nested within one another.
- **Timestamp Check**: The segment timestamps MUST NOT overlap: the end time of the i-th segment MUST be equal to or earlier than the start time of the (i+1)-th segment. The action timestamps MUST also NOT overlap: the end time of `<ActionK>` MUST be strictly equal to or earlier than the start time of `<ActionK+1>`. Any action timestamp MUST NOT be earlier than the segment start time or later than the segment end time.
- **Language Matching Check**: English and Chinese caption structures, subjects, segments, actions, timestamps, and semantics MUST match exactly.

If any test fails, repair the segment, re-slice the timeline, renumber the actions, and rewrite the caption to ensure all checks CAN pass.

## Task 4: Final Constraints and Output Requirements

- **Single Raw JSON Output**: Output exactly one raw JSON object containing only the `english_json` and `chinese_json` keys, strictly following the production schema. Do not include any Markdown code blocks, explanations, drafts, or additional text.
- **Schema Adherence**: Use exactly the JSON schema defined below.
- **Strict Subject Token Constraint**: Every main subject reference MUST use only its exact Subject token (e.g., `<|Subject1|>`), and every Subject token MUST be fully enclosed within a paired Action wrapper.
- **No Natural-Language Subject References**: Natural-language names, display names, roles, categories, pronouns, synonyms, aliases, appositives, repeated identity descriptions, and implicit references to main subjects are strictly forbidden in both description fields (`visual_description_long` and `description_change`), even when placed directly beside a correct Subject token.
- **No Redundancy**: Every action, state, or state change MUST be described in detail but exactly once.
- **Bilingual Structural Alignment**: English and Chinese versions MUST preserve identical structures, segment counts, action sequences, and non-translatable protected values.

# Final Output Schema

Output ONLY one raw JSON object:
```json
{
  "english_json": {
    "perspective_view": "first-person | second-person | third-person follow | third-person observer",
    "Style": "real-world footage | animation/anime | CG | video game | software/web/app/computer screen recording | slideshow",
    "subject_list": [
      {
        "subject_id": "<|Subject1|>",
        "display_name": "English string",
        "subject_attribute": "English static visual description, or null"
      }
    ],
    "segments": [
      {
        "start_time": "MM:SS.mmm",
        "end_time": "MM:SS.mmm",
        "visual_description_long": "First segment: detailed scene sentences; later segments: null",
        "description_change": "First segment: null; later segments: detailed delta beginning with Compared to the previous segment, ",
        "contained_actions": [
            {
              "start_time": "MM:SS.mmm",
              "end_time": "MM:SS.mmm",
              "action_description": "English description of the subject's action, start with <Action#> and end with </Action#>"
            }
          ]
      }
    ]
  },
  "chinese_json": {
    "perspective_view": "MUST remain exactly the same as english_json",
    "Style": "真实视频 | 动画/动漫 | CG | 游戏 | 软件/网页/App/电脑录屏 | 幻灯片",
    "subject_list": [
      {
        "subject_id": "<|Subject1|>",
        "display_name": "Chinese translation",
        "subject_attribute": "Chinese translation, or null"
      }
    ],
    "segments": [
      {
        "start_time": "MM:SS.mmm",
        "end_time": "MM:SS.mmm",
        "visual_description_long": "First segment: Chinese translation; later segments: null",
        "description_change": "First segment: null; later segments: Chinese translation beginning with 与前一片段相比，",
        "contained_actions": [
            {
              "start_time": "MM:SS.mmm",
              "end_time": "MM:SS.mmm",
              "action_description": "Chinese translation"
            }
          ]
      }
    ]
  }
}
```
