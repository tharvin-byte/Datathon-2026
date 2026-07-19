"""
LINK AGENT (Agent 2) — Crime AI
=================================
PURPOSE: Given the records from Query Agent, figure out who's connected
to whom, and through what — building a criminal network graph.

TWO MECHANISMS (both always run on every call):

  1. STRUCTURED FIELD MATCHING — compare accused_name, address, phone,
     co_accused_ids across all records. If two records share any of these,
     an edge is added between the people involved.
     Technique: direct string comparison + fuzzy matching (difflib)

  2. NARRATIVE NER EXTRACTION — run Named Entity Recognition on each
     record's free-text description to pull out person names that may
     NOT appear in the structured columns.
     Technique: spaCy NER (or regex fallback if spaCy isn't installed)

Every entity and edge in the final graph carries a "basis" tag — e.g.
"same_address", "co_accused_field", "narrative_mention" — so the
Verifier Agent can trace exactly WHY two people are connected.

INPUT:  state["records_found"] (from Query Agent)
OUTPUT: state["entities_found"] — list of person nodes with metadata
        state["network_edges"]  — list of connections with basis tags

DEPENDENCY: Runs AFTER Query Agent. Can run IN PARALLEL with Trend Agent
            (both only need Query Agent's output).
"""

import re
from collections import defaultdict
from difflib import SequenceMatcher

# ---------------------------------------------------------------------------
# NetworkX — graph library for building and traversing the criminal network
# We use an undirected graph because "A is connected to B" is bidirectional.
# Each node = a person, each edge = a connection with a basis string.
# ---------------------------------------------------------------------------
import networkx as nx

# ---------------------------------------------------------------------------
# NER SETUP — we try spaCy first, fall back to regex if not installed.
# spaCy's en_core_web_sm model recognizes PERSON, ORG, GPE entities.
# For a crime dataset, we mainly care about PERSON entities in descriptions.
# ---------------------------------------------------------------------------
_nlp_model = None
_ner_checked = False
NER_AVAILABLE = False

def get_spacy_nlp():
    global _nlp_model, _ner_checked, NER_AVAILABLE
    if not _ner_checked:
        _ner_checked = True
        try:
            import spacy
            _nlp_model = spacy.load("en_core_web_sm")
            NER_AVAILABLE = True
        except Exception:
            _nlp_model = None
            NER_AVAILABLE = False
    return _nlp_model


# ===================================================================
# HELPER: Fuzzy string matching
# ===================================================================
# Why fuzzy? Real crime data is messy — "Raju Gowda" in one record
# might be "Raju K. Gowda" or "Raju gowda" in another. A strict
# exact match would miss these. SequenceMatcher gives a similarity
# ratio between 0 and 1; we treat >= 0.85 as "same person."
# ===================================================================

FUZZY_THRESHOLD = 0.85


def is_fuzzy_match(name_a: str, name_b: str) -> bool:
    """Check if two names are similar enough to be the same person."""
    if not name_a or not name_b:
        return False
    a = name_a.strip().lower()
    b = name_b.strip().lower()
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= FUZZY_THRESHOLD


def normalize_name(name) -> str:
    """Standardize a name for consistent node IDs in the graph."""
    if name is None or (isinstance(name, float) and str(name) == "nan"):
        return ""
    name = str(name)
    if not name:
        return ""
    return " ".join(name.strip().split()).title()


def safe_str(value) -> str:
    """
    Safely convert any value to a string.
    Handles NaN (float) from pandas, None, and normal strings.
    Pandas reads empty CSV cells as NaN (a float), which is truthy
    in Python — so `value or ""` doesn't catch it, and calling
    .strip() on a float crashes. This function handles all cases.
    """
    if value is None:
        return ""
    if isinstance(value, float):
        # NaN check: NaN != NaN is True
        if value != value:
            return ""
        return str(int(value)) if value == int(value) else str(value)
    return str(value)


# ===================================================================
# MECHANISM 1: STRUCTURED FIELD MATCHING
# ===================================================================
# Walk through all records and compare structured columns:
#   - accused_name: same person appears in multiple cases
#   - address: different people at the same address
#   - phone: different people using the same phone number
#   - co_accused_ids: explicitly listed as co-accused
#
# Each match creates a graph edge with a specific basis tag.
# ===================================================================

def extract_structured_links(records: list[dict], graph: nx.Graph) -> None:
    """
    Compare structured fields across all record pairs.
    Adds nodes and edges directly to the graph.
    """
    # --- Index records by shared attributes for efficient matching ---

    # Group by address (normalized lowercase, stripped)
    address_groups = defaultdict(list)
    # Group by phone
    phone_groups = defaultdict(list)
    # Track all accused names and their case IDs
    name_to_cases = defaultdict(list)

    for record in records:
        case_id = record.get("case_id", "unknown")
        accused = normalize_name(record.get("accused_name", ""))
        victim = normalize_name(record.get("victim_name", ""))
        address = safe_str(record.get("address")).strip().lower()
        phone = safe_str(record.get("phone")).strip()
        co_accused = safe_str(record.get("co_accused_ids")).strip()

        # Add the accused as a node (with metadata)
        if accused and accused.lower() != "unknown" and accused.lower() != "na":
            graph.add_node(accused, type="accused", cases=[case_id])
            # If node already exists, append this case to its list
            if "cases" in graph.nodes[accused]:
                if case_id not in graph.nodes[accused]["cases"]:
                    graph.nodes[accused]["cases"].append(case_id)

            name_to_cases[accused].append(case_id)

        # Add victim as a node too (they're part of the network)
        if victim and victim.lower() != "unknown" and victim.lower() != "na":
            graph.add_node(victim, type="victim", cases=[case_id])
            if "cases" in graph.nodes[victim]:
                if case_id not in graph.nodes[victim]["cases"]:
                    graph.nodes[victim]["cases"].append(case_id)

        # Index by address
        if address and address not in ("na", "unknown", ""):
            address_groups[address].append(
                {"name": accused, "case_id": case_id}
            )

        # Index by phone
        if phone and phone not in ("na", "unknown", ""):
            phone_groups[phone].append(
                {"name": accused, "case_id": case_id}
            )

        # Handle co_accused_ids — these are explicit links
        if co_accused:
            # co_accused_ids is comma-separated case IDs like "C001,C003"
            linked_case_ids = [
                cid.strip() for cid in co_accused.split(",") if cid.strip()
            ]
            for linked_id in linked_case_ids:
                # Find the accused in the linked case
                for other_record in records:
                    if other_record.get("case_id") == linked_id:
                        other_accused = normalize_name(
                            other_record.get("accused_name", "")
                        )
                        if (
                            other_accused
                            and accused
                            and other_accused != accused
                        ):
                            graph.add_edge(
                                accused,
                                other_accused,
                                basis="co_accused_field",
                                detail=f"co-accused linked via cases {case_id} and {linked_id}",
                                source_cases=[case_id, linked_id],
                            )

    # --- Same address links ---
    # If two different people share the same address, connect them
    for address, people in address_groups.items():
        if len(people) >= 2:
            for i in range(len(people)):
                for j in range(i + 1, len(people)):
                    name_a = people[i]["name"]
                    name_b = people[j]["name"]
                    if name_a and name_b and not is_fuzzy_match(name_a, name_b):
                        graph.add_edge(
                            name_a,
                            name_b,
                            basis="same_address",
                            detail=f"both linked to address: {address}",
                            source_cases=[
                                people[i]["case_id"],
                                people[j]["case_id"],
                            ],
                        )

    # --- Same phone links ---
    # If two different people share the same phone number, connect them
    for phone, people in phone_groups.items():
        if len(people) >= 2:
            for i in range(len(people)):
                for j in range(i + 1, len(people)):
                    name_a = people[i]["name"]
                    name_b = people[j]["name"]
                    if name_a and name_b and not is_fuzzy_match(name_a, name_b):
                        graph.add_edge(
                            name_a,
                            name_b,
                            basis="same_phone",
                            detail=f"both use phone: {phone}",
                            source_cases=[
                                people[i]["case_id"],
                                people[j]["case_id"],
                            ],
                        )

    # --- Fuzzy name matching across cases ---
    # Catch the same person appearing with slightly different name spellings
    all_names = list(name_to_cases.keys())
    for i in range(len(all_names)):
        for j in range(i + 1, len(all_names)):
            if is_fuzzy_match(all_names[i], all_names[j]):
                # Same person, different name variant — merge via edge
                graph.add_edge(
                    all_names[i],
                    all_names[j],
                    basis="fuzzy_name_match",
                    detail=f"'{all_names[i]}' ≈ '{all_names[j]}' (similarity >= {FUZZY_THRESHOLD})",
                    source_cases=name_to_cases[all_names[i]]
                    + name_to_cases[all_names[j]],
                )


# ===================================================================
# MECHANISM 2: NARRATIVE NER EXTRACTION
# ===================================================================
# Run NER on each record's free-text description to find person names
# that may NOT be in the structured columns. This catches mentions
# like "witness Ramesh saw the accused with Sunil" where Sunil isn't
# listed anywhere in the structured fields.
#
# Two implementations:
#   - spaCy NER (preferred, more accurate)
#   - Regex fallback (capitalized word sequences, less accurate but
#     works without any ML library installed)
# ===================================================================

def extract_names_spacy(text: str) -> list[str]:
    """Extract PERSON entities using spaCy's NER model."""
    doc = get_spacy_nlp()(text)
    return [
        normalize_name(ent.text)
        for ent in doc.ents
        if ent.label_ == "PERSON" and len(ent.text.strip()) > 2
    ]


def extract_names_regex(text: str) -> list[str]:
    """
    Fallback: extract likely person names using regex.
    Pattern: 2-3 consecutive capitalized words not at sentence start.
    Less accurate than spaCy but requires no ML dependencies.
    """
    # Find sequences of 2-3 capitalized words
    pattern = r"(?<![.!?]\s)\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b"
    matches = re.findall(pattern, text)

    # Filter out common non-name phrases
    stopwords = {
        "The Police", "Crime Branch", "Gold Chain", "Ring Road",
        "Brigade Road", "Wilson Garden", "MG Road", "KR Circle",
        "Mobile Phone", "Crime Scene",
    }
    return [
        normalize_name(m) for m in matches
        if m not in stopwords and len(m.strip()) > 3
    ]


def extract_narrative_links(records: list[dict], graph: nx.Graph) -> None:
    """
    Run NER (or regex fallback) on every record's description.
    Add any newly discovered person names as nodes, and connect
    them to the record's accused if they co-occur in the same narrative.
    """
    nlp_inst = get_spacy_nlp()
    extract_fn = extract_names_spacy if (nlp_inst is not None and NER_AVAILABLE) else extract_names_regex

    for record in records:
        case_id = record.get("case_id", "unknown")
        accused = normalize_name(record.get("accused_name", ""))
        description = record.get("description", "")

        if not description:
            continue

        # Extract names from the narrative
        narrative_names = extract_fn(description)

        for name in narrative_names:
            if not name or name.lower() in ("na", "unknown"):
                continue

            # Skip if this is the accused themselves
            if is_fuzzy_match(name, accused):
                continue

            # Add as a node (source: narrative)
            if not graph.has_node(name):
                graph.add_node(
                    name, type="narrative_entity", cases=[case_id]
                )
            else:
                # Node exists — just tag that it also appeared in narrative
                if case_id not in graph.nodes[name].get("cases", []):
                    graph.nodes[name].setdefault("cases", []).append(case_id)

            # Connect to the accused in this case
            if accused and not graph.has_edge(accused, name):
                graph.add_edge(
                    accused,
                    name,
                    basis="narrative_mention",
                    detail=f"both mentioned in description of case {case_id}",
                    source_cases=[case_id],
                )


# ===================================================================
# GRAPH ANALYSIS — extract useful insights from the built graph
# ===================================================================

def analyze_graph(graph: nx.Graph, query_entities: list[str]) -> dict:
    """
    Run graph analysis relevant to the investigator's question:
      - Connected components (who's in the same network)
      - High-degree nodes (people with many connections = hubs)
      - Shortest paths between query-relevant entities
    """
    analysis = {
        "total_nodes": graph.number_of_nodes(),
        "total_edges": graph.number_of_edges(),
        "components": [],
        "hub_nodes": [],
    }

    # Find connected components (clusters of linked people)
    for component in nx.connected_components(graph):
        members = list(component)
        analysis["components"].append({
            "size": len(members),
            "members": members,
        })

    # Find hub nodes (people with the most connections)
    if graph.number_of_nodes() > 0:
        degree_sorted = sorted(
            graph.degree(), key=lambda x: x[1], reverse=True
        )
        # Top 5 most connected people
        analysis["hub_nodes"] = [
            {"name": name, "connections": degree}
            for name, degree in degree_sorted[:5]
            if degree > 0
        ]

    # Shortest paths between query-relevant entities (if multiple)
    if len(query_entities) >= 2:
        paths = []
        for i in range(len(query_entities)):
            for j in range(i + 1, len(query_entities)):
                src, tgt = query_entities[i], query_entities[j]
                if graph.has_node(src) and graph.has_node(tgt):
                    try:
                        path = nx.shortest_path(graph, src, tgt)
                        paths.append({
                            "from": src, "to": tgt,
                            "path": path, "length": len(path) - 1,
                        })
                    except nx.NetworkXNoPath:
                        paths.append({
                            "from": src, "to": tgt,
                            "path": None, "length": -1,
                        })
        analysis["shortest_paths"] = paths

    return analysis


# ===================================================================
# MAIN FUNCTION — the link_agent entry point
# ===================================================================

def link_agent(state: dict) -> dict:
    """
    Link Agent — build the criminal network graph.

    Reads:  state["records_found"] — records from Query Agent

    Writes: state["entities_found"]  — list of person nodes with metadata
            state["network_edges"]   — list of connections with basis tags
            state["network_graph"]   — the NetworkX graph object (for Risk Agent)
            state["network_analysis"] — graph stats and insights

    TECHNIQUE SUMMARY:
      1. Build empty NetworkX graph
      2. Run structured field matching (address, phone, co-accused, fuzzy name)
      3. Run NER/regex on descriptions to find hidden entity mentions
      4. Analyze the graph (components, hubs, paths)
      5. Export nodes/edges with basis tags to state
    """
    records = state.get("records_found", [])

    if not records:
        state["entities_found"] = []
        state["network_edges"] = []
        state["network_graph"] = None
        state["network_analysis"] = {"total_nodes": 0, "total_edges": 0}
        print("[LinkAgent] No records to process.")
        return state

    print(f"[LinkAgent] Processing {len(records)} records...")

    # --- Step 1: Create empty graph ---
    graph = nx.Graph()

    # --- Step 2: Structured field matching ---
    # Compare accused_name, address, phone, co_accused_ids across records
    extract_structured_links(records, graph)
    print(
        f"[LinkAgent] After structured matching: "
        f"{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges"
    )

    # --- Step 3: NER extraction from descriptions ---
    # Find person names in free-text that aren't in structured columns
    extract_narrative_links(records, graph)
    ner_method = "spaCy NER" if NER_AVAILABLE else "regex fallback"
    print(
        f"[LinkAgent] After narrative extraction ({ner_method}): "
        f"{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges"
    )

    # --- Step 4: Analyze the graph ---
    # Collect names of accused in the query results as "query entities"
    query_entities = [
        normalize_name(r.get("accused_name", ""))
        for r in records
        if r.get("accused_name")
    ]
    query_entities = list(set(e for e in query_entities if e))

    analysis = analyze_graph(graph, query_entities)
    print(
        f"[LinkAgent] Graph has {analysis['total_nodes']} nodes, "
        f"{analysis['total_edges']} edges, "
        f"{len(analysis['components'])} components"
    )

    # --- Step 5: Export to state ---
    # Convert graph to serializable format for the frontend / verifier

    entities_found = []
    for node, data in graph.nodes(data=True):
        entities_found.append({
            "id": node,
            "name": node,
            "type": data.get("type", "unknown"),
            "cases": data.get("cases", []),
            "basis": data.get("type", "structured"),
        })

    network_edges = []
    for src, tgt, data in graph.edges(data=True):
        network_edges.append({
            "source": src,
            "target": tgt,
            "basis": data.get("basis", "unknown"),
            "detail": data.get("detail", ""),
            "source_cases": data.get("source_cases", []),
        })

    state["entities_found"] = entities_found
    state["network_edges"] = network_edges
    state["network_graph"] = graph  # keep the object for Risk Agent
    state["network_analysis"] = analysis

    print(f"[LinkAgent] Done. {len(entities_found)} entities, {len(network_edges)} edges written to state.")

    return state
