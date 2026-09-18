# HeadingReadmeSkill Reference Patterns

These references are design inputs, not canonical templates. Extract structure and reader-flow patterns; do not copy wording.

## Reference set

### CoplayDev/unity-mcp

Source: https://github.com/CoplayDev/unity-mcp/blob/beta/README.md

Useful patterns:

- centered logo and concise project statement,
- one high-value demo visual near the top,
- compact "What it does" section,
- very short three-step Quickstart,
- advanced topics linked out instead of expanded inline.

Avoid blindly copying:

- project-specific sponsor/promotional blocks,
- version/release details that cannot be verified locally.

### hatayama/unity-cli-loop

Source: https://github.com/hatayama/unity-cli-loop/blob/main/README_ja.md

Useful patterns:

- Concept → Quick Start → How it works → Design philosophy,
- explicit explanation of why the system is designed a certain way,
- command/use-case tables that connect user intent to tooling,
- advanced material collapsed or moved after the main path.

Best fit:

- technical products where architecture and design reasoning are part of adoption.

### affaan-m/ECC

Source: https://github.com/affaan-m/ECC/blob/main/README.md

Useful patterns:

- strong hero treatment,
- warnings/callouts near risky install paths,
- capability and compatibility matrices,
- clear separation between supported and limited integration paths.

Avoid blindly copying:

- excessive badges,
- sponsor/marketing density,
- repeated popularity metrics,
- large promotional blocks above core product identity.

### heygen-com/hyperframes

Source: https://github.com/heygen-com/hyperframes/blob/main/README.md

Useful patterns:

- logo → badges → short tagline → nav → demo,
- strong first-view composition,
- Quick Start immediately after product identity,
- `Skill | Use when` catalog format,
- default/core path separated from optional/advanced workflows.

Best fit:

- product + skills repositories,
- agent-facing tools where routing intent matters.

### emilkowalski/skills

Source: https://github.com/emilkowalski/skills/blob/main/README.md

Useful patterns:

- minimal framing,
- clear Why → Install → Reference progression,
- short descriptions per skill,
- low ceremony for repositories whose main product is the skill catalog itself.

Best fit:

- focused skills collections where architecture prose would be noise.

## Combined design rules

1. Use a strong first view only when there is something worth showing.
2. Prefer one demo over several decorative screenshots.
3. Keep badges to 3-5 high-signal items by default.
4. Put default installation/first-use path before exhaustive variants.
5. Put responsibility boundaries early for control planes, registries, hubs, and orchestrators.
6. Put `Skill | Use when` tables in skills repositories.
7. Use README as a front door; push deep reference material to dedicated docs when available.
8. Never infer technical facts from visual style.
