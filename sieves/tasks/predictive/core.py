from __future__ import annotations

import abc
import enum
from collections.abc import Iterable
from typing import Any, Generic, TypeVar

import datasets
import pydantic

from sieves.data import Doc
from sieves.engines import (
    Engine,
    EngineInferenceMode,
    EngineModel,
    EnginePromptSignature,
    EngineResult,
    EngineType,
)
from sieves.serialization import Config, Serializable
from sieves.tasks.core import Task

_TaskPromptSignature = TypeVar("_TaskPromptSignature", covariant=True)
_TaskResult = TypeVar("_TaskResult")
_TaskBridge = TypeVar("_TaskBridge", bound="Bridge[_TaskPromptSignature, _TaskResult, EngineInferenceMode]")  # type: ignore[valid-type]


class PredictiveTask(
    Generic[_TaskPromptSignature, _TaskResult, _TaskBridge],
    Task,
    abc.ABC,
):
    def __init__(
        self,
        engine: Engine[EnginePromptSignature, EngineResult, EngineModel, EngineInferenceMode],
        task_id: str | None,
        show_progress: bool,
        include_meta: bool,
        prompt_template: str | None = None,
        prompt_signature_desc: str | None = None,
        fewshot_examples: Iterable[pydantic.BaseModel] = (),
    ):
        """
        Initializes new PredictiveTask.
        :param task_id: Task ID.
        :param show_progress: Whether to show progress bar for processed documents.
        :param include_meta: Whether to include meta information generated by the task.
        :param prompt_template: Custom prompt template. If None, default template is being used.
        :param prompt_signature_desc: Custom prompt signature description. If None, default will be used.
        :param fewshot_examples: Few-shot examples.
        """
        super().__init__(task_id=task_id, show_progress=show_progress, include_meta=include_meta)
        self._engine = engine
        self._custom_prompt_template = prompt_template
        self._custom_prompt_signature_desc = prompt_signature_desc
        self._bridge = self._init_bridge(EngineType.get_engine_type(self._engine))
        self._fewshot_examples = fewshot_examples

        self._validate_fewshot_examples()

    def _validate_fewshot_examples(self) -> None:
        """Validates fewshot examples.
        :raises: ValueError if fewshot examples don't pass validation.
        """
        pass

    @abc.abstractmethod
    def _init_bridge(self, engine_type: EngineType) -> _TaskBridge:
        """Initialize engine task.
        :returns: Engine task.
        """

    @property
    @abc.abstractmethod
    def supports(self) -> set[EngineType]:
        """Returns supported engine types.
        :returns: Supported engine types.
        """

    @property
    def prompt_template(self) -> str | None:
        """Returns prompt template.
        :returns: Prompt template.
        """
        prompt_template = self._bridge.prompt_template
        assert prompt_template is None or isinstance(prompt_template, str)
        return prompt_template

    @property
    def prompt_signature_description(self) -> str | None:
        """Returns prompt signature description.
        :returns: Prompt signature description.
        """
        sig_desc = self._bridge.prompt_signature_description
        assert sig_desc is None or isinstance(sig_desc, str)
        return sig_desc

    def __call__(self, docs: Iterable[Doc]) -> Iterable[Doc]:
        """Execute the task on a set of documents.

        Note: the mypy ignore directives are because in practice, TaskX can be a superset of the X types of multiple
        engines, but there is no way in Python's current typing system to model that. E.g.: TaskInferenceMode could be
        outlines_.InferenceMode | dspy_.InferenceMode, depending on the class of the dynamically provided engine
        instance. TypeVars don't support unions however, neither do generics on a higher level of abstraction.
        We hence ignore these mypy errors, as the involved types should nonetheless be consistent.

        :param docs: The documents to process.
        :returns: The processed document
        """
        docs = list(docs)

        # 1. Compile expected prompt signatures.
        signature = self._bridge.prompt_signature

        # 2. Build executable.
        assert isinstance(self._bridge.inference_mode, enum.Enum)
        executable = self._engine.build_executable(
            inference_mode=self._bridge.inference_mode,
            prompt_template=self.prompt_template,
            prompt_signature=signature,
            fewshot_examples=self._fewshot_examples,
        )

        # 3. Extract values from docs to inject/render those into prompt templates.
        docs_values = self._bridge.extract(docs)

        # 4. Map extracted docs values onto chunks.
        docs_chunks_offsets: list[tuple[int, int]] = []
        docs_chunks_values: list[dict[str, Any]] = []
        for doc, doc_values in zip(docs, docs_values):
            assert doc.text
            doc_chunks_values = [doc_values | {"text": chunk} for chunk in (doc.chunks or [doc.text])]
            docs_chunks_offsets.append((len(docs_chunks_values), len(docs_chunks_values) + len(doc_chunks_values)))
            docs_chunks_values.extend(doc_chunks_values)

        # 5. Execute prompts per chunk.
        results = list(executable(docs_chunks_values))
        assert len(results) == len(docs_chunks_values)

        # 6. Consolidate chunk results.
        results = list(self._bridge.consolidate(results, docs_chunks_offsets))
        assert len(results) == len(docs)

        # 7. Integrate results into docs.
        docs = self._bridge.integrate(results, docs)

        return docs

    @property
    def _state(self) -> dict[str, Any]:
        return {
            **super()._state,
            "engine": self._engine.serialize(),
            "prompt_template": self._custom_prompt_template,
            "prompt_signature_desc": self._custom_prompt_signature_desc,
            "fewshot_examples": self._fewshot_examples,
        }

    @classmethod
    def deserialize(
        cls, config: Config, **kwargs: dict[str, Any]
    ) -> PredictiveTask[_TaskPromptSignature, _TaskResult, _TaskBridge]:
        """Generate PredictiveTask instance from config.
        :param config: Config to generate instance from.
        :param kwargs: Values to inject into loaded config.
        :returns: Deserialized PredictiveTask instance.
        """
        # Validate engine config.
        assert hasattr(config, "engine")
        assert isinstance(config.engine.value, Config)
        engine_config = config.engine.value
        engine_cls = engine_config.config_cls
        assert issubclass(engine_cls, Serializable)
        assert issubclass(engine_cls, Engine)

        # Deserialize and inject engine.
        engine_param: dict[str, Any] = {"engine": engine_cls.deserialize(engine_config, **kwargs["engine"])}
        return cls(**config.to_init_dict(cls, **(kwargs | engine_param)))

    @abc.abstractmethod
    def docs_to_dataset(self, docs: Iterable[Doc]) -> datasets.Dataset:
        """Creates Hugging Face datasets.Dataset from docs.
        :param docs: Docs to convert.
        :returns: Hugging Face dataset.
        """


class Bridge(Generic[_TaskPromptSignature, _TaskResult, EngineInferenceMode], abc.ABC):
    def __init__(self, task_id: str, prompt_template: str | None, prompt_signature_desc: str | None):
        """
        Initializes new bridge.
        :param task_id: Task ID.
        :param prompt_template: Custom prompt template. If None, default will be used.
        :param prompt_signature_desc: Custom prompt signature description. If None, default will be used.
        """
        self._task_id = task_id
        self._custom_prompt_template = prompt_template
        self._custom_prompt_signature_desc = prompt_signature_desc

    @property
    @abc.abstractmethod
    def prompt_template(self) -> str | None:
        """Returns prompt template.
        Note: different engines have different expectations as how a prompt should look like. E.g. outlines supports the
        Jinja 2 templating format for insertion of values and few-shot examples, whereas DSPy integrates these things in
        a different value in the workflow and hence expects the prompt not to include these things. Mind engine-specific
        expectations when creating a prompt template.
        :returns: Prompt template as string. None if not used by engine.
        """

    @property
    @abc.abstractmethod
    def prompt_signature_description(self) -> str | None:
        """Returns prompt signature description. This is used by some engines to aid the language model in generating
        structured output.
        :returns: Prompt signature description. None if not used by engine.
        """

    @property
    @abc.abstractmethod
    def prompt_signature(self) -> type[_TaskPromptSignature] | _TaskPromptSignature:
        """Creates output signature (e.g.: `Signature` in DSPy, Pydantic objects in outlines, JSON schema in
        jsonformers). This is engine-specific.
        :returns: Output signature object. This can be an instance (e.g. a regex string) or a class (e.g. a Pydantic
            class).
        """

    @property
    @abc.abstractmethod
    def inference_mode(self) -> EngineInferenceMode:
        """Returns inference mode.
        :returns: Inference mode.
        """

    def extract(self, docs: Iterable[Doc]) -> Iterable[dict[str, Any]]:
        """Extract all values from doc instances that are to be injected into the prompts.
        :param docs: Docs to extract values from.
        :returns: All values from doc instances that are to be injected into the prompts
        """
        return ({"text": doc.text if doc.text else None} for doc in docs)

    @abc.abstractmethod
    def integrate(self, results: Iterable[_TaskResult], docs: Iterable[Doc]) -> Iterable[Doc]:
        """Integrate results into Doc instances.
        :param results: Results from prompt executable.
        :param docs: Doc instances to update.
        :returns: Updated doc instances.
        """

    @abc.abstractmethod
    def consolidate(self, results: Iterable[_TaskResult], docs_offsets: list[tuple[int, int]]) -> Iterable[_TaskResult]:
        """Consolidates results for document chunks into document results.
        :param results: Results per document chunk.
        :param docs_offsets: Chunk offsets per document. Chunks per document can be obtained with
            results[docs_chunk_offsets[i][0]:docs_chunk_offsets[i][1]].
        :returns: Results per document.
        """
