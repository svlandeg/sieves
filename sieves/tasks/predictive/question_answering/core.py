from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TypeAlias

import datasets
import pydantic

from sieves.data import Doc
from sieves.engines import Engine, EngineType, dspy_, glix_
from sieves.engines.core import EngineInferenceMode, EngineModel, EnginePromptSignature, EngineResult
from sieves.serialization import Config
from sieves.tasks.predictive.bridges import GliXBridge
from sieves.tasks.predictive.core import PredictiveTask
from sieves.tasks.predictive.question_answering.bridges import (
    DSPyQA,
    InstructorQA,
    LangChainQA,
    OllamaQA,
    OutlinesQA,
)

_TaskPromptSignature: TypeAlias = glix_.PromptSignature | pydantic.BaseModel | dspy_.PromptSignature
_TaskResult: TypeAlias = pydantic.BaseModel | dspy_.Result
_TaskBridge: TypeAlias = DSPyQA | GliXBridge | InstructorQA | LangChainQA | OllamaQA | OutlinesQA


class TaskFewshotExample(pydantic.BaseModel):
    text: str
    reasoning: str
    questions: tuple[str, ...] | list[str]
    answers: tuple[str, ...] | list[str]


class QuestionAnswering(PredictiveTask[_TaskPromptSignature, _TaskResult, _TaskBridge]):
    def __init__(
        self,
        questions: list[str],
        engine: Engine[EnginePromptSignature, EngineResult, EngineModel, EngineInferenceMode],
        task_id: str | None = None,
        show_progress: bool = True,
        include_meta: bool = True,
        prompt_template: str | None = None,
        prompt_signature_desc: str | None = None,
        fewshot_examples: Iterable[TaskFewshotExample] = (),
    ) -> None:
        """
        Initializes new PredictiveTask.
        :param questions: Questions to answer.
        :param task_id: Task ID.
        :param show_progress: Whether to show progress bar for processed documents.
        :param include_meta: Whether to include meta information generated by the task.
        :param prompt_template: Custom prompt template. If None, task's default template is being used.
        :param prompt_signature_desc: Custom prompt signature description. If None, default will be used.
        :param fewshot_examples: Few-shot examples.
        """
        self._questions = questions
        super().__init__(
            engine=engine,
            task_id=task_id,
            show_progress=show_progress,
            include_meta=include_meta,
            overwrite=False,
            prompt_template=prompt_template,
            prompt_signature_desc=prompt_signature_desc,
            fewshot_examples=fewshot_examples,
        )
        self._fewshot_examples: Iterable[TaskFewshotExample]

    def _init_bridge(self, engine_type: EngineType) -> _TaskBridge:
        """Initialize bridge.
        :return: Engine task.
        :raises ValueError: If engine type is not supported.
        """
        if engine_type == EngineType.glix:
            return GliXBridge(
                task_id=self._task_id,
                prompt_template=self._custom_prompt_template,
                prompt_signature_desc=self._custom_prompt_signature_desc,
                prompt_signature=self._questions,
                inference_mode=glix_.InferenceMode.question_answering,
            )

        bridge_types: dict[EngineType, type[_TaskBridge]] = {
            EngineType.dspy: DSPyQA,
            EngineType.instructor: InstructorQA,
            EngineType.outlines: OutlinesQA,
            EngineType.ollama: OllamaQA,
            EngineType.langchain: LangChainQA,
        }

        try:
            bridge_type = bridge_types[engine_type]
            assert not issubclass(bridge_type, GliXBridge)

            return bridge_type(
                task_id=self._task_id,
                prompt_template=self._custom_prompt_template,
                prompt_signature_desc=self._custom_prompt_signature_desc,
                questions=self._questions,
            )
        except KeyError as err:
            raise KeyError(f"Engine type {engine_type} is not supported by {self.__class__.__name__}.") from err

    @property
    def supports(self) -> set[EngineType]:
        return {EngineType.dspy, EngineType.instructor, EngineType.langchain, EngineType.ollama, EngineType.outlines}

    @property
    def _state(self) -> dict[str, Any]:
        return {
            **super()._state,
            "questions": self._questions,
        }

    def to_dataset(self, docs: Iterable[Doc]) -> datasets.Dataset:
        # Define metadata.
        features = datasets.Features(
            {"text": datasets.Value("string"), "answers": datasets.Sequence(datasets.Value("string"))}
        )
        info = datasets.DatasetInfo(
            description=f"Question-answering dataset with questions {self._questions}. Generated with sieves "
            f"v{Config.get_version()}.",
            features=features,
        )

        # Fetch data used for generating dataset.
        try:
            data = [(doc.text, doc.results[self._task_id]) for doc in docs]
        except KeyError as err:
            raise KeyError(f"Not all documents have results for this task with ID {self._task_id}") from err

        def generate_data() -> Iterable[dict[str, Any]]:
            """Yields results as dicts.
            :return: Results as dicts.
            """
            for text, answers in data:
                yield {"text": text, "answers": answers}

        # Create dataset.
        return datasets.Dataset.from_generator(generate_data, features=features, info=info)
