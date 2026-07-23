---
name: unity-example-skill
description: Use when <concrete trigger, user wording, or project state>. Produces <specific artifact or decision>. Delegates <adjacent work> to <skill-name>. Does not <important non-goal>.
allowed-tools:
  - Read
metadata:
  version: "1.0.0"
---

# Unity Example Skill

<One paragraph: what this Skill owns, whether it is read-only or mutating, and its primary output.>

## When to use

- <Positive trigger 1>
- <Positive trigger 2>
- <Required input state>

Do not use for <adjacent but excluded work>; use `<other-skill>` instead.

## Delegates to

- `<skill-name>` — <condition and delegated responsibility>
- `<skill-name>` — <condition and delegated responsibility>

Do not copy specialist procedures into this Skill.

## Inputs

- <Required file, Task ID, Incident, Rule ID, or user decision>
- <Unity version / package / platform information>
- <Compatibility contracts>
- <Available evidence>

Resolve known information from repository files before asking the user.

## Step 1 — <Resolve context>

- <Action>
- <Decision>
- <Output>
- <Stop condition, only when essential>

## Step 2 — <Audit or design>

- <Action>
- <Decision>
- <Output>

## Step 3 — <Execute bounded work>

- <Mutation boundary>
- <Compatibility rule>
- <Forbidden scope expansion>

## Step 4 — <Verify>

Report the strongest completed level only:

1. Static inspected
2. Local validator / unit test passed
3. Unity compilation passed
4. Editor reproduction passed
5. Player / IL2CPP passed
6. Target-device measurement passed

## Scope — what this Skill does not do

- <Non-goal 1>
- <Non-goal 2>
- <Adjacent responsibility owned by another Skill>

## Output contract

- Primary result
- Task / Incident / Rule ID
- Changed files or inspected files
- Evidence and confidence
- Compatibility impact
- Validation performed
- Unverified items
- Revert condition or next bounded task

## Checklist

- [ ] Trigger and output were correctly classified
- [ ] Required context was resolved
- [ ] Only the bounded responsibility was executed
- [ ] Compatibility contracts were preserved or explicitly changed
- [ ] Validation state was reported accurately

## Common mistakes

- <Real Unity-specific failure 1>
- <Real Unity-specific failure 2>
- <Overreach or evidence mistake>
