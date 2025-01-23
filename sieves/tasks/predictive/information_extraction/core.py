from __future__ import annotations

import inspect
import warnings
from collections.abc import Iterable
from typing import TypeAlias

import pydantic

from sieves.engines import Engine, EngineType, dspy_, ollama_, outlines_
from sieves.engines.core import EngineInferenceMode, EnginePromptSignature, EngineResult, Model
from sieves.serialization import Attribute
from sieves.tasks.core import PredictiveTask
from sieves.tasks.predictive.information_extraction.bridges import (
    DSPyInformationExtraction,
    InformationExtractionBridge,
    LangChainInformationExtraction,
    OllamaInformationExtraction,
    OutlinesInformationExtraction,
)

TaskPromptSignature: TypeAlias = type[pydantic.BaseModel] | type[dspy_.PromptSignature]  # type: ignore[valid-type]
TaskInferenceMode: TypeAlias = outlines_.InferenceMode | dspy_.InferenceMode | ollama_.InferenceMode
TaskResult: TypeAlias = outlines_.Result | dspy_.Result | ollama_.Result
TaskBridge: TypeAlias = (
    DSPyInformationExtraction
    | LangChainInformationExtraction
    | OutlinesInformationExtraction
    | OllamaInformationExtraction
)


class TaskFewshotExample(pydantic.BaseModel):
    text: str
    reasoning: str
    entities: list[pydantic.BaseModel]


class InformationExtraction(
    PredictiveTask[TaskPromptSignature, TaskResult, Model, TaskInferenceMode, TaskFewshotExample]
):
    def __init__(
        self,
        entity_type: type[pydantic.BaseModel],
        engine: Engine[EnginePromptSignature, EngineResult, Model, EngineInferenceMode],
        task_id: str | None = None,
        show_progress: bool = True,
        include_meta: bool = True,
        prompt_template: str | None = None,
        prompt_signature_desc: str | None = None,
        fewshot_examples: Iterable[TaskFewshotExample] = (),
    ) -> None:
        """
        Initializes new PredictiveTask.
        :param entity_type: Object type to extract.
        :param task_id: Task ID.
        :param show_progress: Whether to show progress bar for processed documents.
        :param include_meta: Whether to include meta information generated by the task.
        :param prompt_template: Custom prompt template. If None, task's default template is being used.
        :param prompt_signature_desc: Custom prompt signature description. If None, default will be used.
        :param fewshot_examples: Few-shot examples.
        """
        self._entity_type = entity_type
        if not self._entity_type.model_config.get("frozen", False):
            warnings.warn(
                f"Entity type provided to task {self._task_id} isn't frozen, which means that entities can't "
                f"be deduplicated. Modify entity_type to be frozen=True."
            )

        super().__init__(
            engine=engine,
            task_id=task_id,
            show_progress=show_progress,
            include_meta=include_meta,
            prompt_template=prompt_template,
            prompt_signature_desc=prompt_signature_desc,
            fewshot_examples=fewshot_examples,
        )

    def _init_bridge(
        self, engine_type: EngineType
    ) -> InformationExtractionBridge[TaskPromptSignature, TaskInferenceMode, TaskResult]:
        """Initialize engine task.
        :returns: Engine task.
        :raises ValueError: If engine type is not supported.
        """
        bridge_types: dict[EngineType, type[TaskBridge]] = {
            EngineType.dspy: DSPyInformationExtraction,
            EngineType.langchain: LangChainInformationExtraction,
            EngineType.outlines: OutlinesInformationExtraction,
            EngineType.ollama: OllamaInformationExtraction,
        }

        try:
            bridge_factory = bridge_types[engine_type]
            assert not inspect.isabstract(bridge_factory)
            bridge = bridge_factory(
                task_id=self._task_id,
                prompt_template=self._custom_prompt_template,
                prompt_signature_desc=self._custom_prompt_signature_desc,
                entity_type=self._entity_type,
            )
        except KeyError:
            raise KeyError(f"Engine type {engine_type} is not supported by {self.__class__.__name__}.")

        return bridge  # type: ignore[return-value]

    @property
    def supports(self) -> set[EngineType]:
        return {EngineType.outlines, EngineType.dspy, EngineType.ollama}

    def _validate_fewshot_examples(self) -> None:
        # No fixed validation we can do here beyond what's already done by Pydantic.
        pass

    @property
    def _attributes(self) -> dict[str, Attribute]:
        return {
            **super()._attributes,
            "entity_type": Attribute(value=self._entity_type, is_placeholder=False),
        }
