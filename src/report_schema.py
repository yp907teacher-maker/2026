"""report.json 的 JSON Schema 定義與驗證（對應 T3-3）。"""

from __future__ import annotations

import jsonschema

REPORT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": [
        "date",
        "generated_at",
        "cash",
        "holdings",
        "total_market_value",
        "total_value",
        "top10",
        "predictions",
        "watched_sectors",
        "nav_history",
    ],
    "properties": {
        "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "generated_at": {"type": "string"},
        "cash": {
            "type": "object",
            "required": ["amount", "pct_of_total"],
            "properties": {
                "amount": {"type": "number"},
                "pct_of_total": {"type": ["number", "null"]},
            },
        },
        "holdings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "stock_id",
                    "name",
                    "shares",
                    "cost_basis",
                    "current_price",
                    "market_value",
                    "pct_of_portfolio",
                    "unrealized_pnl_pct",
                    "performance",
                ],
                "properties": {
                    "stock_id": {"type": "string"},
                    "name": {"type": "string"},
                    "shares": {"type": "number"},
                    "cost_basis": {"type": "number"},
                    "current_price": {"type": "number"},
                    "market_value": {"type": "number"},
                    "pct_of_portfolio": {"type": ["number", "null"]},
                    "unrealized_pnl_pct": {"type": ["number", "null"]},
                    "pe_ratio": {"type": ["number", "null"]},
                    "performance": {
                        "type": "object",
                        "required": ["1d_pct", "1w_pct", "1m_pct"],
                        "properties": {
                            "1d_pct": {"type": ["number", "null"]},
                            "1w_pct": {"type": ["number", "null"]},
                            "1m_pct": {"type": ["number", "null"]},
                        },
                    },
                },
            },
        },
        "total_market_value": {"type": "number"},
        "total_value": {"type": "number"},
        "top10": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["stock_id", "score"],
                "properties": {
                    "stock_id": {"type": "string"},
                    "score": {"type": "number"},
                },
            },
        },
        "predictions": {
            "type": "object",
            "required": ["lookback", "top_n", "items"],
            "properties": {
                "lookback": {"type": "integer"},
                "top_n": {"type": "integer"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["stock_id", "predicted_score", "confidence"],
                        "properties": {
                            "stock_id": {"type": "string"},
                            "predicted_score": {"type": "number"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 100,
                            },
                        },
                    },
                },
            },
        },
        "watched_sectors": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["sector", "representative_stocks"],
                "properties": {
                    "sector": {"type": "string"},
                    "representative_stocks": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "today_pct_change": {"type": ["number", "null"]},
                },
            },
        },
        "nav_history": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["date", "nav"],
                "properties": {
                    "date": {"type": "string"},
                    "nav": {"type": "number"},
                    "drawdown_pct": {"type": ["number", "null"]},
                },
            },
        },
    },
}


def validate_report(report: dict) -> None:
    """驗證失敗會拋出 jsonschema.exceptions.ValidationError。"""
    jsonschema.validate(instance=report, schema=REPORT_SCHEMA)
