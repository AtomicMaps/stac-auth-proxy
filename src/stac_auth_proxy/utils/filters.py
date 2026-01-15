"""Utility functions."""

import json
import logging
from typing import Optional
from urllib.parse import parse_qs

from cql2 import Expr
# Use pygeofilter to parse CQL2 text, then convert to cql2 Expr
from pygeofilter.parsers.cql2_text import parse as parse_cql2_text
from pygeofilter.backends.cql2_json import to_cql2

logger = logging.getLogger(__name__)


def append_qs_filter(qs: str, filter: Expr, filter_lang: Optional[str] = None) -> bytes:
    """Insert a filter expression into a query string. If a filter already exists, combine them."""
    qs_dict = {k: v[0] for k, v in parse_qs(qs).items()}
    new_qs_dict = append_body_filter(
        qs_dict, filter, filter_lang or qs_dict.get("filter-lang", "cql2-text")
    )
    return dict_to_query_string(new_qs_dict).encode("utf-8")


def append_body_filter(
    body: dict, filter: Expr, filter_lang: Optional[str] = None
) -> dict:
    """Insert a filter expression into a request body. If a filter already exists, combine them."""
    cur_filter = body.get("filter")
    filter_lang = filter_lang or body.get("filter-lang", "cql2-json")
    if cur_filter:
        filter = filter + Expr(cur_filter)
    return {
        **body,
        "filter": filter.to_text() if filter_lang == "cql2-text" else filter.to_json(),
        "filter-lang": filter_lang,
    }

def append_body_filter(
    body: dict, filter: Expr, filter_lang: Optional[str] = None
) -> dict:
    """Insert a filter expression into a request body. If a filter already exists, combine them."""
    cur_filter = body.get("filter")
    filter_lang = filter_lang or body.get("filter-lang", "cql2-json")
    
    if cur_filter:
        if isinstance(cur_filter, str):
            # Parse the text and convert to JSON
            parsed_ast = parse_cql2_text(cur_filter)
            cur_filter_json = to_cql2(parsed_ast)

            cur_filter_expr = Expr(cur_filter_json)
        else:
            cur_filter_expr = Expr(cur_filter)
        
        # Combine the filters
        filter = filter + cur_filter_expr
    
    return {
        **body,
        "filter": filter.to_text() if filter_lang == "cql2-text" else filter.to_json(),
        "filter-lang": filter_lang,
    }


def dict_to_query_string(params: dict) -> str:
    """
    Convert a dictionary to a query string. Dict values are converted to JSON strings,
    unlike the default behavior of urllib.parse.urlencode.
    """
    parts = []
    for key, val in params.items():
        if isinstance(val, (dict, list)):
            val = json.dumps(val, separators=(",", ":"))
        parts.append(f"{key}={val}")
    return "&".join(parts)
