"""Graph Observatory artifact pipeline.

Canonical data -> projection -> graph artifact -> validation.
Graph is a derived view and never mutates canonical sources.
"""

from dataclasses import dataclass


@dataclass
class PipelineResult:
    artifact_path: str
    validated: bool


class GraphArtifactPipeline:
    def __init__(self, validator):
        self._validator = validator

    def run(self, artifact):
        result = self._validator.validate(artifact)
        if not result:
            raise ValueError("Graph artifact validation failed")

        return PipelineResult(
            artifact_path="Artifacts/graph/observatory.json",
            validated=True,
        )
