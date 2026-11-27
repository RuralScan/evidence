# RuralScan evidence agent guide

This repository owns current evidence workflows and register submissions. CIAT is
read-only history. Preserve unrelated working changes and immutable archives.

## Inclusion before extraction or reuse

Read [the inclusion protocol](handbook/nbs-inclusion.md) for every current discovery,
extraction, review or synthesis task. It applies to all six NbS, both suitability and
effect evidence, and previously approved evidence being reused. Use the authorised
World Bank catalogue's general definition and relevant practice section; keep its
restricted text and assessment privately. Public definitions are context, not proof
that the restricted catalogue was inspected. Missing access means a visible hold.

Keep three decisions separate: practice/family fit, NbS fit, and analytical-role fit.
For water harvesting, harvesting must be a primary purpose supported by source
design and intent. Incidental infiltration, recharge or erosion reduction does not
qualify. A credible NbS can still be the wrong practice. Do not reroute it silently.

Use `workflows/inclusion/check.py` on the private assessment before current staging
or reuse. The checker validates recorded judgments and source/definition hashes;
it cannot read scientific meaning or grant human approval. Follow its hold/exclude
result. Conditional scoping inclusion carries its conditions into every proposal.
Detailed feasibility, monitoring and site design remain downstream.

Current adapters: `.agents/skills/source-command-discover-sources/SKILL.md`,
`.agents/skills/source-command-extract-evidence/SKILL.md`, and the two synthesis
skills. Record their versions plus `nbs-inclusion-1.0.0` and exact instruction hashes.
Never restamp historical units or modify archived rulesets to imply re-review.

## Writes and confidentiality

Source/evidence IDs, quotations and locators survive exclusions. Use reversible
`wrong_practice` drops for established practice mismatches; holds remain holds.
An NbS exclusion needs its own explicit scientific rationale, not a false claim
that the practice label is wrong. Existing approved records require explicit
supersession/reopening and the protected submission route.

Follow `workflows/submissions/README.md`. Receipts, review confirmation, scientific
acceptance and PR merge are separate. Never fabricate a human vote, accept your own
synthesis as a human or merge without authorisation. Do not write registers by hand.
Do not put restricted catalogue files, quotes, clause-level paraphrases, email-chain
details, private assessment paths or assessment contents in public Git/issues.
Use public sources and project-owned scope decisions for public explanations.

Run checks appropriate to changed workflows. Keep local corpus, decisions and
assessment bundles outside Git; do not add unrelated `audit/` work to commits.
