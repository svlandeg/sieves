# mypy: ignore-errors
import os

import anthropic
import dspy
import gliner.multitask
import instructor
import langchain_anthropic
import outlines
import pytest
import tokenizers
import transformers

from sieves import Doc, engines


@pytest.fixture(scope="session")
def tokenizer() -> tokenizers.Tokenizer:
    return tokenizers.Tokenizer.from_pretrained("gpt2")


def _make_engine(engine_type: engines.EngineType, batch_size: int):
    """Create engine.
    :param engine_type: Engine type.
    :param batch_size: Batch size to use in engine.
    :returns Engine: Enstantiated engine.
    """
    match engine_type:
        case engines.EngineType.dspy:
            return engines.dspy_.DSPy(
                model=dspy.LM("claude-3-haiku-20240307", api_key=os.environ["ANTHROPIC_API_KEY"]), batch_size=batch_size
            )

        case engines.EngineType.glix:
            model_id = "knowledgator/gliner-multitask-v1.0"
            return engines.glix_.GliX(
                model=gliner.multitask.GLiNERClassifier(model=gliner.GLiNER.from_pretrained(model_id)),
                batch_size=batch_size,
            )

        case engines.EngineType.langchain:
            model = langchain_anthropic.ChatAnthropic(
                model="claude-3-haiku-20240307", api_key=os.environ["ANTHROPIC_API_KEY"]
            )
            return engines.langchain_.LangChain(model=model, batch_size=batch_size)

        case engines.EngineType.instructor:
            model = engines.instructor_.Model(
                name="claude-3-haiku-20240307",
                client=instructor.from_anthropic(anthropic.AsyncClient()),
            )
            return engines.instructor_.Instructor(model=model, batch_size=batch_size)

        case engines.EngineType.huggingface:
            model = transformers.pipeline(
                "zero-shot-classification", model="MoritzLaurer/xtremedistil-l6-h256-zeroshot-v1.1-all-33"
            )
            return engines.huggingface_.HuggingFace(model=model, batch_size=batch_size)

        case engines.EngineType.ollama:
            model = engines.ollama_.Model(client_mode="async", host="http://localhost:11434", name="smollm:135m")
            return engines.ollama_.Ollama(model=model, batch_size=batch_size)

        case engines.EngineType.outlines:
            model_name = "HuggingFaceTB/SmolLM-135M-Instruct"
            return engines.outlines_.Outlines(model=outlines.models.transformers(model_name), batch_size=batch_size)


@pytest.fixture(scope="session")
def batch_engine(request) -> engines.Engine:
    """Initializes engine with batching."""
    assert isinstance(request.param, engines.EngineType)
    return _make_engine(engine_type=request.param, batch_size=-1)


@pytest.fixture(scope="session")
def engine(request) -> engines.Engine:
    """Initializes engine without batching."""
    assert isinstance(request.param, engines.EngineType)
    return _make_engine(engine_type=request.param, batch_size=1)


@pytest.fixture(scope="session")
def dummy_docs() -> list[Doc]:
    return [Doc(text="This is about politics stuff. " * 10), Doc(text="This is about science stuff. " * 10)]


@pytest.fixture(scope="session")
def translation_docs() -> list[Doc]:
    return [Doc(text="It is rainy today."), Doc(text="It is cloudy today.")]


@pytest.fixture(scope="session")
def summarization_docs() -> list[Doc]:
    return [
        Doc(
            text="The decay spreads over the State, and the sweet smell is a great sorrow on the land. Men who can "
            "graft the trees and make the seed fertile and big can find no way to let the hungry people eat their "
            "produce. Men who have created new fruits in the world cannot create a system whereby their fruits "
            "may be eaten. And the failure hangs over the State like a great sorrow. The works of the roots of "
            "the vines, of the trees, must be destroyed to keep up the price, and this is the saddest, bitterest"
            " thing of all. Carloads of oranges dumped on the ground. The people came for miles to take the "
            "fruit, but this could not be. How would they buy oranges at twenty cents a dozen if they could drive"
            " out and pick them up? And men with hoses squirt kerosene on the oranges, and they are angry at the"
            " crime, angry at the people who have come to take the fruit. A million people hungry, needing the"
            " fruit—and kerosene sprayed over the golden mountains. And the smell of rot fills the country."
        ),
        Doc(
            text="After all, the practical reason why, when the power is once in the hands of the people, a majority "
            "are permitted, and for a long period continue, to rule is not because they are most likely to be in"
            " the right, nor because this seems fairest to the minority, but because they are physically the"
            " strongest. But a government in which the majority rule in all cases cannot be based on justice,"
            " even as far as men understand it. Can there not be a government in which majorities do not "
            "virtually decide right and wrong, but conscience?- in which majorities decide only those questions"
            " to which the rule of expediency is applicable? Must the citizen ever for a moment, or in the least"
            " degree, resign his conscience to the legislation? Why has every man a conscience, then? I think"
            " that we should be men first, and subjects afterward. It is not desirable to cultivate a respect for"
            " the law, so much as for the right. The only obligation which I have a right to assume is to do at"
            " any time what I think right. It is truly enough said that a corporation has no conscience; but a"
            " corporation of conscientious men is a corporation with a conscience."
        ),
    ]


@pytest.fixture(scope="session")
def information_extraction_docs() -> list[Doc]:
    return [
        Doc(text="Mahatma Ghandi lived to 79 years old. Bugs Bunny is at least 85 years old."),
        Doc(text="Marie Curie passed away at the age of 67 years. Marie Curie was 67 years old."),
    ]
