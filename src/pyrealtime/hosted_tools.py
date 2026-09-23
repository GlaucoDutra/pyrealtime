"""Reusable server-side tools backed directly by the OpenAI API."""

from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Any, Mapping, Sequence

import httpx

from .exceptions import UpstreamError
from .principal import Principal
from .tools import ToolRegistry


class OpenAIHostedTools:
    """Register web, file, image, and general model tools without app endpoints."""

    def __init__(
        self,
        *,
        api_key: str,
        response_model: str = "gpt-5-mini",
        image_model: str = "gpt-image-2.5-flare",
        vector_store_ids: Sequence[str] = (),
        base_url: str = "https://api.openai.com",
        timeout: float = 120.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key cannot be empty")
        self.api_key = api_key.strip()
        self.response_model = response_model.strip()
        self.image_model = image_model.strip()
        self.vector_store_ids = tuple(value.strip() for value in vector_store_ids if value.strip())
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.http_client = http_client

    def register(self, registry: ToolRegistry) -> None:
        @registry.tool(
            name="web_search",
            description="Search the live web for current external information and return a sourced answer.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 4000}},
                "required": ["query"],
                "additionalProperties": False,
            },
        )
        async def web_search(arguments: Mapping[str, Any], principal: Principal) -> dict[str, Any]:
            query = self._required_text(arguments, "query", maximum=4000)
            return await self._response(
                input_text=query,
                tools=[{"type": "web_search", "search_context_size": "low"}],
                include=["web_search_call.action.sources"],
                principal=principal,
            )

        @registry.tool(
            name="backend_openai_call",
            description="Run a private server-side OpenAI text task for classification, planning, or extraction.",
            parameters={
                "type": "object",
                "properties": {
                    "input": {"type": "string", "minLength": 1, "maxLength": 20000},
                    "instructions": {"type": "string", "minLength": 1, "maxLength": 512},
                },
                "required": ["input", "instructions"],
                "additionalProperties": False,
            },
        )
        async def backend_openai_call(arguments: Mapping[str, Any], principal: Principal) -> dict[str, Any]:
            input_text = self._required_text(arguments, "input", maximum=20000)
            instructions = self._required_text(arguments, "instructions", maximum=512)
            return await self._response(
                input_text=input_text,
                instructions=instructions,
                principal=principal,
            )

        @registry.tool(
            name="generate_image",
            description="Generate an image only when the user explicitly asks for one.",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "minLength": 1, "maxLength": 32000},
                    "size": {"type": "string", "enum": ["auto", "1024x1024", "1536x1024", "1024x1536"]},
                    "quality": {"type": "string", "enum": ["low", "medium", "high", "auto"]},
                    "output_format": {"type": "string", "enum": ["png", "jpeg", "webp"]},
                    "background": {"type": "string", "enum": ["auto", "opaque", "transparent"]},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        )
        async def generate_image(arguments: Mapping[str, Any], principal: Principal) -> dict[str, Any]:
            prompt = self._required_text(arguments, "prompt", maximum=32000)
            output_format = self._choice(arguments, "output_format", {"png", "jpeg", "webp"}, "png")
            background = self._choice(arguments, "background", {"auto", "opaque", "transparent"}, "auto")
            if background == "transparent" and output_format == "jpeg":
                raise ValueError("Transparent images require png or webp output")
            payload = await self._post(
                "/v1/images/generations",
                {
                    "model": self.image_model,
                    "prompt": prompt,
                    "size": self._choice(arguments, "size", {"auto", "1024x1024", "1536x1024", "1024x1536"}, "1024x1024"),
                    "quality": self._choice(arguments, "quality", {"low", "medium", "high", "auto"}, "low"),
                    "output_format": output_format,
                    "background": background,
                    "n": 1,
                },
                principal,
            )
            data = payload.get("data") if isinstance(payload, dict) else None
            image = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
            encoded = image.get("b64_json")
            if not isinstance(encoded, str) or not encoded:
                raise UpstreamError("OpenAI returned no generated image")
            try:
                base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise UpstreamError("OpenAI returned invalid generated image data") from exc
            return {
                "ok": True,
                "image_data_uri": f"data:image/{output_format};base64,{encoded}",
                "revised_prompt": image.get("revised_prompt"),
            }

        if self.vector_store_ids:
            @registry.tool(
                name="file_search",
                description="Search the configured private knowledge base for information relevant to the query.",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 4000}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            )
            async def file_search(arguments: Mapping[str, Any], principal: Principal) -> dict[str, Any]:
                query = self._required_text(arguments, "query", maximum=4000)
                return await self._response(
                    input_text=query,
                    tools=[{
                        "type": "file_search",
                        "vector_store_ids": list(self.vector_store_ids),
                        "max_num_results": 5,
                    }],
                    include=["file_search_call.results"],
                    principal=principal,
                )

    async def _response(
        self,
        *,
        input_text: str,
        principal: Principal,
        instructions: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.response_model,
            "input": input_text,
            "store": False,
        }
        if instructions:
            body["instructions"] = instructions
        if tools:
            body["tools"] = tools
        if include:
            body["include"] = include
        payload = await self._post("/v1/responses", body, principal)
        output_text = payload.get("output_text") if isinstance(payload, dict) else None
        if not isinstance(output_text, str) or not output_text.strip():
            output_text = self._extract_output_text(payload)
        return {
            "ok": True,
            "output_text": output_text,
            "response_id": payload.get("id") if isinstance(payload, dict) else None,
            "citations": self._extract_citations(payload),
        }

    async def _post(self, path: str, body: dict[str, Any], principal: Principal) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "OpenAI-Safety-Identifier": hashlib.sha256(principal.id.encode("utf-8")).hexdigest(),
        }
        if self.http_client is not None:
            response = await self.http_client.post(f"{self.base_url}{path}", headers=headers, json=body)
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}{path}", headers=headers, json=body)
        if not response.is_success:
            raise UpstreamError(
                "OpenAI rejected the hosted tool request",
                status_code=response.status_code,
                response_body=response.text[:1000],
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise UpstreamError("OpenAI returned an invalid hosted tool response")
        return payload

    @staticmethod
    def _extract_output_text(payload: Any) -> str:
        parts: list[str] = []
        for item in payload.get("output", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str):
                        parts.append(text)
        return "\n".join(parts).strip()

    @staticmethod
    def _extract_citations(payload: Any) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for item in payload.get("output", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                for annotation in content.get("annotations", []):
                    if not isinstance(annotation, dict):
                        continue
                    citation = {
                        key: annotation[key]
                        for key in ("type", "title", "url", "filename", "file_id")
                        if annotation.get(key) is not None
                    }
                    marker = tuple(sorted(citation.items()))
                    if citation and marker not in seen:
                        seen.add(marker)
                        citations.append(citation)
        return citations

    @staticmethod
    def _required_text(arguments: Mapping[str, Any], name: str, *, maximum: int) -> str:
        value = str(arguments.get(name, "")).strip()
        if not value:
            raise ValueError(f"{name} is required")
        if len(value) > maximum:
            raise ValueError(f"{name} cannot exceed {maximum} characters")
        return value

    @staticmethod
    def _choice(arguments: Mapping[str, Any], name: str, allowed: set[str], default: str) -> str:
        value = str(arguments.get(name, default)).strip() or default
        if value not in allowed:
            raise ValueError(f"Unsupported {name}: {value}")
        return value
