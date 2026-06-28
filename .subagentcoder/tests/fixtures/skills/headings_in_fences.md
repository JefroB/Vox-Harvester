---
name: Markdown Processing
tags: [code, docs]
description: Rules for parsing and generating markdown content.
---

# Markdown Processing

Guidance for working with markdown documents programmatically.

## Parsing Rules

- Split documents on level-2 headings (`## `) for section extraction
- NEVER split on headings inside fenced code blocks
- Treat sub-headings (###, ####) as part of the parent section

Example of a markdown template that contains headings in code:

```markdown
# My Document

## Introduction

This is the intro section.

## API Reference

Details about the API here.

### Subsection

More content under subsection.
```

The parser must not be confused by the above fenced content.

## Code Generation

- ALWAYS preserve language annotations on fenced code blocks
- Use triple backticks, never indented code blocks

Here is another tricky case with nested fences and headings:

```python
TEMPLATE = """
## Section Header

This is a template string that contains markdown headings.
The parser should ignore these completely.

## Another Header In Template

More template content here.
"""

def split_sections(doc: str) -> list[str]:
    """Split on ## outside fences only."""
    pass
```

- Validate generated markdown renders correctly
- MUST escape special characters in user-provided content

## Output Formatting

- Use consistent heading levels (never skip from ## to ####)
- Separate sections with exactly one blank line
- ALWAYS end files with a trailing newline
