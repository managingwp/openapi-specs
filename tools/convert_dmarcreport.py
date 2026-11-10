#!/usr/bin/env python3
"""Convert DMARC Report's Swagger 2.0 description into an MCP-ready spec.

Source: https://docs.dmarcreport.com/api/2.0.json?type=swagger

The converter is re-runnable: point ``--source`` at an updated vendor file, or
omit it to fetch the current published document, and the output is regenerated.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.lib import (  # noqa: E402
    auth,
    descriptions,
    mcphub,
    operation_ids,
    parameters,
    responses,
    servers,
    swagger2,
    types,
    writer,
)

SOURCE_URL = "https://docs.dmarcreport.com/api/2.0.json?type=swagger"
API_NAME = "dmarcreport"
SERVER_URL = "https://api.dmarcreport.com"
RAW_SPEC_URL = (
    "https://raw.githubusercontent.com/managingwp/openapi-specs/main/"
    "specs/dmarcreport/openapi.json"
)
EXPECTED_OPERATIONS = 50

#: The Gist's operationId mapping, keyed by the vendor's generated IDs.
OPERATION_IDS = {
    "get_v2_accounts": "list_accounts",
    "get_v2_accounts_id": "get_account",
    "post_v2_accounts.json": "create_account",
    "put_v2_accounts_id.json": "update_account",
    "delete_v2_accounts_id.json": "delete_account",
    "get_v2_accounts_id_compliance_summary": "get_account_compliance_summary",
    "get_v2_accounts_account_id_domains_domain_id_agg_reports.json": "list_aggregate_reports",
    "get_v2_accounts_account_id_domains_domain_id_agg_reports_records.json": "search_aggregate_report_records",
    "get_v2_accounts_account_id_domains_domain_id_agg_reports_id.json": "get_aggregate_report",
    "get_v2_accounts_account_id_domains_domain_id_agg_reports_agg_report_stats": "get_aggregate_report_stats",
    "get_v2_accounts_account_id_domains_domain_id_agg_reports_top_sources": "get_top_email_sources",
    "get_v2_accounts_account_id_domains_domain_id_agg_reports_alignment_failures": "get_alignment_failures",
    "get_v2_accounts_account_id_domains_domain_id_agg_reports_trends": "get_compliance_trends",
    "get_v2_accounts_account_id_domains_domain_id_agg_reports_pdf": "download_domain_pdf_report",
    "get_v2_accounts_account_id_alerts": "list_alerts",
    "get_v2_accounts_account_id_alerts_id": "get_alert",
    "get_v2_accounts_account_id_domains_domain_id_bimi_status": "get_bimi_status",
    "get_v2_accounts_account_id_domain_accounts": "list_domain_accounts",
    "get_v2_accounts_account_id_domain_accounts_id": "get_domain_account",
    "post_v2_accounts_account_id_domain_accounts.json": "add_domains_to_account",
    "delete_v2_accounts_account_id_domain_accounts_domain_accounts_id.json": "remove_domain_from_account",
    "get_v2_all_domains.json": "list_all_domains",
    "get_v2_accounts_account_id_domains.json": "list_domains",
    "post_v2_accounts_account_id_domains.json": "create_domain",
    "get_v2_accounts_account_id_domains_id.json": "get_domain",
    "put_v2_accounts_account_id_domains_id.json": "update_domain",
    "delete_v2_accounts_account_id_domains_id.json": "delete_domain",
    "get_v2_accounts_account_id_domains_id_hosted_services.json": "get_hosted_services",
    "post_v2_accounts_account_id_domains_id_verify_hosted_dmarc.json": "verify_hosted_dmarc",
    "post_v2_accounts_account_id_domains_id_verify_hosted_mta_sts.json": "verify_hosted_mta_sts",
    "post_v2_accounts_account_id_domains_id_generate_dmarc_record.json": "generate_dmarc_record",
    "delete_v2_accounts_account_id_domains_id_disable_hosted_dmarc.json": "disable_hosted_dmarc",
    "delete_v2_accounts_account_id_domains_id_disable_hosted_mta_sts.json": "disable_hosted_mta_sts",
    "get_v2_email_sources": "list_email_sources",
    "get_v2_email_tests_address": "get_email_test_address",
    "get_v2_email_tests": "list_email_tests",
    "get_v2_email_tests_id": "get_email_test",
    "get_v2_accounts_account_id_domains_domain_id_forensic_reports.json": "list_failure_reports",
    "get_v2_accounts_account_id_domains_domain_id_forensic_reports_id.json": "get_failure_report",
    "get_v2_accounts_account_id_domains_domain_id_mta_sts_reports.json": "list_mta_sts_reports",
    "get_v2_accounts_account_id_domains_domain_id_mta_sts_reports_mta_failure_details.json": "list_mta_sts_failure_details",
    "get_v2_accounts_account_id_domains_domain_id_mta_sts_reports_id.json": "get_mta_sts_report",
    "get_v2_postmaster_account_records.json": "list_postmaster_records",
    "get_v2_postmaster_account_records_id.json": "get_postmaster_record",
    "get_v2_postmaster_account_records_connected.json": "list_connected_postmaster_accounts",
    "get_v2_accounts_account_id_user_accounts": "list_user_accounts",
    "get_v2_accounts_account_id_user_accounts_id": "get_user_account",
    "post_v2_accounts_account_id_user_accounts.json": "add_user_to_account",
    "put_v2_accounts_account_id_user_accounts_id.json": "update_user_account",
    "delete_v2_accounts_account_id_user_accounts_id.json": "remove_user_from_account",
}

INFO_DESCRIPTION = """\
Unofficial OpenAPI 3.0.3 conversion of the DMARC Report API v2 \
(https://docs.dmarcreport.com/), cleaned up for MCPHub's OpenAPI server type and \
other OpenAPI-to-MCP bridges.

Converted from the Apipie Swagger 2.0 output at \
https://docs.dmarcreport.com/api/2.0.json?type=swagger by Managing WP \
(https://managingwp.io). Not affiliated with or endorsed by DMARC Report.

### Authentication
Create an API token in app.dmarcreport.com (profile icon > API Tokens > New Api \
Token), then send it as:

`Authorization: Token token=<your-token>`

### Changes from the source spec
- Swagger 2.0 to OpenAPI 3.0.3, with `servers` set to https://api.dmarcreport.com \
(the source had host localhost:3000).
- Added a `TokenAuth` security scheme (the source had none).
- Short operationIds that are valid MCP tool names (no dots, under 40 characters).
- `q[...]` query filters collapsed into a single `q` deepObject parameter; the \
bridge must support deepObject to send them.
- Form fields such as `domain[address]` turned into nested JSON request bodies.
- Boolean, integer and enum types fixed (page/per/limit as integers, true/false \
enums as booleans).
- HTML descriptions converted to Markdown; the sample token in the auth docs removed.
- Generic JSON 200 responses added (the source defines no success responses).
"""

RESPONSE_OVERRIDES = {
    "download_domain_pdf_report": {
        "description": "PDF audit report",
        "media_type": "application/pdf",
        "schema": {"type": "string", "format": "binary"},
    }
}


def fetch_swagger(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "openapi-specs/1.0 (+https://github.com/managingwp/openapi-specs)",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def load_swagger(source: str | None, url: str) -> dict:
    if not source:
        return fetch_swagger(url)
    if source.startswith(("http://", "https://")):
        return fetch_swagger(source)
    return writer.read_json(source)


def convert(swagger: dict) -> dict:
    document = swagger2.convert(
        swagger,
        server_url=SERVER_URL,
        server_description="DMARC Report API v2 (production)",
    )

    document["info"]["title"] = "DMARC Report API (unofficial OpenAPI 3)"
    document["info"]["description"] = INFO_DESCRIPTION

    auth.add_api_key(
        document,
        name="TokenAuth",
        header="Authorization",
        description="Value must be `Token token=<your-token>`.",
    )

    rewritten = operation_ids.rewrite_operation_ids(document, OPERATION_IDS)

    for _path, _method, operation in operation_ids.iter_operations(document):
        parameters.hoist_bracketed_query_params(operation)

    types.fix_document(document, integer_names={"pct"})
    descriptions.clean_document(document)
    responses.ensure_success_responses(document, overrides=RESPONSE_OVERRIDES)

    problems = servers.validate_servers(document)
    problems.extend(parameters.invalid_property_names(document))
    if problems:
        raise ValueError("generated spec is not MCP-ready:\n  - " + "\n  - ".join(problems))

    operation_count = sum(1 for _ in operation_ids.iter_operations(document))
    if operation_count != EXPECTED_OPERATIONS:
        raise ValueError(
            f"expected {EXPECTED_OPERATIONS} operations, found {operation_count}; "
            "review the vendor changes and update the operationId mapping"
        )

    unmapped = [
        operation.get("operationId", "")
        for _path, _method, operation in operation_ids.iter_operations(document)
        if operation.get("operationId") not in OPERATION_IDS.values()
    ]
    if unmapped:
        print(f"note: auto-named operations: {', '.join(sorted(unmapped))}")

    print(
        f"operationIds: {len(rewritten)} mapped, "
        f"{operation_count - len(rewritten)} auto-generated"
    )
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        help="local Swagger 2.0 file or URL (default: fetch the vendor URL)",
    )
    parser.add_argument("--url", default=SOURCE_URL, help="vendor Swagger 2.0 URL")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "specs" / API_NAME,
        help="output directory for the four spec files",
    )
    args = parser.parse_args()

    swagger = load_swagger(args.source, args.url)
    document = convert(swagger)

    output = args.out_dir / "openapi.json"
    writer.write_json(output, document)
    writer.write_json(
        args.out_dir / "mcphub.json",
        mcphub.api_key_server(
            API_NAME,
            RAW_SPEC_URL,
            value="Token token=YOUR_DMARC_REPORT_API_TOKEN",
        ),
    )

    write_operations = sum(
        1
        for _path, method, _operation in operation_ids.iter_operations(document)
        if method not in ("get", "head", "options")
    )
    total = sum(1 for _ in operation_ids.iter_operations(document))
    print(
        f"wrote {output} ({total} operations: "
        f"{total - write_operations} read, {write_operations} write)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
