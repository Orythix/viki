"""
Data analysis skill: load CSV/Excel, describe stats, visualize (charts), optional LLM summary.
Manus-style "process datasets, identify patterns, generate reports, create visualizations."
"""
import os
import io
from typing import Dict, Any, Optional

from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger
from viki.core.utils.path_sandbox import validate_output_path


class DataAnalysisSkill(BaseSkill):
    def __init__(self, controller=None):
        self._controller = controller

    @property
    def name(self) -> str:
        return "data_analysis"

    @property
    def description(self) -> str:
        return (
            "Analyze data from CSV or Excel files. Actions: analyze(file_path=..., question=...), "
            "describe(file_path=...), visualize(file_path=..., chart_type=bar|line|scatter, output_path=...). "
            "Optional: csv_content= inline CSV string instead of file_path."
        )

    def _load_data(self, file_path: Optional[str], csv_content: Optional[str]):
        import pandas as pd
        if csv_content:
            return pd.read_csv(io.StringIO(csv_content))
        if not file_path or not os.path.isfile(file_path):
            return None
        low = (file_path or "").lower()
        if low.endswith(".xlsx") or low.endswith(".xls"):
            return pd.read_excel(file_path, engine="openpyxl")
        return pd.read_csv(file_path)

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action", "analyze")
        file_path = params.get("file_path") or params.get("file")
        csv_content = params.get("csv_content")
        if not file_path and not csv_content:
            return "Provide file_path= (path to CSV/XLSX) or csv_content= (inline CSV string)."

        if file_path:
            ok, path_or_err = validate_output_path(file_path, controller=self._controller)
            if not ok:
                return path_or_err
            file_path = path_or_err

        try:
            import pandas as pd
        except ImportError:
            return "Install pandas: pip install pandas openpyxl"

        df = self._load_data(file_path, csv_content)
        if df is None:
            return f"Could not load data from {file_path or 'csv_content'}."

        if action == "describe":
            desc = df.describe(include="all").to_string()
            return f"Describe:\n{desc}\n\nShape: {df.shape[0]} rows, {df.shape[1]} columns."

        if action == "visualize":
            chart_type = (params.get("chart_type") or "bar").lower()
            output_path = params.get("output_path") or params.get("output")
            if not output_path:
                return "For visualize, provide output_path= to save the chart."
            ok, resolved = validate_output_path(output_path, controller=self._controller)
            if not ok:
                return resolved
            output_path = resolved
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
            except ImportError:
                return "Install matplotlib for charts: pip install matplotlib"
            try:
                plt.figure(figsize=(8, 5))
                numeric = df.select_dtypes(include=["number"])
                if numeric.empty:
                    return "No numeric columns to plot. Use describe for summary."
                if chart_type == "bar":
                    numeric.iloc[:10].plot(kind="bar", ax=plt.gca())
                elif chart_type == "line":
                    numeric.iloc[:50].plot(kind="line", ax=plt.gca())
                elif chart_type == "scatter" and numeric.shape[1] >= 2:
                    plt.scatter(numeric.iloc[:, 0], numeric.iloc[:, 1])
                    plt.xlabel(numeric.columns[0])
                    plt.ylabel(numeric.columns[1])
                else:
                    numeric.mean().plot(kind="bar", ax=plt.gca())
                plt.tight_layout()
                plt.savefig(output_path)
                plt.close()
                return f"Chart saved to {output_path}."
            except Exception as e:
                viki_logger.warning(f"Visualize failed: {e}")
                return f"Visualization error: {e}"

        # analyze (default): stats + optional question to LLM
        desc = df.describe(include="all").to_string()
        summary = f"Shape: {df.shape[0]} rows, {df.shape[1]} columns.\nDescribe:\n{desc}"
        question = params.get("question")
        if question and self._controller and hasattr(self._controller, "model_router"):
            try:
                model = self._controller.model_router.get_model(capabilities=["general"])
                messages = [{"role": "user", "content": f"Given this data summary:\n{summary[:4000]}\n\nUser question: {question}\nAnswer briefly."}]
                reply = await model.chat(messages, temperature=0.3)
                if reply and isinstance(reply, str):
                    summary += f"\n\nAnswer to '{question}': {reply}"
            except Exception as e:
                viki_logger.debug(f"LLM summary: {e}")
        return summary
