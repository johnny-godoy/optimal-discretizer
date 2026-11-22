# Writing style

Two audiences need two styles. People read documentation, so it follows Simplified Technical English. Models read
prompts, so they follow Anthropic's prompting guide. Choose the style by the reader, not by the file type.

## Documentation: 80% of the way to ASD-STE100

Scope: `README.md`, `ROADMAP.md`, `docs/` (except `docs/plans/`), `scripts/README.md`,
`CONTRIBUTING.md`, `CHANGELOG.md`, docstrings, code comments and notebook prose. Exempt: code, command output, quoted
error text and proper names.

Write "80% of the way to ASD-STE100". The full specification is very strict, so follow its spirit: plain, short,
unambiguous sentences. Models know the specification well, so no tool or count measures compliance. Use the rules below
as a guide, and break one when a strict version would make the text harder to read.

1. Write one instruction per sentence, in the imperative. Procedure sentences have at most 20 words.
2. Descriptive sentences have at most 25 words. Put one idea in each.
3. Paragraphs have at most 6 sentences.
4. Use the active voice and the simple present tense. Use the future tense only for events that have not happened.
5. Keep articles (`a`, `the`) and write full sentences. Do not use fragments or telegraphic style.
6. Use one word for one meaning, and use it every time. Do not vary terms for style (`graph`, not `plot` or `chart`).
7. Use the simplest word (`use`, not `utilize`; `start`, not `initiate`; `check`, not `verify` when `check` is exact).
8. Do not use a noun as a verb, or a verb as a noun, when a common word exists. Avoid phrasal verbs with several senses.
9. Do not use the `-ing` form as a verb in a procedure. Do not use idioms, jokes or figures of speech.
10. Put a warning before the step it applies to. Put the condition before the instruction (`If X, do Y`).
11. Use a list for steps or items that are really parallel. Use a table for a lookup. Use prose for explanation.
12. Do not use noun strings of more than three nouns. Add a preposition or split the phrase.

The STE dictionary at <https://www.asd-ste100.org> is the reference for approved words and meanings. A technical name
(`summarize`, `DATABASE_URL`) is always allowed.

## Current state, not history

The package has no users yet and makes no promise of backward compatibility. Every document describes the code as it
is now. It is not a log. Edit or replace a sentence when the code changes, and do not add a note about the old state.

- Do not write "before", "no longer", "now", "used to", "still", "keeps working", "the old ..." or "new" to compare
  with an earlier version. Write what the code does.
- Do not promise compatibility with an earlier version ("so code that you wrote before still works"), unless the user
  has chosen to keep it.
- Do not tell the story of the project ("started as a port of", "ported from"). State the relation in the present
  tense ("is based on", "follows") and only where the reader needs it.
- Do not keep a deprecated or removed item in the text. Delete the text with the item.
- A comparison with another tool is allowed as a description ("How this differs from library X").
- Exempt: `CHANGELOG.md`, which is a log by design, and a word with its normal sense ("before the call" for order,
  "a new row" for an addition).
- Audit: run `rg -in "\bbefore\b|no longer|used to|started as|\bported?\b|\bold\b|backward"` over the files in
  scope and read each match. Fix the sentence when it compares with an earlier state.

## LLM prompts: Anthropic prompting guide

Scope: every prompt string in the code, `CLAUDE.md`, the rules in `.claude/rules/`, and the implementation plans in
`docs/plans/`, which are handoff prompts for the agent that implements each feature. Reference:
<https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview>, which sends you to
<https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices>.

Prompts are not STE. A model gains from context and examples that STE would remove. Apply these rules instead:

- **Be clear and direct.** Say exactly what output you want, with its format and limits. Pass the colleague test:
  if a person with no context would be confused by the prompt, the model will be too.
- **Give the reason.** A rule with its motive generalizes better than a bare command. Write "the reader is a layperson,
  so give no numbers", not "NEVER give numbers".
- **Say what to do, not what to avoid.** Write "answer in plain prose paragraphs", not "do not use markdown".
- **Use XML tags** with consistent, descriptive names to separate instructions, context, examples and inputs
  (`<instructions>`, `<document>`, `<example>`). Nest tags when the content has a hierarchy.
- **Use examples** that are relevant, diverse and wrapped in `<example>` tags inside `<examples>`. Use 3 to 5 when the
  format matters.
- **Set a role** in one sentence at the start of the system prompt.
- **Put long data first** and the question or task last. For a long document, ask the model to quote the
  relevant parts before it answers.
- **Match the prompt's formatting to the output you want.** A prompt full of markdown produces markdown.
- **Order steps** as a numbered list when order matters. Ask for reasoning before the final answer when accuracy
  matters.
- **Test the change.** Compare the new prompt with the old one on the tests of the prompt. Do not change a prompt on
  taste alone.

`CLAUDE.md` is a prompt too: give each rule with its reason, state it positively, and group content under clear
headings or tags. Keep it short, because every line costs context in every session.

## Checks

- After you edit a prose file, reread it once against the documentation list above, or the prompt list for a prompt.
- A user-visible wording change in a prompt needs a changelog fragment (`just changelog`).
