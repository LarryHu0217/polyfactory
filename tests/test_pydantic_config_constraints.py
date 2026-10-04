from enum import Enum
from typing import Any, Literal, Optional, Union

import pytest

import pydantic

import pydantic.v1 as pydantic_v1

from polyfactory.factories.pydantic_factory import _IS_PYDANTIC_V1, ModelFactory


@pytest.fixture(params=["v1", "v2"])
def pydantic_api(request: pytest.FixtureRequest) -> Any:
    if request.param == "v2" and _IS_PYDANTIC_V1:
        pytest.skip("pydantic v2 only functionality")
    return pydantic_v1 if request.param == "v1" else pydantic


def make_model(api: Any, **fields: Any) -> Any:
    config = (
        type("Config", (), {"min_anystr_length": 100, "max_anystr_length": 100})
        if api is pydantic_v1
        else {"str_min_length": 100, "str_max_length": 100}
    )
    return api.create_model("ConfiguredModel", __config__=config, **fields)


@pytest.mark.parametrize("type_name", ["str", "bytes", "SecretStr", "SecretBytes"])
@pytest.mark.parametrize("method", ["build", "coverage"])
def test_model_string_length_config(pydantic_api: Any, type_name: str, method: str) -> None:
    annotation = {"str": str, "bytes": bytes}.get(type_name, getattr(pydantic_api, type_name, None))
    model = make_model(pydantic_api, value=(annotation, ...))
    factory = ModelFactory.create_factory(model=model)
    factory.seed_random(0)

    values = [factory.build()] if method == "build" else list(factory.coverage())
    for value in values:
        generated = value.value
        if hasattr(generated, "get_secret_value"):
            generated = generated.get_secret_value()
        if pydantic_api is pydantic and type_name in {"bytes", "SecretBytes"}:
            assert factory.get_model_fields()[0].constraints is None
            continue
        assert len(generated) == 100


@pytest.mark.parametrize("annotation", [list[str], dict[str, str], tuple[str, str], Optional[str], Union[str, int]])
def test_model_string_length_config_in_children(pydantic_api: Any, annotation: Any) -> None:
    model = make_model(pydantic_api, value=(annotation, ...))
    factory = ModelFactory.create_factory(model=model, __allow_none_optionals__=False)
    factory.seed_random(0)

    for _ in range(10):
        result = factory.build().value
        if isinstance(result, dict):
            assert all(len(item) == 100 for item in (*result.keys(), *result.values()))
        elif isinstance(result, (list, tuple)):
            assert all(len(item) == 100 for item in result)
            assert len(result) < 100
        elif isinstance(result, str):
            assert len(result) == 100
        else:
            assert isinstance(result, int)


@pytest.mark.parametrize("bounds", [(0, 0), (2, 3)])
@pytest.mark.parametrize("method", ["build", "coverage"])
def test_field_string_length_overrides_config(pydantic_api: Any, bounds: tuple[int, int], method: str) -> None:
    model = make_model(pydantic_api, value=(str, pydantic_api.Field(..., min_length=bounds[0], max_length=bounds[1])))
    factory = ModelFactory.create_factory(model=model)
    factory.seed_random(0)

    values = [factory.build()] if method == "build" else list(factory.coverage())
    for value in values:
        assert bounds[0] <= len(value.value) <= bounds[1]


def test_model_config_does_not_apply_to_literal(pydantic_api: Any) -> None:
    model = make_model(pydantic_api, value=(Literal["short"], ...))
    factory = ModelFactory.create_factory(model=model)
    assert factory.build().value == "short"


def test_nested_model_uses_its_own_config(pydantic_api: Any) -> None:
    child_config = (
        type("Config", (), {"min_anystr_length": 2, "max_anystr_length": 2})
        if pydantic_api is pydantic_v1
        else {"str_min_length": 2, "str_max_length": 2}
    )
    child = pydantic_api.create_model("Child", __config__=child_config, value=(str, ...))
    parent = make_model(pydantic_api, child=(child, ...), value=(str, ...))
    factory = ModelFactory.create_factory(model=parent)
    factory.seed_random(0)
    result = factory.build()
    assert len(result.value) == 100
    assert len(result.child.value) == 2


@pytest.mark.parametrize("minimum, maximum", [(100, None), (0, 0), (0, 2), (2, 3)])
def test_independent_model_string_bounds(pydantic_api: Any, minimum: int, maximum: Optional[int]) -> None:
    config = (
        type("Config", (), {"min_anystr_length": minimum, "max_anystr_length": maximum})
        if pydantic_api is pydantic_v1
        else {"str_min_length": minimum, "str_max_length": maximum}
    )
    model = pydantic_api.create_model("ConfiguredModel", __config__=config, value=(str, ...))
    factory = ModelFactory.create_factory(model=model)
    for _ in range(10):
        value = factory.build().value
        assert len(value) >= minimum
        if maximum is not None:
            assert len(value) <= maximum


def test_model_config_does_not_apply_to_string_enum(pydantic_api: Any) -> None:
    class TextEnum(str, Enum):
        SHORT = "short"

    model = make_model(pydantic_api, value=(TextEnum, ...))
    factory = ModelFactory.create_factory(model=model)
    assert factory.build().value is TextEnum.SHORT


def test_one_field_bound_overrides_its_model_default(pydantic_api: Any) -> None:
    config = (
        type("Config", (), {"min_anystr_length": 10, "max_anystr_length": 30})
        if pydantic_api is pydantic_v1
        else {"str_min_length": 10, "str_max_length": 30}
    )
    model = pydantic_api.create_model(
        "ConfiguredModel",
        __config__=config,
        lower=(str, pydantic_api.Field(..., min_length=20)),
        upper=(str, pydantic_api.Field(..., max_length=20)),
    )
    factory = ModelFactory.create_factory(model=model)
    for _ in range(10):
        value = factory.build()
        assert 20 <= len(value.lower) <= 30
        assert 10 <= len(value.upper) <= 20
