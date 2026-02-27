"""
Sandboxed Python code execution engine.

Security model:
- AST validation: whitelist imports, block dangerous builtins/attributes
- subprocess isolation: 30s timeout, stdin closed, stdout/stderr capped
- Temp directory: each execution gets its own isolated directory
- Network: allowed (yfinance needs it), but server-side modules blocked
"""

import ast
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

logger = logging.getLogger(__name__)

OUTPUT_BASE_DIR = os.path.join(os.path.dirname(__file__), "code_output")

# Modules the LLM is allowed to import
ALLOWED_MODULES = {
    # Math & science
    "math", "cmath", "decimal", "fractions", "statistics", "random",
    # Data
    "numpy", "np", "pandas", "pd",
    # Plotting
    "matplotlib", "matplotlib.pyplot", "matplotlib.figure", "matplotlib.dates",
    "mpl_toolkits", "mpl_toolkits.mplot3d",
    "seaborn", "sns",
    # Finance
    "yfinance", "yf",
    # ML / scipy
    "scipy", "scipy.stats", "scipy.optimize", "scipy.interpolate",
    "scipy.signal", "scipy.linalg", "scipy.integrate",
    "sklearn", "sklearn.linear_model", "sklearn.cluster", "sklearn.preprocessing",
    "sklearn.model_selection", "sklearn.metrics", "sklearn.ensemble",
    "sklearn.tree", "sklearn.neighbors", "sklearn.svm",
    "sklearn.decomposition", "sklearn.pipeline",
    # Web requests (yfinance uses this internally; also useful standalone)
    "requests",
    # Standard library safe modules
    "datetime", "json", "csv", "collections", "itertools", "functools",
    "re", "string", "textwrap", "operator", "copy", "pprint",
    "typing", "dataclasses", "enum", "abc",
    "io", "base64", "hashlib", "hmac",
    "time", "calendar",
}

# Builtins that must never be called
BLOCKED_BUILTINS = {
    "exec", "eval", "compile", "__import__", "globals", "locals",
    "getattr", "setattr", "delattr", "vars",
    "open",  # no file I/O
    "input",  # no stdin
    "breakpoint",
    "exit", "quit",
}

# Dunder attributes that indicate introspection / escape attempts
BLOCKED_DUNDERS = {
    "__subclasses__", "__bases__", "__mro__", "__class__",
    "__globals__", "__code__", "__builtins__",
    "__import__", "__loader__", "__spec__",
}


class CodeValidator(ast.NodeVisitor):
    """Walk AST to enforce the security policy."""

    def __init__(self):
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self._check_module(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            self._check_module(node.module, node.lineno)
        self.generic_visit(node)

    def _check_module(self, module_name: str, lineno: int):
        # Allow exact match or parent package match
        top = module_name.split(".")[0]
        if module_name not in ALLOWED_MODULES and top not in ALLOWED_MODULES:
            self.errors.append(
                f"Line {lineno}: import of '{module_name}' is not allowed. "
                f"Allowed modules: {', '.join(sorted(ALLOWED_MODULES))}"
            )

    def visit_Call(self, node: ast.Call):
        # Block dangerous builtin calls
        if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_BUILTINS:
            self.errors.append(
                f"Line {node.lineno}: call to '{node.func.id}()' is not allowed."
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in BLOCKED_DUNDERS:
            self.errors.append(
                f"Line {node.lineno}: access to '{node.attr}' is not allowed."
            )
        self.generic_visit(node)


def validate_code(code: str) -> tuple[bool, list[str]]:
    """Parse and validate code. Returns (is_valid, error_list)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"Syntax error: {e}"]

    validator = CodeValidator()
    validator.visit(tree)

    if validator.errors:
        return False, validator.errors
    return True, []


# Max output sizes
MAX_STDOUT = 50_000   # 50 KB
MAX_STDERR = 10_000   # 10 KB


def execute_code(code: str) -> dict:
    """
    Validate and execute Python code in a subprocess.

    Returns dict with: success, stdout, stderr, images, execution_id, errors
    """
    # Validate first
    is_valid, errors = validate_code(code)
    if not is_valid:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "images": [],
            "execution_id": "",
            "errors": errors,
        }

    execution_id = str(uuid.uuid4())
    output_dir = os.path.join(OUTPUT_BASE_DIR, execution_id)
    os.makedirs(output_dir, exist_ok=True)

    # Create a temp directory for the script to run in
    work_dir = tempfile.mkdtemp(prefix="code_exec_")

    # Build wrapper script that:
    # 1. Sets matplotlib to non-interactive backend
    # 2. Patches plt.show() to save figures as PNGs
    # 3. Runs the user code
    wrapper = f'''\
import sys
import os

# Set up matplotlib if available (non-interactive backend, patched show)
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _output_dir = {output_dir!r}
    _plot_counter = [0]

    _original_show = plt.show

    def _patched_show(*args, **kwargs):
        for fig_num in plt.get_fignums():
            fig = plt.figure(fig_num)
            _plot_counter[0] += 1
            path = os.path.join(_output_dir, f"plot_{{_plot_counter[0]}}.png")
            fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close("all")

    plt.show = _patched_show
    _has_matplotlib = True
except ImportError:
    _has_matplotlib = False

# --- User code below ---
{code}

# Auto-save any remaining open figures
if _has_matplotlib:
    import matplotlib.pyplot as plt
    if plt.get_fignums():
        _patched_show()
'''

    script_path = os.path.join(work_dir, "script.py")
    with open(script_path, "w") as f:
        f.write(wrapper)

    try:
        result = subprocess.run(
            [sys.executable if hasattr(sys, "executable") else "python3", script_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=work_dir,
            stdin=subprocess.DEVNULL,
            env={
                **os.environ,
                "MPLBACKEND": "Agg",
            },
        )

        stdout = result.stdout[:MAX_STDOUT]
        stderr = result.stderr[:MAX_STDERR]

        # Scan for output images
        images = []
        if os.path.isdir(output_dir):
            for fname in sorted(os.listdir(output_dir)):
                if fname.endswith(".png"):
                    images.append(f"/api/code-output/{execution_id}/{fname}")

        return {
            "success": result.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "images": images,
            "execution_id": execution_id,
            "errors": [],
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out after 30 seconds.",
            "images": [],
            "execution_id": execution_id,
            "errors": ["Execution timed out after 30 seconds."],
        }
    except Exception as e:
        logger.exception("Code execution error")
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "images": [],
            "execution_id": execution_id,
            "errors": [str(e)],
        }
    finally:
        # Clean up the temporary work directory
        shutil.rmtree(work_dir, ignore_errors=True)
        # Clean up output dir if empty (no images produced)
        if os.path.isdir(output_dir) and not os.listdir(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)


def cleanup_old_outputs(max_age_hours: int = 1):
    """Remove output directories older than max_age_hours."""
    if not os.path.isdir(OUTPUT_BASE_DIR):
        return

    cutoff = time.time() - (max_age_hours * 3600)
    for name in os.listdir(OUTPUT_BASE_DIR):
        path = os.path.join(OUTPUT_BASE_DIR, name)
        if os.path.isdir(path):
            try:
                if os.path.getmtime(path) < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
                    logger.info(f"Cleaned up old code output: {name}")
            except OSError:
                pass
