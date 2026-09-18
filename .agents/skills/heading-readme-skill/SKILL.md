---
name: heading-readme-skill
description: Use when designing or restructuring a GitHub repository README's hero/header, headings, navigation, badges, section order, or visual hierarchy. Triggers on README layout, template, heading, first-view, or information-architecture requests. Does not invent project facts, installation commands, API behavior, or implementation details.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "1.0.0"
---

# HeadingReadmeSkill

## Purpose

Own the information architecture and visual hierarchy of a repository README.
It may create or revise heading structure and presentation scaffolding, but it must not fabricate repository facts or expand into product documentation ownership.

Primary output: a README heading/layout plan or a bounded README structure update.

## When to use

Use for requests such as:

- 「READMEの見出しを整えて」
- 「GitHubのREADMEを見やすくしたい」
- 「Hero / Badge / Navigationをいい感じにしたい」
- 「このRepositoryに合うREADME構成にして」
- 「README Templateを選んで」
- "Improve the README layout / headings / first view"

Do not use for:

- factual installation/API documentation where layout is not the problem,
- release notes or changelog authoring,
- architecture redesign of the product itself,
- code implementation unrelated to README presentation.

## Core rule

**Repository type determines information architecture. Visual consistency does not mean identical section order.**

Keep the shared visual language consistent while adapting the section sequence to the repository's actual role.

## Workflow

1. **Inspect before composing**
   - Read the current README.
   - Inspect repository metadata and the smallest set of files needed to identify its role.
   - Classify the repository: product/tool, architecture/platform, skills collection, registry/hub, or library/package.
   - If classification is uncertain, preserve the current structure rather than forcing a preset.

2. **Select the first-view contract**
   - Prefer only the useful subset of: logo/hero, title, one-sentence tagline, 3-5 high-signal badges, short navigation, one demo visual.
   - Do not add popularity, sponsor, download, or technology badges unless they materially help the reader.

3. **Compose headings from a preset**
   - Use `references/presets.md`.
   - Add or remove sections based on evidence from the repository.
   - Keep Quick Start early when first-use is the primary reader goal.
   - Keep architecture/responsibility boundaries early when misunderstanding system roles is the primary risk.

4. **Preserve content authority**
   - Reorder or frame existing content without changing technical meaning.
   - Do not invent supported versions, commands, features, compatibility, benchmarks, or roadmap claims.
   - When a needed fact is missing, leave a clear content slot instead of guessing.

5. **Control density**
   - Move long API/reference material out of the main README when a dedicated document already exists.
   - Use tables for capability/compatibility matrices, callouts for warnings, and `<details>` for secondary or advanced material.
   - Avoid repeating the same claim in prose, tables, and diagrams.

6. **Validate the result**
   - Check heading nesting, relative links, image paths, anchor links, and duplicate sections.
   - Confirm the top of the README explains what the project is and gives the next useful action.
   - Confirm manually written content was not rewritten unless the request included content editing.

## Repository-type presets

| Type | Prioritize |
|---|---|
| Product / Tool | Hero → What it is → Why → Quick Start → Capabilities → Advanced |
| Architecture / Platform | Hero → What it is → Architecture → Boundaries → Workflow → Principles |
| Skills collection | Hero → Install → Why → Skill catalog → Usage |
| Registry / Hub | Hero → Role → Does / Does Not → Architecture → Resolution / Compatibility |
| Library / Package | Title → Install → Usage → API entry points → Compatibility |

See `references/presets.md` for full section recipes.

## Reference design language

Use `references/reference-patterns.md` for reusable patterns distilled from:

- CoplayDev/unity-mcp
- hatayama/unity-cli-loop
- affaan-m/ECC
- heygen-com/hyperframes
- emilkowalski/skills

Treat them as design references, not text to copy.

## Scope

This Skill owns:

- Hero/header composition
- Heading hierarchy
- Section order
- README navigation
- Badge density
- Demo placement
- Table / callout / details placement
- Visual and information hierarchy

This Skill does not own:

- technical truth of feature claims,
- installation-command derivation,
- API reference generation,
- changelog generation,
- product architecture decisions,
- implementation code.

## Output contract

Return or apply:

1. **Repository type**
2. **Chosen preset**
3. **First-view structure**
4. **Ordered heading tree**
5. **Sections kept / moved / removed**
6. **Unverified content slots**
7. **Validation performed**

When editing a README, preserve existing technical meaning unless content editing was explicitly requested.

## Quick reference

| Problem | Preferred treatment |
|---|---|
| Too much above the fold | Reduce badges/links; keep one tagline and one primary visual |
| Long install variants | Keep default path visible; fold secondary paths |
| Complex system roles | Add responsibility-boundary section/table early |
| Large skill catalog | Use `Skill | Use when` table |
| Large advanced docs | Link out or use `<details>` |
| Missing project facts | Leave slot / mark unverified; never guess |

## Common mistakes

- Using one fixed README template for every repository.
- Copying reference README wording instead of extracting layout patterns.
- Treating badge count or visual density as quality.
- Putting architecture detail before basic product identity in a simple tool repository.
- Burying responsibility boundaries in a control-plane or registry repository.
- Rewriting human-authored technical content just to make the prose uniform.
- Inventing compatibility, install commands, versions, feature counts, or benchmark claims.
- Turning the README into full documentation instead of a navigable front door.

## Checklist

- [ ] Repository role was identified from evidence.
- [ ] First view is understandable without scrolling through decoration.
- [ ] Badge count is justified.
- [ ] Heading levels are valid and non-duplicated.
- [ ] Section order matches repository type.
- [ ] Existing manual content is preserved unless editing was requested.
- [ ] No unsupported facts were introduced.
- [ ] Links, anchors, and image paths were checked.
