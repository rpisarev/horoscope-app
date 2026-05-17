from __future__ import annotations

from .base import ProviderRequest, ProviderResult


class StubHoroscopeProvider:
    name = "stub"
    model_name = "stub"

    def generate(self, request: ProviderRequest) -> ProviderResult:
        rendered_prompt = self._render_prompt(request)
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
            request_payload={
                **request.to_payload(),
                "rendered_prompt": rendered_prompt,
            },
            response_payload=response_payload,
            raw_response=text,
            provider=self.name,
            model_name=self.model_name,
        )

    def _render_prompt(self, request: ProviderRequest) -> str:
        prompt_version = request.prompt_version
        if not prompt_version:
            return (
                "Составь короткий ежедневный прогноз на дату "
                f"{request.target_date.isoformat()}. "
                "Обращайся к читателю только напрямую: Вы, Вам, Вас. "
                "Не упоминай знак зодиака."
            )

        return prompt_version.user_prompt_template.format(
            date=request.target_date.isoformat(),
            locale=request.locale,
            forecast_type=request.forecast_type,
        )