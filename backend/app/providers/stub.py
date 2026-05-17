from __future__ import annotations

from .base import ProviderRequest, ProviderResult


class StubHoroscopeProvider:
    name = "stub"
    model_name = "stub"

    def generate(self, request: ProviderRequest) -> ProviderResult:
        text = (
            "Вас ждет спокойный день, в котором лучше не спешить с выводами "
            "и внимательно относиться к небольшим подсказкам вокруг. "
            "Вам будет проще двигаться вперед, если выбрать одно главное дело "
            "и не распыляться на лишнее. "
            "Ближе к вечеру Вас может порадовать приятная новость или теплый разговор."
        )
        response_payload = {
            "title": None,
            "text": text,
        }

        return ProviderResult(
            title=None,
            text=text,
            payload={"text": text},
            request_payload=request.to_payload(),
            response_payload=response_payload,
            raw_response=text,
            provider=self.name,
            model_name=self.model_name,
        )