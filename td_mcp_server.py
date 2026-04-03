#!/usr/bin/env python3
"""
TouchDesigner MCP Server
========================
A FastMCP server that bridges Claude to a live TouchDesigner instance.
Communication happens over WebSocket — TD runs a WebSocket Server DAT,
and this server sends Python commands to be exec'd inside TD's environment.

Requirements (install outside TD):
    pip install mcp[cli] websockets

Usage:
    python td_mcp_server.py

Configure in Claude Desktop / claude_desktop_config.json:
    {
        "mcpServers": {
            "touchdesigner_mcp": {
                "command": "python",
                "args": ["/path/to/td_mcp_server.py"]
            }
        }
    }
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

import websockets

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TD_WS_HOST = "localhost"
TD_WS_PORT = 9980  # Must match the WebSocket Server DAT port inside TD

# ---------------------------------------------------------------------------
# WebSocket Client — persistent connection to TD
# ---------------------------------------------------------------------------

class TDConnection:
    """Manages a single WebSocket connection to the TouchDesigner bridge."""

    def __init__(self):
        self.ws = None
        self._lock = asyncio.Lock()

    async def connect(self):
        try:
            self.ws = await websockets.connect(
                f"ws://{TD_WS_HOST}:{TD_WS_PORT}",
                ping_interval=20,
                ping_timeout=10,
            )
        except Exception as e:
            self.ws = None
            raise ConnectionError(
                f"Cannot connect to TouchDesigner at ws://{TD_WS_HOST}:{TD_WS_PORT}. "
                f"Make sure TD is running and the bridge component is loaded. Error: {e}"
            )

    async def send_command(self, python_code: str, timeout: float = 30.0) -> dict:
        """Send a Python command to TD and wait for the JSON response."""
        async with self._lock:
            for attempt in range(2):
                try:
                    if self.ws is None:
                        await self.connect()
                    request_id = str(uuid.uuid4())[:8]
                    payload = json.dumps({"id": request_id, "code": python_code})
                    await self.ws.send(payload)
                    raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
                    return json.loads(raw)
                except asyncio.TimeoutError:
                    return {"id": request_id, "status": "error",
                            "result": "Timeout waiting for TouchDesigner response."}
                except Exception:
                    self.ws = None
                    if attempt == 1:
                        return {"id": "?", "status": "error",
                                "result": "Lost connection to TD and reconnect failed."}

    async def close(self):
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass

# ---------------------------------------------------------------------------
# Lifespan — keep a persistent TD connection
# ---------------------------------------------------------------------------

@asynccontextmanager
async def app_lifespan(server):
    td = TDConnection()
    try:
        await td.connect()
    except ConnectionError:
        pass  # Tools will retry on first call
    yield {"td": td}
    await td.close()


# ---------------------------------------------------------------------------
# FastMCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("touchdesigner_mcp", lifespan=app_lifespan)


def _get_td(ctx) -> TDConnection:
    return ctx.request_context.lifespan_context["td"]


# ---------------------------------------------------------------------------
# Pydantic Input Models
# ---------------------------------------------------------------------------

class ExecPythonInput(BaseModel):
    """Execute arbitrary Python code inside TouchDesigner."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    code: str = Field(..., description=(
        "Python code to execute in TD's environment. "
        "Has access to op(), parent(), root, me, etc. "
        "The last expression's repr is returned as the result."
    ))
    timeout: float = Field(default=30.0, description="Max seconds to wait", ge=1, le=120)


class CreateOpInput(BaseModel):
    """Create an operator inside a target component."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    parent_path: str = Field(
        default="/project1",
        description="Path to the parent COMP where the new OP will be created (e.g. '/project1')"
    )
    op_type: str = Field(..., description=(
        "TD operator type string, e.g. 'noiseTOP', 'waveCHOP', 'baseCOMP', "
        "'compositeTOP', 'textDAT', 'audiofileinCHOP', 'glslTOP', etc."
    ))
    name: Optional[str] = Field(default=None, description="Optional name for the new operator")


class SetParamsInput(BaseModel):
    """Set one or more parameters on an existing operator."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    op_path: str = Field(..., description="Path to the operator, e.g. '/project1/noise1'")
    params: Dict[str, Any] = Field(..., description=(
        "Dictionary of parameter_name: value pairs. "
        "e.g. {'resolutionw': 1920, 'resolutionh': 1080, 'type': 'random'}"
    ))


class ConnectOpsInput(BaseModel):
    """Wire the output of one OP to the input of another."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    from_op: str = Field(..., description="Path to the source operator (output)")
    to_op: str = Field(..., description="Path to the destination operator (input)")
    from_output: int = Field(default=0, description="Output connector index on the source", ge=0)
    to_input: int = Field(default=0, description="Input connector index on the destination", ge=0)


class QueryOpInput(BaseModel):
    """Get info about an operator — type, parameters, connections, children."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    op_path: str = Field(..., description="Path to the operator, e.g. '/project1/noise1'")
    include_params: bool = Field(default=True, description="Include non-default parameter values")
    include_connections: bool = Field(default=True, description="Include input/output wiring info")


class DeleteOpInput(BaseModel):
    """Delete an operator."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    op_path: str = Field(..., description="Path to the operator to delete")


class ListOpsInput(BaseModel):
    """List operators inside a component."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    parent_path: str = Field(default="/project1", description="Path to the parent COMP")
    op_type: Optional[str] = Field(default=None, description="Filter by type, e.g. 'TOP', 'CHOP', 'SOP', 'DAT', 'COMP'")
    max_depth: int = Field(default=1, description="How deep to search (1 = direct children only)", ge=1, le=5)


class SetExpressionInput(BaseModel):
    """Set a parameter expression (evaluated every frame) on an operator."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    op_path: str = Field(..., description="Path to the operator")
    param_name: str = Field(..., description="Parameter name, e.g. 'tx', 'seed', 'resolutionw'")
    expression: str = Field(..., description=(
        "Python expression string evaluated each frame. "
        "e.g. \"absTime.seconds\" or \"op('audiospectrum1')['chan1']\" "
        "or \"math.sin(absTime.seconds * 2)\""
    ))


class SaveProjectInput(BaseModel):
    """Save the current TD project."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    file_path: Optional[str] = Field(default=None, description=(
        "Optional path to save to. If omitted, saves to current project file."
    ))


class LayoutOpsInput(BaseModel):
    """Auto-layout operators inside a component for visual clarity."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    parent_path: str = Field(default="/project1", description="Path to the parent COMP to layout")


class SetPositionInput(BaseModel):
    """Set the network editor position of an operator for visual layout."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    op_path: str = Field(..., description="Path to the operator")
    x: float = Field(..., description="X position in network editor units")
    y: float = Field(..., description="Y position in network editor units")


# ---------------------------------------------------------------------------
# Helper: run code in TD
# ---------------------------------------------------------------------------

async def _run(td: TDConnection, code: str, timeout: float = 30.0) -> str:
    resp = await td.send_command(code, timeout=timeout)
    if resp.get("status") == "error":
        return f"Error: {resp.get('result', 'Unknown error')}"
    return resp.get("result", "OK")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="td_exec_python",
    annotations={
        "title": "Execute Python in TouchDesigner",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def td_exec_python(params: ExecPythonInput, ctx: Context) -> str:
    """Execute arbitrary Python code inside a running TouchDesigner instance.

    The code runs in TD's main Python context with access to all TD globals:
    op(), parent(), root, me, absTime, etc.

    The result of the last expression is returned as a string.

    Args:
        params: ExecPythonInput with code and optional timeout.

    Returns:
        str: The result or error message from TD.
    """
    td = _get_td(ctx)
    return await _run(td, params.code, params.timeout)


@mcp.tool(
    name="td_create_op",
    annotations={
        "title": "Create TouchDesigner Operator",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def td_create_op(params: CreateOpInput, ctx: Context) -> str:
    """Create a new operator inside a TouchDesigner component.

    Supports all TD operator types: noiseTOP, waveCHOP, baseCOMP, textDAT,
    compositeTOP, glslTOP, audiofileinCHOP, etc.

    Args:
        params: CreateOpInput with parent_path, op_type, and optional name.

    Returns:
        str: The path and info of the created operator, or an error.
    """
    td = _get_td(ctx)
    name_arg = f", '{params.name}'" if params.name else ""
    code = f"""
p = op('{params.parent_path}')
if p is None:
    result = 'Error: parent component not found: {params.parent_path}'
else:
    n = p.create({params.op_type}{name_arg})
    result = '{{"path": "' + n.path + '", "name": "' + n.name + '", "type": "' + n.OPType + '"}}'
result
"""
    return await _run(td, code)


@mcp.tool(
    name="td_set_params",
    annotations={
        "title": "Set Operator Parameters",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def td_set_params(params: SetParamsInput, ctx: Context) -> str:
    """Set one or more parameters on a TouchDesigner operator.

    Parameters are set by their internal name (e.g. 'resolutionw', 'seed', 'type').
    Use td_query_op to discover available parameter names first.

    Args:
        params: SetParamsInput with op_path and a dict of param: value pairs.

    Returns:
        str: Confirmation of which parameters were set, or errors.
    """
    td = _get_td(ctx)
    params_json = json.dumps(params.params)
    code = f"""
import json
n = op('{params.op_path}')
if n is None:
    result = 'Error: operator not found: {params.op_path}'
else:
    params_dict = json.loads('''{params_json}''')
    set_params = []
    errors = []
    for k, v in params_dict.items():
        try:
            setattr(n.par, k, v)
            set_params.append(k)
        except Exception as e:
            errors.append(f'{{k}}: {{str(e)}}')
    parts = []
    if set_params:
        parts.append('Set: ' + ', '.join(set_params))
    if errors:
        parts.append('Errors: ' + '; '.join(errors))
    result = ' | '.join(parts) if parts else 'No parameters provided'
result
"""
    return await _run(td, code)


@mcp.tool(
    name="td_connect",
    annotations={
        "title": "Connect (Wire) Operators",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def td_connect(params: ConnectOpsInput, ctx: Context) -> str:
    """Wire the output of one operator to the input of another.

    Both operators must be in the same parent component and of the same family
    (TOP→TOP, CHOP→CHOP, etc.).

    Args:
        params: ConnectOpsInput with source/dest paths and connector indices.

    Returns:
        str: Confirmation or error message.
    """
    td = _get_td(ctx)
    code = f"""
src = op('{params.from_op}')
dst = op('{params.to_op}')
if src is None:
    result = 'Error: source not found: {params.from_op}'
elif dst is None:
    result = 'Error: destination not found: {params.to_op}'
else:
    try:
        dst.inputConnectors[{params.to_input}].connect(src.outputConnectors[{params.from_output}])
        result = f'Connected {{src.path}} [out {params.from_output}] → {{dst.path}} [in {params.to_input}]'
    except Exception as e:
        result = f'Error connecting: {{str(e)}}'
result
"""
    return await _run(td, code)


@mcp.tool(
    name="td_query_op",
    annotations={
        "title": "Query Operator Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def td_query_op(params: QueryOpInput, ctx: Context) -> str:
    """Get detailed information about a TouchDesigner operator.

    Returns the operator's type, family, path, non-default parameters,
    input/output connections, and children (if it's a COMP).

    Args:
        params: QueryOpInput with op_path and flags.

    Returns:
        str: JSON-formatted operator info, or an error.
    """
    td = _get_td(ctx)
    code = f"""
import json
n = op('{params.op_path}')
if n is None:
    result = 'Error: operator not found: {params.op_path}'
else:
    info = {{
        'path': n.path,
        'name': n.name,
        'type': n.OPType,
        'family': n.family,
    }}
    if {params.include_params}:
        pars = {{}}
        for p in n.pars():
            if not p.isDefault and not p.readOnly:
                try:
                    pars[p.name] = str(p.eval())
                except:
                    pars[p.name] = str(p.val)
        info['params'] = pars
    if {params.include_connections}:
        inputs = []
        for c in n.inputConnectors:
            for conn in c.connections:
                inputs.append(conn.owner.path)
        outputs = []
        for c in n.outputConnectors:
            for conn in c.connections:
                outputs.append(conn.owner.path)
        info['inputs'] = inputs
        info['outputs'] = outputs
    if hasattr(n, 'children'):
        info['children'] = [c.path for c in n.children]
    result = json.dumps(info, indent=2)
result
"""
    return await _run(td, code)


@mcp.tool(
    name="td_delete_op",
    annotations={
        "title": "Delete Operator",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def td_delete_op(params: DeleteOpInput, ctx: Context) -> str:
    """Delete an operator from the TouchDesigner network.

    Args:
        params: DeleteOpInput with the op_path to delete.

    Returns:
        str: Confirmation or error.
    """
    td = _get_td(ctx)
    code = f"""
n = op('{params.op_path}')
if n is None:
    result = 'Error: operator not found: {params.op_path}'
else:
    path = n.path
    n.destroy()
    result = f'Deleted: {{path}}'
result
"""
    return await _run(td, code)


@mcp.tool(
    name="td_list_ops",
    annotations={
        "title": "List Operators in Component",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def td_list_ops(params: ListOpsInput, ctx: Context) -> str:
    """List operators inside a TouchDesigner component.

    Can filter by operator family (TOP, CHOP, SOP, DAT, COMP) and
    control search depth.

    Args:
        params: ListOpsInput with parent_path, optional type filter, and depth.

    Returns:
        str: JSON list of operators with path, name, type, family.
    """
    td = _get_td(ctx)
    type_filter = f"'{params.op_type}'" if params.op_type else "None"
    code = f"""
import json
p = op('{params.parent_path}')
if p is None:
    result = 'Error: component not found: {params.parent_path}'
else:
    type_filter = {type_filter}
    children = p.findChildren(maxDepth={params.max_depth})
    ops_list = []
    for c in children:
        if type_filter and c.family != type_filter:
            continue
        ops_list.append({{
            'path': c.path,
            'name': c.name,
            'type': c.OPType,
            'family': c.family,
        }})
    result = json.dumps(ops_list, indent=2)
result
"""
    return await _run(td, code)


@mcp.tool(
    name="td_set_expression",
    annotations={
        "title": "Set Parameter Expression",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def td_set_expression(params: SetExpressionInput, ctx: Context) -> str:
    """Set a Python expression on an operator parameter.

    The expression is evaluated every frame by TD's cook engine.
    Useful for animation, audio-reactivity, time-based effects, etc.

    Examples:
        - "absTime.seconds" (continuous time)
        - "math.sin(absTime.seconds * 3.14)" (oscillation)
        - "op('audioanalysis1')['chan1']" (audio-reactive)

    Args:
        params: SetExpressionInput with op_path, param_name, expression.

    Returns:
        str: Confirmation or error.
    """
    td = _get_td(ctx)
    # Escape quotes in the expression for safe embedding
    escaped_expr = params.expression.replace("\\", "\\\\").replace("'", "\\'")
    code = f"""
n = op('{params.op_path}')
if n is None:
    result = 'Error: operator not found: {params.op_path}'
else:
    try:
        p = getattr(n.par, '{params.param_name}')
        p.expr = '{escaped_expr}'
        p.mode = ParMode.EXPRESSION
        result = f'Expression set on {{n.path}}.par.{params.param_name}'
    except Exception as e:
        result = f'Error: {{str(e)}}'
result
"""
    return await _run(td, code)


@mcp.tool(
    name="td_save_project",
    annotations={
        "title": "Save TouchDesigner Project",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def td_save_project(params: SaveProjectInput, ctx: Context) -> str:
    """Save the current TouchDesigner project (.toe file).

    Can save to the current file or a specified path.

    Args:
        params: SaveProjectInput with optional file_path.

    Returns:
        str: Confirmation with the saved file path.
    """
    td = _get_td(ctx)
    if params.file_path:
        code = f"""
project.save('{params.file_path}')
result = 'Project saved to: {params.file_path}'
result
"""
    else:
        code = """
project.save()
result = f'Project saved to: {project.name}'
result
"""
    return await _run(td, code)


@mcp.tool(
    name="td_layout",
    annotations={
        "title": "Auto-Layout Operators",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def td_layout(params: LayoutOpsInput, ctx: Context) -> str:
    """Auto-layout operators inside a component for visual clarity.

    Args:
        params: LayoutOpsInput with parent_path.

    Returns:
        str: Confirmation.
    """
    td = _get_td(ctx)
    code = f"""
p = op('{params.parent_path}')
if p is None:
    result = 'Error: component not found: {params.parent_path}'
else:
    p.layoutChildren()
    result = f'Layout complete for {{p.path}}'
result
"""
    return await _run(td, code)


@mcp.tool(
    name="td_set_position",
    annotations={
        "title": "Set Operator Position",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def td_set_position(params: SetPositionInput, ctx: Context) -> str:
    """Set the network editor position of an operator.

    Useful for laying out networks in a readable way.

    Args:
        params: SetPositionInput with op_path, x, y.

    Returns:
        str: Confirmation or error.
    """
    td = _get_td(ctx)
    code = f"""
n = op('{params.op_path}')
if n is None:
    result = 'Error: operator not found: {params.op_path}'
else:
    n.nodeX = {params.x}
    n.nodeY = {params.y}
    result = f'Position set: {{n.path}} @ ({params.x}, {params.y})'
result
"""
    return await _run(td, code)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
