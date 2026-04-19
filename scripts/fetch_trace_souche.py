


#!/usr/bin/env python3
"""
Fetch trace logs from Souche trace backend.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Optional
from urllib.parse import quote
import re

import urllib.request
import urllib.error
import ssl

try:
    import graphviz
except ImportError:
    graphviz = None


class TraceFetcher:
    """A class to fetch and process trace logs from Souche trace system."""

    def __init__(self, endpoint: str = "https://trace.souche-inc.com", cookies: Optional[str] = None, verify_ssl: bool = True):
        """Initialize the TraceFetcher.

        Args:
            endpoint: The base URL of the Souche trace API
            cookies: Optional cookies string for authentication
            verify_ssl: Whether to verify SSL certificates
        """
        self.endpoint = endpoint
        self.cookies = cookies
        self.verify_ssl = verify_ssl

    def fetch_trace(self, trace_id: str, date: str) -> dict:
        """Fetch trace tree from Souche trace system.

        Args:
            trace_id: The trace ID to fetch
            date: Date in YYYY-MM-DD format

        Returns:
            The trace data as a dictionary
        """
        begin_date = f"{date} 00:00:00.000"
        end_date = f"{date} 23:59:59.999"
        url = f"{self.endpoint}/logtrace/show/logTreeByTraceid.json?traceid={trace_id}&beginDate={quote(begin_date)}&endDate={quote(end_date)}&regType=0"
        return self._make_request(url)

    def fetch_host(self) -> dict:
        """Fetch host information from Souche trace system.

        Returns:
            The host information as a dictionary
        """
        url = f"{self.endpoint}/logtrace/show/getCuckooHost.json"
        return self._make_request(url)

    def _make_request(self, url: str) -> dict:
        """Make HTTP request and return JSON response.

        Args:
            url: The URL to request

        Returns:
            The JSON response as a dictionary
        """
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://trace.souche-inc.com/logTraceidResult.html",
            "Sec-Ch-Ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest"
        }

        req = urllib.request.Request(url, headers=headers)

        if self.cookies:
            req.add_header("Cookie", self.cookies)

        try:
            if self.verify_ssl:
                with urllib.request.urlopen(req) as response:
                    return json.loads(response.read().decode('utf-8'))
            else:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, context=ctx) as response:
                    return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(f"URL Error: {e.reason}", file=sys.stderr)
            sys.exit(1)

    @staticmethod
    def _extract_params_from_sql(actual_sql: str, sql_template: str) -> list:
        """Extract parameter values from actual SQL by comparing with template.
        
        Args:
            actual_sql: The actual SQL with values substituted
            sql_template: The SQL template with ? placeholders
            
        Returns:
            List of extracted parameter values
        """
        import re
        params = []
        # Split both SQLs by common delimiters to find differences
        template_parts = re.split(r'(\?|=|\s+)', sql_template)
        actual_parts = re.split(r'(=|\s+)', actual_sql)
        
        # Find values that replace ? in template
        t_idx = 0
        a_idx = 0
        while t_idx < len(template_parts) and a_idx < len(actual_parts):
            if template_parts[t_idx] == '?':
                # Next non-empty part in actual is the parameter value
                while a_idx < len(actual_parts) and actual_parts[a_idx].strip() == '':
                    a_idx += 1
                if a_idx < len(actual_parts):
                    val = actual_parts[a_idx].strip()
                    # Clean up value (remove trailing punctuation)
                    val = re.sub(r'[,;)\]]+$', '', val)
                    params.append(val)
                a_idx += 1
                t_idx += 1
            elif template_parts[t_idx].strip() == '':
                t_idx += 1
            elif actual_parts[a_idx].strip() == '':
                a_idx += 1
            else:
                t_idx += 1
                a_idx += 1
        return params

    @staticmethod
    def _extract_params_from_actual_sql(actual_sql: str) -> list:
        """Extract parameter values from actual SQL by finding values after operators.
        
        Args:
            actual_sql: The actual SQL with values
            
        Returns:
            List of extracted parameter values
        """
        import re
        params = []
        # Find values after = , IN (, etc.
        # Pattern: = value or IN (value1, value2)
        patterns = [
            r'=\s*([^,\s\)]+)',  # Values after =
            r'IN\s*\(\s*([^\)]+)\)',  # Values inside IN ()
        ]
        for pattern in patterns:
            matches = re.findall(pattern, actual_sql, re.IGNORECASE)
            for match in matches:
                if ',' in match:
                    # Multiple values in IN clause
                    vals = [v.strip().strip("'\"") for v in match.split(',')]
                    params.extend(vals)
                else:
                    params.append(match.strip().strip("'\""))
        return params

    @staticmethod
    def extract_sql_data(data: dict or list) -> list:
        """Recursively extract all items with type='sql' from the trace data.

        Args:
            data: The trace data (dict or list)

        Returns:
            A list of SQL entries
        """
        sql_items = []

        if isinstance(data, dict):
            if data.get("type") == "sql":
                sql_items.append(data)
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    sql_items.extend(TraceFetcher.extract_sql_data(value))
        elif isinstance(data, list):
            for item in data:
                sql_items.extend(TraceFetcher.extract_sql_data(item))

        return sql_items

    @staticmethod
    def format_complete_sql(detail: dict) -> Optional[str]:
        """Format complete SQL by combining sql template with params.

        Args:
            detail: The SQL detail response from API

        Returns:
            The formatted complete SQL string, or None if cannot format
        """
        if not detail or not isinstance(detail, dict):
            return None

        # Handle nested data structure from API response
        if "data" in detail and isinstance(detail["data"], dict):
            data = detail["data"]
        else:
            data = detail

        # Get SQL template - in this API it's in 'path' field
        sql_template = (data.get("path") or
                       data.get("sql") or
                       data.get("sqlText") or
                       data.get("sqlStatement") or
                       data.get("statement") or
                       data.get("query"))

        # Get params - in this API they might be in 'extparams'
        params = (data.get("extparams") or
                 data.get("params") or
                 data.get("parameters") or
                 data.get("args"))

        if not sql_template:
            return None

        # Clean up SQL template (remove newlines and extra whitespace)
        sql_template = " ".join(sql_template.split())

        if not params:
            return sql_template

        # Format params into SQL template
        try:
            # Handle extparams as string - parse it properly
            if isinstance(params, str):
                # Try to parse as JSON first
                import json
                try:
                    parsed_params = json.loads(params)

                    if isinstance(parsed_params, dict):
                        # Check for sqlParams field which contains param[0]=value format
                        if "sqlParams" in parsed_params:
                            sql_params = parsed_params["sqlParams"]
                            # Parse param[0]='value',param[1]=value format
                            import re
                            # Match param[index]=value where value can be quoted string, number, or null
                            param_matches = re.findall(r'param\[(\d+)\]=([^,]*(?:\[[^\]]*\][^,]*)?)', sql_params)
                            if param_matches:
                                # Sort by index and extract values
                                param_dict = {}
                                for idx, val in param_matches:
                                    val = val.strip()
                                    # Handle null
                                    if val.lower() == 'null':
                                        param_dict[int(idx)] = None
                                    # Handle quoted strings
                                    elif val.startswith("'") and val.endswith("'"):
                                        param_dict[int(idx)] = val[1:-1]
                                    elif val.startswith('"') and val.endswith('"'):
                                        param_dict[int(idx)] = val[1:-1]
                                    # Handle numbers
                                    else:
                                        try:
                                            num_val = float(val)
                                            if num_val.is_integer():
                                                param_dict[int(idx)] = int(num_val)
                                            else:
                                                param_dict[int(idx)] = num_val
                                        except ValueError:
                                            param_dict[int(idx)] = val

                                # Convert to list in order
                                max_idx = max(param_dict.keys())
                                param_list = []
                                for i in range(max_idx + 1):
                                    param_list.append(param_dict.get(i))
                                params = param_list

                                # Use dbSql as template if available, otherwise use path
                                if "dbSql" in parsed_params:
                                    sql_template = parsed_params["dbSql"]
                                    # Clean up SQL template (remove newlines and extra whitespace)
                                    sql_template = " ".join(sql_template.split())

                        # First try to get actual SQL from actualSqlList
                        elif "actualSqlList" in parsed_params and isinstance(parsed_params["actualSqlList"], str):
                            try:
                                actual_sql_list = json.loads(parsed_params["actualSqlList"])
                                if isinstance(actual_sql_list, list) and len(actual_sql_list) > 0:
                                    first_sql = actual_sql_list[0]
                                    actual_sql = first_sql.get("sql", "")

                                    if actual_sql and len(actual_sql) >= len(sql_template) * 0.9:
                                        return actual_sql

                                    # Try to extract params from actual_sql
                                    extracted_params = TraceFetcher._extract_params_from_actual_sql(actual_sql)
                                    if extracted_params:
                                        params = extracted_params
                            except json.JSONDecodeError:
                                pass

                        # If we have logicSql and no params extracted, use logicSql
                        if "logicSql" in parsed_params and not isinstance(params, list):
                            logic_sql = parsed_params["logicSql"]
                            # Remove newlines and extra whitespace
                            logic_sql = " ".join(logic_sql.split())
                            return logic_sql

                        if not isinstance(params, list):
                            params = parsed_params
                    elif isinstance(parsed_params, list):
                        params = parsed_params
                    else:
                        params = [parsed_params]
                except json.JSONDecodeError:
                    # Not valid JSON, try to extract param[0], param[1] values
                    # Format: param[0]='value',param[1]='value' or param[0]=value,param[1]=value
                    import re
                    param_matches = re.findall(r'param\[(\d+)\]=([^,]+)', params)
                    if param_matches:
                        # Sort by index and extract values
                        param_dict = {int(idx): val.strip().strip("'\"") for idx, val in param_matches}
                        max_idx = max(param_dict.keys())
                        param_list = []
                        for i in range(max_idx + 1):
                            if i in param_dict:
                                val = param_dict[i]
                                # Try to convert to number
                                try:
                                    num_val = float(val)
                                    if num_val.is_integer():
                                        val = int(num_val)
                                except ValueError:
                                    pass
                                param_list.append(val)
                            else:
                                param_list.append(None)
                        params = param_list
                    else:
                        # Simple comma-separated fallback
                        param_list = [p.strip() for p in params.split(",")]
                        params = param_list

            if isinstance(params, list):
                formatted_sql = sql_template
                for param in params:
                    if isinstance(param, str):
                        formatted_sql = formatted_sql.replace("?", f"'{param}'", 1)
                    elif param is None:
                        formatted_sql = formatted_sql.replace("?", "NULL", 1)
                    else:
                        formatted_sql = formatted_sql.replace("?", str(param), 1)
                # Remove newlines and extra whitespace
                formatted_sql = " ".join(formatted_sql.split())
                return formatted_sql
            elif isinstance(params, dict):
                # Replace named placeholders like :name or #{name}
                formatted_sql = sql_template
                for key, value in params.items():
                    placeholder = f":{key}"
                    if placeholder in formatted_sql:
                        if isinstance(value, str):
                            formatted_sql = formatted_sql.replace(placeholder, f"'{value}'")
                        elif value is None:
                            formatted_sql = formatted_sql.replace(placeholder, "NULL")
                        else:
                            formatted_sql = formatted_sql.replace(placeholder, str(value))
                # Remove newlines and extra whitespace
                formatted_sql = " ".join(formatted_sql.split())
                return formatted_sql
            else:
                # Remove newlines and extra whitespace
                sql_template = " ".join(sql_template.split())
                return sql_template
        except Exception:
            # If formatting fails, return original SQL
            return sql_template

    @staticmethod
    def _build_span_tree(spans_data, root_span_id=None):
        """Build a tree representation from span data.

        Args:
            spans_data: List of spans from trace data
            root_span_id: ID of the root span (if None, find spans without parents)

        Returns:
            Tree structure of spans
        """
        # Create a mapping of spans by their IDs
        spans_by_id = {}
        for span in spans_data:
            span_id = span.get("spanId", "unknown")
            spans_by_id[span_id] = span

        # Helper function to recursively find children
        def find_children(parent_id):
            children = []
            for span_id, span in spans_by_id.items():
                if span.get("parentId") == parent_id:
                    child_node = {
                        "span": span,
                        "children": find_children(span_id)
                    }
                    children.append(child_node)
            return children

        # Find root span(s) - spans with no parent or parent not in our dataset
        roots = []
        for span_id, span in spans_by_id.items():
            parent_id = span.get("parentId")
            if not parent_id or parent_id not in spans_by_id:
                root_node = {
                    "span": span,
                    "children": find_children(span_id)
                }
                roots.append(root_node)

        return roots

    @staticmethod
    def _print_span_tree(tree_node, depth=0, prefix="", is_last=True):
        """Print the span tree in a visual format.

        Args:
            tree_node: Node in the tree to print
            depth: Current depth in the tree
            prefix: Prefix to use for current level
            is_last: Whether this is the last child at this level
        """
        if depth == 0:
            # Root level
            span = tree_node["span"]
            operation_name = span.get("operationName", "Unknown")
            service_name = span.get("serviceName", "Unknown")
            duration = span.get("duration", 0)
            print(f"{operation_name} ({service_name}) [{duration}us]")
            for i, child in enumerate(tree_node["children"]):
                is_last_child = (i == len(tree_node["children"]) - 1)
                TraceFetcher._print_span_tree(child, depth + 1, "", is_last_child)
        else:
            # Child levels
            span = tree_node["span"]
            operation_name = span.get("operationName", "Unknown")
            service_name = span.get("serviceName", "Unknown")
            duration = span.get("duration", 0)

            # Draw tree lines
            if is_last:
                print("{}L-- {} ({}) [{}us]".format(prefix, operation_name, service_name, duration))
                new_prefix = prefix + "    "
            else:
                print("{}+-- {} ({}) [{}us]".format(prefix, operation_name, service_name, duration))
                new_prefix = prefix + "|   "

            # Print children
            for i, child in enumerate(tree_node["children"]):
                is_last_child = (i == len(tree_node["children"]) - 1)
                TraceFetcher._print_span_tree(child, depth + 1, new_prefix, is_last_child)

    @staticmethod
    def _generate_text_call_graph(trace_data):
        """Generate a text-based call graph from the trace data.

        Args:
            trace_data: The full trace data from API
        """
        def extract_spans_from_log_tree(data, spans=None):
            """Extract spans from logTreeVOList format."""
            if spans is None:
                spans = []

            def traverse_nodes(nodes, parent_seq=None):
                if not nodes:
                    return

                for node in nodes:
                    # Create a span-like object from the log tree node
                    span = {
                        "spanId": node.get("rid"),
                        "parentId": parent_seq,
                        "operationName": node.get("path", "Unknown"),
                        "serviceName": node.get("app", "Unknown"),
                        "duration": node.get("cost", 0),
                        "type": node.get("type", "Unknown"),
                        "seq": node.get("seq", ""),  # Store the sequence for parent-child relationship
                        "env": node.get("env", ""),
                        "errtag": node.get("errtag", ""),
                        "time": node.get("time", "")
                    }
                    spans.append(span)

                    # Process children if they exist
                    children = node.get("children", [])
                    if children:
                        traverse_nodes(children, node.get("seq"))

            # Handle the top level of the log tree
            if isinstance(data, dict) and "data" in data and "logTreeVOList" in data["data"]:
                log_tree_list = data["data"]["logTreeVOList"]
                if log_tree_list:
                    traverse_nodes(log_tree_list)

            return spans

        # Extract spans from the trace data
        spans = extract_spans_from_log_tree(trace_data)

        if not spans:
            print("No spans found in trace data")
            return

        print("Found {} spans in trace data".format(len(spans)))

        # Build a mapping of sequences to spans for building the tree
        span_map = {}
        for span in spans:
            seq = span["seq"]  # Use sequence for parent-child relationships
            if seq:
                span_map[seq] = span

        # Find root spans (those without parents or parents not in the dataset)
        root_spans = []
        for span in spans:
            parent_id = span["parentId"]
            if not parent_id or parent_id not in span_map:
                root_spans.append(span)

        # Helper function to print the tree
        def print_tree(spans_list, prefix="", is_last=True):
            for i, span in enumerate(spans_list):
                is_last_item = (i == len(spans_list) - 1)

                # Find children of this span
                children = []
                for s in spans:
                    if s["parentId"] == span["seq"]:  # Match by sequence
                        children.append(s)

                # Print current span
                if is_last_item:
                    print("{}L-- {} ({}) [{}us] (type: {})".format(
                        prefix,
                        span["operationName"],
                        span["serviceName"],
                        span["duration"],
                        span["type"]
                    ))
                    new_prefix = prefix + "    "
                else:
                    print("{}+-- {} ({}) [{}us] (type: {})".format(
                        prefix,
                        span["operationName"],
                        span["serviceName"],
                        span["duration"],
                        span["type"]
                    ))
                    new_prefix = prefix + "|   "

                # Recursively print children
                if children:
                    print_tree(children, new_prefix, True)

        # Print the tree starting from root spans
        print_tree(root_spans)

    @staticmethod
    def _generate_call_graph(trace_data, output_file=None):
        """Generate a call graph from the trace data.

        Args:
            trace_data: The full trace data from API
            output_file: Output file for the graph (without extension)
        """
        global graphviz

        try:
            import graphviz
        except ImportError:
            graphviz = None

        if not graphviz:
            print("graphviz Python module is not installed. Generating text-based call graph instead.")
            TraceFetcher._generate_text_call_graph(trace_data)
            return

        def extract_spans(data, spans=None):
            """Recursively extract spans from trace data."""
            if spans is None:
                spans = []

            if isinstance(data, dict):
                if "spanId" in data and "operationName" in data:
                    spans.append(data)
                for value in data.values():
                    extract_spans(value, spans)
            elif isinstance(data, list):
                for item in data:
                    extract_spans(item, spans)
            return spans

        # Extract all spans from the trace data
        spans = extract_spans(trace_data)

        # Check if Graphviz binary is available
        try:
            import graphviz.backend
            has_dot = graphviz.backend.find_executable('dot') is not None
        except:
            has_dot = False

        if not has_dot:
            print("Graphviz 'dot' executable not found. Generating text-based call graph instead.")
            TraceFetcher._generate_text_call_graph(trace_data)
            return

        # Create a directed graph
        dot = graphviz.Digraph(comment='Trace Call Graph')
        dot.attr(rankdir='TB', size='12,16')
        dot.attr('node', shape='box', fontsize='10', margin='0.1')

        # Add nodes and edges
        for span in spans:
            span_id = span.get("spanId", "unknown")
            operation_name = span.get("operationName", "unknown")
            service_name = span.get("serviceName", "unknown")
            duration = span.get("duration", 0)

            # Format node label
            label = "{}\\n({})\\n{}us".format(operation_name, service_name, duration)
            dot.node(span_id, label)

        # Add edges based on parent-child relationships
        for span in spans:
            span_id = span.get("spanId", "unknown")
            parent_id = span.get("parentId")

            if parent_id and parent_id != span_id:
                dot.edge(parent_id, span_id)

        # Save the graph
        if output_file:
            # Extract the directory and base name
            directory = os.path.dirname(output_file)
            basename = os.path.basename(output_file)
            # Render the graph (this creates both .dot and .png files)
            dot.render(filename=output_file, format='png', cleanup=True)
            print("Call graph saved to {}.png".format(output_file))
        else:
            print(dot.source)  # Print DOT source

        return dot

    def fetch_sql_detail(self, rid: str) -> dict:
        """Fetch SQL detail by RID from getDetailParamsByRid.jsonp API.

        Args:
            rid: The RID (e.g., '1774764304798_AKFw-1.3.1.1')

        Returns:
            The SQL detail response as a dictionary
        """
        import re
        callback = "__jp3"
        url = f"{self.endpoint}/logtrace/show/getDetailParamsByRid.jsonp?rid={rid}&callback={callback}"

        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://trace.souche-inc.com/index.html",
            "Sec-Ch-Ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "script",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        }

        req = urllib.request.Request(url, headers=headers)

        if self.cookies:
            req.add_header("Cookie", self.cookies)

        try:
            if self.verify_ssl:
                with urllib.request.urlopen(req) as response:
                    content = response.read().decode('utf-8')
            else:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, context=ctx) as response:
                    content = response.read().decode('utf-8')

            # Parse JSONP response: __jp3({...})
            match = re.search(rf'{callback}\((.*)\)\s*$', content, re.DOTALL)
            if match:
                json_content = match.group(1)
                return json.loads(json_content)
            else:
                # Try alternative patterns
                match2 = re.search(rf'{callback}\s*\(\s*(\{{.*\}})\s*\)\s*;?\s*$', content, re.DOTALL)
                if match2:
                    return json.loads(match2.group(1))
                # Try to find any JSON object in the response
                match3 = re.search(r'\{.*\}', content, re.DOTALL)
                if match3:
                    try:
                        return json.loads(match3.group(0))
                    except:
                        pass
                return {"raw_response": content}
        except urllib.error.HTTPError as e:
            print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
            return {"error": f"HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            print(f"URL Error: {e.reason}", file=sys.stderr)
            return {"error": f"URL Error: {e.reason}"}
        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {e}", file=sys.stderr)
            return {"error": f"JSON Decode Error: {e}", "raw_response": content if 'content' in locals() else None}


# ========== DEFAULT PARAMETERS ==========
# You can modify these values to set default parameters

# Environment endpoints
ENV_ENDPOINTS = {
    "pro": "https://trace.souche-inc.com",
    "env": "https://test-trace.dasouche-inc.net"
}
DEFAULT_ENV = "pro"  # Default environment: pro or env

DEFAULT_TRACE_ID = "1774764304798_AKFw"
DEFAULT_DATE = "2026-03-29"

# Individual cookie parameters
DEFAULT_USER_IID = "31893307"
# DEFAULT_IS_DINGDING = "true"
DEFAULT_TRACKNICK = "13655815401"
DEFAULT_SECURITY_TOKEN = "91774582198396869"
DEFAULT_ACW_TC = "781a97e317747659085477856e947033e68dbf7a0ca21b35e6191666046574"
DEFAULT_JSESSIONID = "A892166CD9C258BAEF0405B1BD322C51"

# Combined cookies string (auto-generated from individual parameters)
DEFAULT_COOKIES = f"_user_iid={DEFAULT_USER_IID}; tracknick={DEFAULT_TRACKNICK}; _security_token_inc={DEFAULT_SECURITY_TOKEN}; acw_tc={DEFAULT_ACW_TC}; JSESSIONID={DEFAULT_JSESSIONID}"

DEFAULT_VERIFY_SSL = False
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/Desktop")
DEFAULT_EXTRACT_SQL = True
# ========== END OF DEFAULT PARAMETERS ==========


def main():
    parser = argparse.ArgumentParser(description="Fetch trace logs from Souche trace system")
    parser.add_argument("--env", default=DEFAULT_ENV, choices=["pro", "env"],
                        help="Environment: pro (production) or env (test)")
    parser.add_argument("--endpoint",
                        help="Souche trace API endpoint (overrides --env)")
    parser.add_argument("--trace-id", default=DEFAULT_TRACE_ID,
                        help="Trace ID to fetch")
    parser.add_argument("--date", default=DEFAULT_DATE,
                        help="Date for Souche trace (YYYY-MM-DD format)")
    parser.add_argument("--souche-host", action="store_true",
                        help="Fetch Souche host information (getCuckooHost.json)")
    parser.add_argument("--cookies", default=DEFAULT_COOKIES,
                        help="Cookies string for authentication (e.g., '_user_iid=xxx; JSESSIONID=xxx')")
    parser.add_argument("--insecure", default=not DEFAULT_VERIFY_SSL, action="store_true",
                        help="Disable SSL certificate verification (insecure)")
    parser.add_argument("--output", help="Output file (default: auto-generated)")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help="Output directory for default filenames (default: ~/Desktop)")
    parser.add_argument("--extract-sql", default=DEFAULT_EXTRACT_SQL, action="store_true",
                        help="Extract and save SQL data to a separate file")
    parser.add_argument("--no-extract-sql", dest="extract_sql", action="store_false",
                        help="Disable SQL extraction")
    parser.add_argument("--generate-call-graph", action="store_true",
                        help="Generate a call graph from the trace data")

    args = parser.parse_args()

    # Determine endpoint based on environment
    if args.endpoint:
        endpoint = args.endpoint
    else:
        endpoint = ENV_ENDPOINTS.get(args.env, ENV_ENDPOINTS["pro"])

    # Initialize the TraceFetcher class
    fetcher = TraceFetcher(
        endpoint=endpoint,
        cookies=args.cookies,
        verify_ssl=not args.insecure
    )

    if args.souche_host:
        result = fetcher.fetch_host()
        output = json.dumps(result, indent=2, ensure_ascii=False)

        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(f"Output written to {args.output}")
        else:
            print(output)
    elif args.trace_id:
        if not args.date:
            parser.error("--date is required for Souche trace fetching (format: YYYY-MM-DD)")

        result = fetcher.fetch_trace(args.trace_id, args.date)

        # Generate dynamic filename for full trace data
        current_time = datetime.now().strftime("%Y%m%d%H%M%S")

        # Generate call graph if requested
        if args.generate_call_graph:
            graph_filename = os.path.join(args.output_dir, f"trace_{args.trace_id}_{current_time}_call_graph")
            print(f"Generating call graph...")
            TraceFetcher._generate_call_graph(result, graph_filename)

        # Write full trace data to file if not extracting SQL
        if not args.extract_sql:
            full_trace_file = os.path.join(args.output_dir, f"trace_{args.trace_id}_{current_time}_full.json")
            with open(full_trace_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"Full trace data written to {full_trace_file}")

        # Extract SQL data
        if args.extract_sql:
            sql_data = TraceFetcher.extract_sql_data(result)
            print(f"Found {len(sql_data)} SQL entries")

        # Fetch SQL details for each SQL entry
        if args.extract_sql and sql_data:
            print(f"\nFetching SQL details for {len(sql_data)} entries...")
            sql_details = []
            for i, sql_entry in enumerate(sql_data, 1):
                rid = sql_entry.get("rid") or sql_entry.get("id")
                if rid:
                    print(f"  [{i}/{len(sql_data)}] Fetching detail for RID: {rid}")
                    detail = fetcher.fetch_sql_detail(rid)
                    # Format complete SQL if detail contains sql and params
                    formatted_sql = TraceFetcher.format_complete_sql(detail)
                    # Only keep the 'sql' key in detail
                    if formatted_sql:
                        detail = {"sql": formatted_sql}
                    else:
                        detail = {"sql": None}
                    sql_details.append({
                        "rid": rid,
                        "detail": detail
                    })
                else:
                    print(f"  [{i}/{len(sql_data)}] No RID found, skipping")
                    sql_details.append({
                        "rid": None,
                        "detail": {"sql": None}
                    })

            # Write SQL details output (JSON)
            sql_detail_file = os.path.join(args.output_dir, f"trace_{args.trace_id}_{current_time}_sql_details.json")
            sql_detail_output = {
                "summary": {
                    "trace_id": args.trace_id,
                    "date": args.date,
                    "sql_count": len(sql_data),
                    "detail_count": len([d for d in sql_details if d["detail"] is not None]),
                    "generated_at": datetime.now().isoformat()
                },
                "sql_details": sql_details
            }
            with open(sql_detail_file, 'w', encoding='utf-8') as f:
                json.dump(sql_detail_output, f, indent=2, ensure_ascii=False)
            print(f"\nSQL details written to {sql_detail_file}")
    else:
        parser.error("Either --trace-id or --souche-host is required")


if __name__ == "__main__":
    main()
