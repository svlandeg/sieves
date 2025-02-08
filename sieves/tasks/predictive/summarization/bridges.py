import abc
from collections.abc import Iterable
from functools import cached_property
from typing import Any, TypeVar

import dspy
import jinja2
import pydantic

from sieves.data import Doc
from sieves.engines import EngineInferenceMode, dspy_, instructor_, langchain_, ollama_, outlines_
from sieves.tasks.predictive.core import Bridge

_BridgePromptSignature = TypeVar("_BridgePromptSignature")
_BridgeResult = TypeVar("_BridgeResult")


class SummarizationBridge(
    Bridge[_BridgePromptSignature, _BridgeResult, EngineInferenceMode],
    abc.ABC,
):
    def __init__(
        self,
        task_id: str,
        prompt_template: str | None,
        prompt_signature_desc: str | None,
        max_n: int,
    ):
        """
        Initializes InformationExtractionBridge.
        :param task_id: Task ID.
        :param prompt_template: Custom prompt template.
        :param prompt_signature_desc: Custom prompt signature description.
        :param max_n: Maximal number of words (consider this a guideline, not a strict limit).
        """
        super().__init__(task_id=task_id, prompt_template=prompt_template, prompt_signature_desc=prompt_signature_desc)
        self._max_n = max_n

    def extract(self, docs: Iterable[Doc]) -> Iterable[dict[str, Any]]:
        return ({"text": doc.text if doc.text else None, "max_n": self._max_n} for doc in docs)


class DSPySummarization(SummarizationBridge[dspy_.PromptSignature, dspy_.Result, dspy_.InferenceMode]):
    @property
    def _prompt_template(self) -> str | None:
        return None

    @property
    def _prompt_signature_description(self) -> str | None:
        return "Summary of a longer text."

    @cached_property
    def prompt_signature(self) -> type[dspy_.PromptSignature]:
        class Summary(dspy.Signature):  # type: ignore[misc]
            text: str = dspy.InputField(description="Text to summarize.")
            max_n: str = dspy.InputField(description="Maximal number of words to use for summary.")
            summary: str = dspy.OutputField(description="Summary of text.")

        Summary.__doc__ = jinja2.Template(self.prompt_signature_description).render()

        return Summary

    @property
    def inference_mode(self) -> dspy_.InferenceMode:
        return dspy_.InferenceMode.chain_of_thought

    def integrate(self, results: Iterable[dspy_.Result], docs: Iterable[Doc]) -> Iterable[Doc]:
        for doc, result in zip(docs, results):
            assert len(result.completions.summary) == 1
            doc.results[self._task_id] = result.summary
        return docs

    def consolidate(
        self, results: Iterable[dspy_.Result], docs_offsets: list[tuple[int, int]]
    ) -> Iterable[dspy_.Result]:
        results = list(results)

        # Merge all chunk translations.
        for doc_offset in docs_offsets:
            summaries: list[str] = []

            for res in results[doc_offset[0] : doc_offset[1]]:
                if res is None:
                    continue
                summaries.append(res.summary)

            yield dspy.Prediction.from_completions(
                {"summary": ["\n".join(summaries)]},
                signature=self.prompt_signature,
            )


class PydanticBasedSummarization(
    SummarizationBridge[pydantic.BaseModel, pydantic.BaseModel, EngineInferenceMode],
    abc.ABC,
):
    @property
    def _prompt_template(self) -> str | None:
        return """
        Your goal is to summarize a text. This summary shouldn't be longer than {{ max_n }} words.

        {% if examples|length > 0 -%}
            Examples:
            ----------
            {%- for example in examples %}
                Text: "{{ example.text }}":
                Max. number of words in summary: {{ example.max_n }}
                Summary: "{{ example.summary }}"
            {% endfor -%}
            ----------
        {% endif -%}

        ========
        Text: {{ text }}
        Max. number of words in summary: {{ max_n }}
        Summary: 
        """

    @property
    def _prompt_signature_description(self) -> str | None:
        return None

    @cached_property
    def prompt_signature(self) -> type[pydantic.BaseModel]:
        class Summary(pydantic.BaseModel, frozen=True):
            summary: str

        if self.prompt_signature_description:
            Summary.__doc__ = jinja2.Template(self.prompt_signature_description).render()

        return Summary

    def integrate(self, results: Iterable[pydantic.BaseModel], docs: Iterable[Doc]) -> Iterable[Doc]:
        for doc, result in zip(docs, results):
            assert hasattr(result, "summary")
            doc.results[self._task_id] = result.summary
        return docs

    def consolidate(
        self, results: Iterable[pydantic.BaseModel], docs_offsets: list[tuple[int, int]]
    ) -> Iterable[pydantic.BaseModel]:
        results = list(results)

        # Determine label scores for chunks per document.
        for doc_offset in docs_offsets:
            summaries: list[str] = []

            for res in results[doc_offset[0] : doc_offset[1]]:
                if res:
                    assert hasattr(res, "summary")
                    summaries.append(res.summary)

            yield self.prompt_signature(summary="\n".join(summaries))


class OutlinesSummarization(PydanticBasedSummarization[outlines_.InferenceMode]):
    @property
    def inference_mode(self) -> outlines_.InferenceMode:
        return outlines_.InferenceMode.json


class OllamaSummarization(PydanticBasedSummarization[ollama_.InferenceMode]):
    @property
    def inference_mode(self) -> ollama_.InferenceMode:
        return ollama_.InferenceMode.chat


class LangChainSummarization(PydanticBasedSummarization[langchain_.InferenceMode]):
    @property
    def inference_mode(self) -> langchain_.InferenceMode:
        return langchain_.InferenceMode.structured_output


class InstructorSummarization(PydanticBasedSummarization[instructor_.InferenceMode]):
    @property
    def inference_mode(self) -> instructor_.InferenceMode:
        return instructor_.InferenceMode.chat
