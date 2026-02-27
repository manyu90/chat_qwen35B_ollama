"""Tests for the sandboxed Python code execution engine."""

import os
import shutil

import pytest

from code_executor import (
    validate_code,
    execute_code,
    cleanup_old_outputs,
    OUTPUT_BASE_DIR,
    ALLOWED_MODULES,
    BLOCKED_BUILTINS,
    BLOCKED_DUNDERS,
)


# ---------------------------------------------------------------------------
# AST Validation Tests
# ---------------------------------------------------------------------------


class TestValidateCode:
    """Tests for the AST-based code validator."""

    # --- Allowed code ---

    def test_simple_print(self):
        ok, errors = validate_code("print('hello')")
        assert ok is True
        assert errors == []

    def test_math_operations(self):
        ok, errors = validate_code("x = 2 ** 100\nprint(x)")
        assert ok is True

    def test_allowed_import_math(self):
        ok, errors = validate_code("import math\nprint(math.sqrt(2))")
        assert ok is True

    def test_allowed_import_numpy(self):
        ok, errors = validate_code("import numpy as np\nprint(np.array([1,2,3]))")
        assert ok is True

    def test_allowed_import_pandas(self):
        ok, errors = validate_code("import pandas as pd")
        assert ok is True

    def test_allowed_import_matplotlib(self):
        ok, errors = validate_code("import matplotlib.pyplot as plt")
        assert ok is True

    def test_allowed_import_yfinance(self):
        ok, errors = validate_code("import yfinance as yf")
        assert ok is True

    def test_allowed_import_from(self):
        ok, errors = validate_code("from datetime import datetime")
        assert ok is True

    def test_allowed_import_scipy_submodule(self):
        ok, errors = validate_code("from scipy.stats import norm")
        assert ok is True

    def test_allowed_import_sklearn_submodule(self):
        ok, errors = validate_code("from sklearn.linear_model import LinearRegression")
        assert ok is True

    def test_allowed_import_collections(self):
        ok, errors = validate_code("from collections import Counter")
        assert ok is True

    def test_allowed_import_json(self):
        ok, errors = validate_code("import json\nprint(json.dumps({'a': 1}))")
        assert ok is True

    def test_allowed_import_requests(self):
        ok, errors = validate_code("import requests")
        assert ok is True

    def test_multiline_code(self):
        code = """
import math
import statistics

data = [1, 2, 3, 4, 5]
print(f"Mean: {statistics.mean(data)}")
print(f"Pi: {math.pi}")
"""
        ok, errors = validate_code(code)
        assert ok is True

    # --- Blocked imports ---

    def test_blocked_import_os(self):
        ok, errors = validate_code("import os")
        assert ok is False
        assert any("os" in e for e in errors)

    def test_blocked_import_sys(self):
        ok, errors = validate_code("import sys")
        assert ok is False
        assert any("sys" in e for e in errors)

    def test_blocked_import_subprocess(self):
        ok, errors = validate_code("import subprocess")
        assert ok is False

    def test_blocked_import_shutil(self):
        ok, errors = validate_code("import shutil")
        assert ok is False

    def test_blocked_import_pathlib(self):
        ok, errors = validate_code("import pathlib")
        assert ok is False

    def test_blocked_import_socket(self):
        ok, errors = validate_code("import socket")
        assert ok is False

    def test_blocked_import_http_server(self):
        ok, errors = validate_code("from http.server import HTTPServer")
        assert ok is False

    def test_blocked_import_ctypes(self):
        ok, errors = validate_code("import ctypes")
        assert ok is False

    def test_blocked_from_os(self):
        ok, errors = validate_code("from os import listdir")
        assert ok is False

    # --- Blocked builtins ---

    def test_blocked_exec(self):
        ok, errors = validate_code("exec('print(1)')")
        assert ok is False
        assert any("exec" in e for e in errors)

    def test_blocked_eval(self):
        ok, errors = validate_code("eval('1+1')")
        assert ok is False
        assert any("eval" in e for e in errors)

    def test_blocked_compile(self):
        ok, errors = validate_code("compile('x=1', '<string>', 'exec')")
        assert ok is False

    def test_blocked_open(self):
        ok, errors = validate_code("open('/etc/passwd')")
        assert ok is False
        assert any("open" in e for e in errors)

    def test_blocked___import__(self):
        ok, errors = validate_code("__import__('os')")
        assert ok is False

    def test_blocked_getattr(self):
        ok, errors = validate_code("getattr(object, '__subclasses__')")
        assert ok is False

    def test_blocked_input(self):
        ok, errors = validate_code("x = input('prompt')")
        assert ok is False

    def test_blocked_breakpoint(self):
        ok, errors = validate_code("breakpoint()")
        assert ok is False

    # --- Blocked dunder attributes ---

    def test_blocked_dunder_subclasses(self):
        ok, errors = validate_code("object.__subclasses__()")
        assert ok is False
        assert any("__subclasses__" in e for e in errors)

    def test_blocked_dunder_globals(self):
        ok, errors = validate_code("f.__globals__")
        assert ok is False

    def test_blocked_dunder_builtins(self):
        ok, errors = validate_code("x.__builtins__")
        assert ok is False

    def test_blocked_dunder_code(self):
        ok, errors = validate_code("f.__code__")
        assert ok is False

    # --- Syntax errors ---

    def test_syntax_error(self):
        ok, errors = validate_code("def foo(")
        assert ok is False
        assert any("Syntax error" in e for e in errors)

    def test_empty_code(self):
        ok, errors = validate_code("")
        assert ok is True

    # --- Multiple violations ---

    def test_multiple_violations(self):
        code = "import os\nimport subprocess\nexec('bad')"
        ok, errors = validate_code(code)
        assert ok is False
        assert len(errors) >= 3


# ---------------------------------------------------------------------------
# Code Execution Tests
# ---------------------------------------------------------------------------


class TestExecuteCode:
    """Tests for the subprocess-based code executor."""

    def test_simple_calculation(self):
        result = execute_code("print(2 ** 100)")
        assert result["success"] is True
        assert "1267650600228229401496703205376" in result["stdout"]
        assert result["errors"] == []

    def test_stdout_capture(self):
        result = execute_code("for i in range(5): print(i)")
        assert result["success"] is True
        assert "0\n1\n2\n3\n4" in result["stdout"]

    def test_stderr_on_runtime_error(self):
        result = execute_code("1/0")
        assert result["success"] is False
        assert "ZeroDivisionError" in result["stderr"]

    def test_blocked_import_rejected(self):
        result = execute_code("import os\nos.listdir('/')")
        assert result["success"] is False
        assert len(result["errors"]) > 0
        assert result["stdout"] == ""
        assert result["execution_id"] == ""

    def test_blocked_builtin_rejected(self):
        result = execute_code("eval('1+1')")
        assert result["success"] is False
        assert any("eval" in e for e in result["errors"])

    def test_execution_id_generated(self):
        result = execute_code("print('hi')")
        assert result["success"] is True
        assert len(result["execution_id"]) > 0

    def test_images_empty_without_plots(self):
        result = execute_code("print('no plots')")
        assert result["success"] is True
        assert result["images"] == []

    def test_matplotlib_plot_generates_image(self):
        code = """
import matplotlib.pyplot as plt
plt.figure()
plt.plot([1, 2, 3], [4, 5, 6])
plt.title("Test")
plt.show()
"""
        result = execute_code(code)
        assert result["success"] is True
        assert len(result["images"]) == 1
        assert result["images"][0].startswith("/api/code-output/")
        assert result["images"][0].endswith(".png")

        # Verify the file actually exists on disk
        img_path = os.path.join(
            OUTPUT_BASE_DIR,
            result["execution_id"],
            "plot_1.png",
        )
        assert os.path.isfile(img_path)

        # Cleanup
        shutil.rmtree(os.path.join(OUTPUT_BASE_DIR, result["execution_id"]), ignore_errors=True)

    def test_multiple_plots(self):
        code = """
import matplotlib.pyplot as plt

plt.figure()
plt.plot([1, 2], [3, 4])
plt.show()

plt.figure()
plt.bar([1, 2], [5, 6])
plt.show()
"""
        result = execute_code(code)
        assert result["success"] is True
        assert len(result["images"]) == 2

        # Cleanup
        shutil.rmtree(os.path.join(OUTPUT_BASE_DIR, result["execution_id"]), ignore_errors=True)

    def test_auto_save_unsaved_figures(self):
        """Figures without explicit plt.show() should still be saved."""
        code = """
import matplotlib.pyplot as plt
plt.figure()
plt.plot([1, 2, 3], [1, 4, 9])
# No plt.show() call
"""
        result = execute_code(code)
        assert result["success"] is True
        assert len(result["images"]) == 1

        # Cleanup
        shutil.rmtree(os.path.join(OUTPUT_BASE_DIR, result["execution_id"]), ignore_errors=True)

    def test_numpy_execution(self):
        code = """
import numpy as np
arr = np.array([1, 2, 3, 4, 5])
print(f"mean={arr.mean()}, std={arr.std():.4f}")
"""
        result = execute_code(code)
        assert result["success"] is True
        assert "mean=3.0" in result["stdout"]

    def test_pandas_execution(self):
        code = """
import pandas as pd
df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
print(df.describe())
"""
        result = execute_code(code)
        assert result["success"] is True
        assert "mean" in result["stdout"]

    def test_json_stdlib(self):
        code = """
import json
data = {"key": "value", "num": 42}
print(json.dumps(data, sort_keys=True))
"""
        result = execute_code(code)
        assert result["success"] is True
        assert '"key": "value"' in result["stdout"]

    def test_timeout_enforcement(self):
        """Code that runs too long should be killed."""
        code = """
import time
time.sleep(60)
"""
        result = execute_code(code)
        assert result["success"] is False
        assert "timed out" in result["stderr"].lower() or "timed out" in str(result["errors"]).lower()

    def test_temp_dir_cleaned_up(self):
        """The temporary working directory should be removed after execution."""
        import glob
        import tempfile

        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "code_exec_*")))
        execute_code("print('cleanup test')")
        after = set(glob.glob(os.path.join(tempfile.gettempdir(), "code_exec_*")))
        # No new temp dirs should remain
        assert after == before

    def test_syntax_error_rejected(self):
        result = execute_code("def foo(")
        assert result["success"] is False
        assert any("Syntax error" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Cleanup Tests
# ---------------------------------------------------------------------------


class TestCleanupOldOutputs:

    def test_cleanup_removes_old_dirs(self):
        """Directories older than max_age should be removed."""
        test_dir = os.path.join(OUTPUT_BASE_DIR, "test-old-cleanup")
        os.makedirs(test_dir, exist_ok=True)

        # Set mtime to 2 hours ago
        old_time = os.path.getmtime(test_dir) - 7200
        os.utime(test_dir, (old_time, old_time))

        cleanup_old_outputs(max_age_hours=1)
        assert not os.path.exists(test_dir)

    def test_cleanup_keeps_recent_dirs(self):
        """Recent directories should not be removed."""
        test_dir = os.path.join(OUTPUT_BASE_DIR, "test-recent-cleanup")
        os.makedirs(test_dir, exist_ok=True)

        cleanup_old_outputs(max_age_hours=1)
        assert os.path.exists(test_dir)

        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)
