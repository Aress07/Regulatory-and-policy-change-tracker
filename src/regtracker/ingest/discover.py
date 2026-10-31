"""Discover consolidated versions of an act via the Cellar SPARQL endpoint.

Consolidated versions are separate Cellar works linked to the base act by
`cdm:act_consolidated_based_on_resource_legal`. Their CELEX is the base CELEX with sector `0`
and a `-YYYYMMDD` suffix, e.g. 32016R0679 -> 02016R0679-20160504.
"""

import re
from datetime import date
from typing import Any

from pydantic import BaseModel

from regtracker.common.http import PoliteClient

SPARQL_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
CELEX_RESOURCE = "http://publications.europa.eu/resource/celex/"

_BASE_CELEX = re.compile(r"^[1-9]\d{4}[A-Z]{1,2}\d{4}$")
_CONSOLIDATED_CELEX = re.compile(r"^0\d{4}[A-Z]{1,2}\d{4}-(\d{8})$")

_QUERY = """\
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?date WHERE {{
  ?base cdm:resource_legal_id_celex ?bc .
  FILTER(STR(?bc) = "{celex_base}")
  ?cons cdm:act_consolidated_based_on_resource_legal ?base ;
        cdm:resource_legal_id_celex ?celex .
  OPTIONAL {{ ?cons cdm:work_date_document ?date }}
}} ORDER BY ?celex
"""


class DiscoveryError(Exception):
    """The endpoint answered, but not with something we can use."""


class ConsolidatedVersion(BaseModel):
    celex_version: str
    version_date: date
    url: str


def build_query(celex_base: str) -> str:
    # Validating the format also guarantees nothing can be injected into the query.
    if not _BASE_CELEX.match(celex_base):
        raise ValueError(f"not a base CELEX number: {celex_base!r}")
    return _QUERY.format(celex_base=celex_base)


def parse_version_celex(celex: str) -> date:
    """Version date from the CELEX suffix, e.g. 02016R0679-20160504 -> 2016-05-04."""
    match = _CONSOLIDATED_CELEX.match(celex)
    if not match:
        raise ValueError(f"not a consolidated-version CELEX: {celex!r}")
    raw = match.group(1)
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))


def parse_results(payload: dict[str, Any]) -> list[ConsolidatedVersion]:
    """SPARQL JSON results -> versions sorted by date, deduplicated by CELEX.

    The CELEX suffix is the version date; `work_date_document` is only used as a sanity check.
    """
    try:
        bindings = payload["results"]["bindings"]
    except (KeyError, TypeError) as exc:
        raise DiscoveryError("unexpected SPARQL response shape") from exc

    versions: dict[str, ConsolidatedVersion] = {}
    for row in bindings:
        celex = row["celex"]["value"]
        version_date = parse_version_celex(celex)
        doc_date = row.get("date", {}).get("value")
        if doc_date and date.fromisoformat(doc_date) != version_date:
            raise DiscoveryError(f"{celex}: CELEX date and work_date_document ({doc_date}) differ")
        versions[celex] = ConsolidatedVersion(
            celex_version=celex, version_date=version_date, url=CELEX_RESOURCE + celex
        )
    return sorted(versions.values(), key=lambda v: v.version_date)


def discover_versions(client: PoliteClient, celex_base: str) -> list[ConsolidatedVersion]:
    """List consolidated versions of `celex_base`, oldest first."""
    response = client.get(
        SPARQL_ENDPOINT,
        params={"query": build_query(celex_base)},
        headers={"Accept": "application/sparql-results+json"},
        use_cache=False,  # new versions must never be hidden by a stale cached answer
    )
    if not response.is_success:
        raise DiscoveryError(f"SPARQL endpoint returned {response.status_code} for {celex_base}")
    return parse_results(response.json())
