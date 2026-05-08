"""
AWS console skill (dynamic / Phase 4).

Lightweight, read-only AWS console wrapper. Uses boto3 if installed;
otherwise reports a clear error explaining the missing dependency. Restricted
to enumerate-style operations (list_*, describe_*, get_*) so this skill can
ship in the "safe_utilities" tier. Write/destructive AWS calls require an
operator-supplied capability promotion.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from viki.skills.base import BaseSkill


class AwsConsoleSkill(BaseSkill):
    """Read-only AWS API caller via boto3."""

    def __init__(self, controller=None):
        self.controller = controller

    @property
    def name(self) -> str:
        return "aws_console"

    @property
    def description(self) -> str:
        return (
            "Read-only AWS console queries via boto3 with pagination. "
            "Params: service (str), operation (str, must start with 'list_'/'describe_'/'get_'), "
            "kwargs (dict, optional), region (str, optional), page_size (int, optional), "
            "max_pages (int, optional, default 5), profile (str, optional)."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "operation": {"type": "string"},
                "kwargs": {"type": "object"},
                "region": {"type": "string"},
                "page_size": {"type": "integer"},
                "max_pages": {"type": "integer"},
                "profile": {"type": "string"},
            },
            "required": ["service", "operation"],
        }

    @property
    def safety_tier(self) -> str:
        return "safe"

    async def execute(self, params: Dict[str, Any]) -> str:
        service = (params.get("service") or "").strip()
        operation = (params.get("operation") or "").strip()
        kwargs = params.get("kwargs") or {}
        region = params.get("region")
        profile = params.get("profile")
        try:
            page_size = int(params.get("page_size", 0)) or None
        except (TypeError, ValueError):
            page_size = None
        try:
            max_pages = max(1, min(int(params.get("max_pages", 5)), 50))
        except (TypeError, ValueError):
            max_pages = 5

        if not service or not operation:
            return "Error: 'service' and 'operation' are required."
        if not (
            operation.startswith("list_")
            or operation.startswith("describe_")
            or operation.startswith("get_")
        ):
            return "Error: only read-only operations (list_/describe_/get_) are allowed."

        try:
            import boto3  # type: ignore
        except Exception:
            return "Error: boto3 not installed; pip install boto3 to enable aws_console."

        try:
            session = boto3.session.Session(
                profile_name=profile,
                region_name=region,
            ) if (profile or region) else boto3.session.Session()
            client = session.client(service)
            if client.can_paginate(operation):
                pcfg = {"MaxItems": page_size * max_pages} if page_size else {"MaxItems": 1000}
                if page_size:
                    pcfg["PageSize"] = page_size
                paginator = client.get_paginator(operation)
                pages = []
                for i, page in enumerate(paginator.paginate(PaginationConfig=pcfg, **kwargs)):
                    page.pop("ResponseMetadata", None)
                    pages.append(page)
                    if i + 1 >= max_pages:
                        break
                return json.dumps({"pages": pages, "page_count": len(pages)}, default=str)[:120_000]
            method = getattr(client, operation, None)
            if method is None:
                return f"Error: {service}.{operation} not found."
            response = method(**kwargs)
            response.pop("ResponseMetadata", None)
            return json.dumps(response, default=str)[:60_000]
        except Exception as e:
            return f"aws_console error: {e}"
