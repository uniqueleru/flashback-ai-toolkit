---
name: flashback-clips
description: Create or revise Minecraft Flashback footage from existing replays or new Carpet bot scenes, using scene observations, recording, agent-authored cameras, previews, and edits.
---

# Flashback Clips

Create the footage the user describes. The agent decides what to show and how to shoot or edit it; the local CLI provides scene data and executes those decisions.

## Creative scope

Let the request determine the subject, framing, camera motion, timing, sound, and format. Do not assume a player subject, tracking camera, cinematic treatment, moving camera, or montage. A simple request can have a simple execution. Use established conversation context; ask only for missing information that materially affects the result.

Treat shot recipes and command examples as possibilities, never as an exhaustive menu. A previous clip or camera failure is evidence about that clip, not a universal shooting rule. For example, stabilization and deliberately rough motion call for different choices.

## Available tools

Use `python -m flashback_agent` from any directory after the package is installed. Run `capabilities` to inspect the current tool contract. Read [tools and operational boundaries](references/tools.md) for the commands needed by the task, and [camera and edit schemas](references/plans.md) when authoring plans.

`capabilities` lists the Minecraft versions that have a bridge build. Run `doctor` before submitting game jobs; when it reports no worker, follow the first-use steps in [background runtime](references/runtime.md), where the user chooses the Minecraft installation. Do not change the user's modpack merely to fit an example.

When footage needs events that have not been recorded, read [Carpet actors and live recording](references/actors.md). The agent can observe and direct bots through structured tools, record the live scene, then use the replay tools. Existing replays remain valid inputs; creating new footage is a task decision. Tool schemas describe mechanics, not a prescribed story or filming style.

## Observe, author, revise

Use metadata, entity samples, and rendered views as needed to understand the scene. Samples describe recorded entities at selected times; they do not identify interesting events or establish what the camera can see. The agent makes those judgments from available evidence. A world-space shot needs no entity target.

Author camera positions, orientations or look-at points, roll, FOV, interpolation, source range, and speed to suit the request. Entity motion can be an input to a plan when useful. Decide whether to preserve, filter, anticipate, or ignore that motion based on the intended shot.

Use previews to resolve uncertain framing or motion, then revise the plan where the evidence warrants it. `review` extracts chronological frames and media properties; it does not grade composition. Sparse stills cannot prove smooth motion, visibility between frames, or the absence of camera shake. Match the depth of review to the requested result and describe what was actually checked.

Use a single plan or an ordered edit according to the brief. Additional media tools can provide editing operations outside this CLI when appropriate. If the available tools cannot express a material requirement, explain the specific limitation rather than quietly substituting another shot.

`--style dynamic-follow` is an optional legacy generator for requests it actually fits. It is not a default, a creative director, or a substitute for authoring other camera behavior.

## Execution and delivery

For game execution, read [background runtime](references/runtime.md). Use the isolated hidden worker by default so automated work does not display windows, take focus or capture the user's mouse. Startup failures must not trigger a visible fallback. This is an execution preference, not a constraint on subjects, scenes or camera choices.

Keep original replays and saved editor state intact. Use a new output path. Rendering requires a live compatible Minecraft client; use the managed worker without disconnecting the user's active game. When a compatible worker cannot run, preserve the plan and report the specific execution problem without claiming an MP4 exists.

Retain job IDs. A waiting timeout or Ctrl+C does not cancel a render: inspect `status`, continue with `wait`, or explicitly `cancel` that job. Resume a sequence from its checkpoint instead of submitting duplicate shots. Retry failures only after identifying a change likely to address the cause.

Deliver the verified output, relevant source intervals/settings, and any material limitations. Preserve editable camera/edit files for revision. Distinguish successful rendering from fulfillment of the user's visual intent.
