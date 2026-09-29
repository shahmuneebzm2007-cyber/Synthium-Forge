"""
Export Engine — CSV, JSON, SQL, SQLite, Parquet, Excel, pytest fixtures.

Formula-injection guard on CSV/Excel exports.
SHA-256 hash for every artifact.
"""
from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from app.core.seeding import file_sha256, content_sha256
from app.validation.relational import schema_to_ddl


FORMULA_PREFIX_CHARS = {"=", "+", "-", "@", "\t", "\r"}


def _guard_formula(val) -> str:
    """Prefix cells that look like spreadsheet formulas with a tab."""
    if not isinstance(val, str):
        return str(val) if val is not None else ""
    if val and val[0] in FORMULA_PREFIX_CHARS:
        return "\t" + val
    return val


def _safe_df(df: pd.DataFrame) -> pd.DataFrame:
    """Apply formula injection guard to all string columns."""
    df = df.copy()
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).map(_guard_formula)
    return df


class ExportEngine:
    """Unified export to all supported formats."""

    def __init__(self, output_dir: str = "./exports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts: list[dict] = []

    def export_csv(self, df: pd.DataFrame, name: str,
                   bom: bool = True) -> dict:
        """Export to CSV with formula-injection guard."""
        safe = _safe_df(df)
        path = self.output_dir / f"{name}.csv"
        encoding = "utf-8-sig" if bom else "utf-8"
        safe.to_csv(path, index=False, encoding=encoding)
        artifact = self._record(name, "csv", path)
        return artifact

    def export_json(self, df: pd.DataFrame, name: str) -> dict:
        """Export to JSON (array of objects, pretty-printed)."""
        path = self.output_dir / f"{name}.json"
        # Handle numpy/pandas types
        records = json.loads(df.to_json(orient="records", date_format="iso", default_handler=str))
        path.write_text(json.dumps(records, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return self._record(name, "json", path)

    def export_jsonl(self, df: pd.DataFrame, name: str) -> dict:
        """Export to JSON Lines (one object per line)."""
        path = self.output_dir / f"{name}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for _, row in df.iterrows():
                f.write(json.dumps(row.to_dict(), default=str, ensure_ascii=False) + "\n")
        return self._record(name, "jsonl", path)

    def export_parquet(self, df: pd.DataFrame, name: str) -> dict:
        """Export to Parquet via pyarrow."""
        path = self.output_dir / f"{name}.parquet"
        df.to_parquet(path, index=False, engine="pyarrow")
        return self._record(name, "parquet", path)

    def export_excel(self, df: pd.DataFrame, name: str) -> dict:
        """Export to Excel with auto-column-widths."""
        safe = _safe_df(df)
        path = self.output_dir / f"{name}.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            safe.to_excel(writer, index=False, sheet_name="Data")
            ws = writer.sheets["Data"]
            for col_idx, col_name in enumerate(safe.columns, 1):
                max_len = max(
                    safe[col_name].astype(str).str.len().max(),
                    len(str(col_name))
                ) + 2
                ws.column_dimensions[ws.cell(1, col_idx).column_letter].width = min(max_len, 50)
        return self._record(name, "xlsx", path)

    def export_sql_dump(self, tables: dict[str, pd.DataFrame],
                        schema_dict: dict | None = None,
                        dialect: str = "sqlite",
                        name: str = "dump") -> dict:
        """Export DDL + INSERT statements."""
        path = self.output_dir / f"{name}.sql"
        lines = []

        # DDL
        if schema_dict:
            ddl = schema_to_ddl(schema_dict)
            lines.append(ddl)
        else:
            for tname, df in tables.items():
                cols = ", ".join(f"{c} TEXT" for c in df.columns)
                lines.append(f"CREATE TABLE IF NOT EXISTS {tname} ({cols});")

        lines.append("")

        # INSERTs
        for tname, df in tables.items():
            for _, row in df.iterrows():
                vals = []
                for v in row.values:
                    if pd.isna(v):
                        vals.append("NULL")
                    elif isinstance(v, (int, float, np.integer, np.floating)):
                        vals.append(str(v))
                    else:
                        escaped = str(v).replace("'", "''")
                        vals.append(f"'{escaped}'")
                lines.append(f"INSERT INTO {tname} VALUES ({', '.join(vals)});")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        return self._record(name, "sql", path)

    def export_sqlite(self, tables: dict[str, pd.DataFrame],
                      schema_dict: dict | None = None,
                      name: str = "database") -> dict:
        """Export as a ready-to-open SQLite file."""
        path = self.output_dir / f"{name}.sqlite"
        con = sqlite3.connect(str(path))
        con.execute("PRAGMA foreign_keys = ON")

        if schema_dict:
            ddl = schema_to_ddl(schema_dict)
            con.executescript(ddl)
            for tname in ["customers", "products", "orders", "order_items"]:
                if tname in tables:
                    tables[tname].to_sql(tname, con, if_exists="append", index=False)
            for tname, df in tables.items():
                if tname not in ["customers", "products", "orders", "order_items"]:
                    df.to_sql(tname, con, if_exists="replace", index=False)
        else:
            for tname, df in tables.items():
                df.to_sql(tname, con, if_exists="replace", index=False)

        con.commit()
        con.close()
        return self._record(name, "sqlite", path)

    def export_pytest_fixtures(self, tables: dict[str, pd.DataFrame],
                                name: str = "fixtures") -> dict:
        """Generate a Python file with pytest fixtures."""
        path = self.output_dir / f"{name}.py"
        lines = [
            '"""Auto-generated pytest fixtures from SynthGen AI."""',
            "import pytest",
            "import pandas as pd",
            "",
        ]

        for tname, df in tables.items():
            records = df.head(20).to_dict("records")
            lines.append(f"@pytest.fixture")
            lines.append(f"def {tname}_df():")
            lines.append(f'    """Sample {tname} data ({len(df)} rows, showing first 20)."""')
            lines.append(f"    data = {json.dumps(records, indent=8, default=str)}")
            lines.append(f"    return pd.DataFrame(data)")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        return self._record(name, "py", path)

    def export_all(self, tables: dict[str, pd.DataFrame],
                   formats: list[str] | None = None,
                   schema_dict: dict | None = None) -> list[dict]:
        """Export all tables in all requested formats."""
        formats = formats or ["csv", "json"]
        results = []

        for tname, df in tables.items():
            for fmt in formats:
                if fmt == "csv":
                    results.append(self.export_csv(df, tname))
                elif fmt == "json":
                    results.append(self.export_json(df, tname))
                elif fmt == "jsonl":
                    results.append(self.export_jsonl(df, tname))
                elif fmt == "parquet":
                    results.append(self.export_parquet(df, tname))
                elif fmt == "excel":
                    results.append(self.export_excel(df, tname))

        if "sql" in (formats or []):
            results.append(self.export_sql_dump(tables, schema_dict))
        if "sqlite" in (formats or []):
            results.append(self.export_sqlite(tables, schema_dict))
        if "pytest" in (formats or []):
            results.append(self.export_pytest_fixtures(tables))

        return results

    def _record(self, name: str, fmt: str, path: Path) -> dict:
        stat = path.stat()
        sha = file_sha256(str(path))
        record = {
            "name": f"{name}.{fmt}",
            "format": fmt,
            "size_bytes": stat.st_size,
            "sha256": sha,
            "path": str(path),
        }
        self.artifacts.append(record)
        return record
