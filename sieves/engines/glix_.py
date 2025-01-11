import enum
import warnings
from collections.abc import Iterable
from typing import Any, TypeAlias

import gliclass
import gliner

from sieves.engines.core import Engine, Executable

PromptSignature: TypeAlias = list[str]
Model: TypeAlias = gliner.GLiNER | gliclass.ZeroShotClassificationPipeline
Result: TypeAlias = dict[str, str | float]


class InferenceMode(enum.Enum):
    """Available inference modes."""

    gliner = 0
    gliclass = 1


class GliX(Engine[PromptSignature, Result, Model, InferenceMode]):
    def __init__(self, model: Model, threshold: float = 0.5):
        """
        :param model: Model to run. Should be gliclass.ZeroShotClassificationPipeline or gliner.GLiNER.
        :param threshold: Threshold to use for scores.
        """
        super().__init__(model)
        self._threshold = threshold

    @property
    def inference_modes(self) -> type[InferenceMode]:
        return InferenceMode

    @property
    def supports_few_shotting(self) -> bool:
        return False

    def build_executable(
        self,
        inference_mode: InferenceMode,
        prompt_template: str | None,
        prompt_signature: PromptSignature,
    ) -> Executable[Result]:
        cls_name = self.__class__.__name__
        if prompt_template:
            warnings.warn(f"prompt_template is ignored by {cls_name} engine.")

        def execute(values: Iterable[dict[str, Any]]) -> Iterable[Result]:
            texts = [dv["text"] for dv in values]
            match inference_mode:
                case InferenceMode.gliclass:
                    result = self._model(texts, prompt_signature, threshold=self._threshold)
                case InferenceMode.gliner:
                    result = self._model.batch_predict_entities(texts, prompt_signature, threshold=self._threshold)
                case _:
                    raise ValueError(f"Inference mode {inference_mode} not supported by {cls_name} engine.")

            assert isinstance(result, Iterable)
            return result

        return execute
