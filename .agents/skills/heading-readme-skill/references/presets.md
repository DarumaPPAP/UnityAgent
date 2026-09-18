# HeadingReadmeSkill Presets

Presets define section order, not mandatory content. Omit unsupported sections instead of creating filler.

## Product / Tool

```text
Hero / Logo
Project title
Tagline
Badges
Navigation
Demo
What is it?
Why?
Quick Start
Core Capabilities
How It Works (only when useful)
Advanced
Contributing
License
```

Use when first-time adoption is the main reader task.

## Architecture / Platform

```text
Hero / Title
Tagline
Navigation
What is it?
Core Principles
Architecture
Responsibility Boundaries
Request / Data Flow
Capabilities
Extension Points
Repository Structure
Development
Testing
License
```

Use when component ownership and system boundaries matter more than a marketing-style quickstart.

## Skills Collection

```text
Hero / Title
Tagline
Install
Why use it?
Skills
Usage
Contributing
License
```

Preferred catalog:

| Skill | Use when |
|---|---|
| example-skill | One concise routing condition |

Do not add architecture sections unless the repository itself contains a runtime/orchestrator.

## Registry / Hub

```text
Hero / Title
Tagline
Role
Does / Does Not
System Position
Core Rules
Manifest / Contract
Resolution Flow
Compatibility
Adding a Component
Validation
Development
License
```

Prioritize authority boundaries and exclusion rules. This preset is appropriate for registries, catalogs, plugin hubs, and optional-provider indexes.

## Library / Package

```text
Title
Tagline
Badges
Install
Usage
API Entry Points
Configuration
Examples
Compatibility
Breaking Changes / Migration (when applicable)
Testing
Contributing
License
```

Keep API details shallow in the README when dedicated reference docs exist.

## First-view variants

### Compact

Use for small utilities or skill collections.

```text
Title
One-line purpose
3-4 badges
Install / Quick Start
```

### Visual Product

Use when a screenshot/GIF proves value better than prose.

```text
Logo
Tagline
Badges
Navigation
Single demo visual
One-sentence description
```

### Architecture First

Use when incorrect mental models create integration risk.

```text
Title
One-sentence role
Core invariant / boundary
Architecture link
Responsibility boundary
```

## Selection rule

Choose the smallest preset that makes the repository understandable.
Do not choose a denser preset only because reference repositories look polished.
