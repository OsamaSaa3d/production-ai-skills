# Metaprompting: Diagnose, Then Patch

Guessing which line caused a behavior is expensive and usually wrong. Hand the prompt and its failures back to a model and ask it to find the drivers.

**Use two separate calls.** Asking for diagnosis and fix together produces a rewrite with a post-hoc justification. Separating them gives you an analysis you can disagree with before any edit exists.

## Assembling the failure set

Each trace needs four fields. Anything less and the analysis is speculation.

```json
{
  "query": "What's a good venue for a 20-person leadership dinner?",
  "tools_called": ["venue_search", "catering_search"],
  "final_answer": "Here are three certified-sustainable venues in Austin... (620 words)",
  "eval_signal": "thumbs_down — user asked a conceptual question and got a booking list"
}
```

Two rules:

**Batch by theme.** One failure mode per diagnosis call. A dump mixing verbosity failures with tool-eagerness failures produces analysis that ties no thread properly — the model spreads its attention and names vague causes. Run separate calls and merge the patches yourself.

**Include the tools *actually* called, not the ones you expected.** The gap between them is often the entire finding.

**8-20 traces is a good size.** Fewer and you're patching noise; more and the analysis generalizes past what you can verify.

## Call 1 — diagnosis only

```text
You are a prompt engineer debugging a system prompt for <one line: what the
agent does>.

You are given:

1) The current system prompt:
<system_prompt>
{SYSTEM_PROMPT}
</system_prompt>

2) A set of logged failures. Each has: query, tools_called (as actually
executed), final_answer (shortened if needed), eval_signal.
<failure_traces>
{FAILURE_TRACES}
</failure_traces>

Your tasks:

1) Identify the distinct failure modes you see (e.g. tool_usage_inconsistency,
   autonomy_vs_clarifications, verbosity_vs_concision, unit_mismatch).
2) For each, quote or paraphrase the specific lines or sections of the system
   prompt most likely causing or reinforcing it. Include any contradictions
   between lines.
3) Briefly explain how those lines steer the agent toward the observed
   behavior.

Do not propose fixes.

Return:

failure_modes:
- name: ...
  description: ...
  prompt_drivers:
    - exact_or_paraphrased_line: ...
      why_it_matters: ...
```

Read this output before proceeding. You are looking for one specific thing: **pairs of lines that cannot both be satisfied.** Those are the real findings. A driver identified as "this line is vague" is weaker evidence and may just be the model pattern-matching.

## Call 2 — surgical patch

```text
You previously analyzed this system prompt and its failure modes.

<system_prompt>
{SYSTEM_PROMPT}
</system_prompt>

Failure-mode analysis:
{ANALYSIS}

Propose a surgical revision that reduces the observed issues while preserving
the good behaviors.

Constraints:
- Do not redesign the agent from scratch.
- Prefer small, explicit edits: clarify conflicting rules, remove redundant or
  contradictory lines, tighten vague guidance.
- Make tradeoffs explicit — state exactly when to prioritize concision over
  completeness, and exactly when tools must vs must not be called.
- Keep the structure and overall length roughly similar, unless a short
  consolidation removes obvious duplication.

Output:
1) patch_notes: the key changes and the reasoning behind each.
2) revised_system_prompt: the full updated prompt, ready to drop in.
```

The constraints are doing real work. Without them the model returns a plausible-looking full rewrite whose diff you cannot review, which means you cannot attribute a later regression to anything.

## Reviewing the patch

Read `patch_notes` first, then diff the prompt. Reject the patch if it:

- **Grew substantially.** A patch that adds 40 lines has not resolved contradictions, it has added participants.
- **Resolved a contradiction by deleting the rule you care about.** The model does not know which side of the tradeoff matters to your product. Check every removal.
- **Replaced a heuristic with an enumeration.** This is a common regression — models are happy to convert one good sentence into eight cases.
- **Introduced an absolute with no escape hatch.** "Always call X before responding" reintroduces null-argument failures.

## Closing the loop

```text
1. Re-run the failure set on the patched prompt. Did the named modes improve?
2. Re-run the full regression suite. What regressed?
3. If a mode is unimproved, the diagnosis was wrong, not the patch — go back
   to call 1 with a tighter trace batch.
4. Commit the patch and the eval delta together.
```

Repeat until the failure modes are triaged. Expect two or three rounds; expect the second round to be about a contradiction the first round introduced.

## Using it to grow a prompt

Metaprompting is also the right way to *add* scope. When broadening an agent — new tools, a new domain — describe the addition and ask the model to integrate it into the existing prompt rather than appending a section by hand. Appending is how you get two tool-guidance blocks with different rules. Integration forces the boundary between the new and existing behavior to be stated.

## Limits

- The model will confidently name drivers that aren't. Weight contradiction findings heavily and "this is vague" findings lightly.
- It cannot tell you which behavior is *desired*. Every tradeoff resolution is your call.
- It cannot replace the regression suite. Metaprompting generates hypotheses; `evals-before-shipping` decides.
- Do not run it against a prompt with no failure set. With nothing to explain, it will restructure for tidiness and you will ship an unmeasured change.
