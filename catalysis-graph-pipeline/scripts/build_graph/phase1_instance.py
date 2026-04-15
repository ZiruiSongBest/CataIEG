"""Phase 1: 从 sample.jsonl 解析实例层节点和边"""
import json
from config import normalize_doi


def build_instance_layer(papers: list[dict]) -> tuple[list[dict], list[dict]]:
    nodes, edges = [], []

    for paper in papers:
        doi = paper["DOI"]
        doi_norm = normalize_doi(doi)
        title = paper.get("title", "")
        time_arr = paper.get("time", [])
        year = time_arr[0] if time_arr else None
        paper_uid = f"paper:{doi_norm}"

        # --- Paper 节点 ---
        nodes.append({
            "uid": paper_uid, "node_type": "Paper",
            "doi": doi, "title": title, "year": year,
        })

        # --- Reaction 节点 ---
        for r in paper["task1"].get("reaction_catalog", []):
            rid = r["reaction_id"]
            r_uid = f"reaction:{doi_norm}:{rid}"
            nodes.append({
                "uid": r_uid, "node_type": "Reaction", "local_id": rid,
                "reaction_name_reported": r.get("reaction_name_reported", ""),
                "transformation": r.get("transformation", ""),
                "reaction_domain": r.get("reaction_domain", ""),
                "reaction_class": r.get("reaction_class", ""),
                "reaction_family": r.get("reaction_family", []),
                "reactants": r.get("reactants", []),
                "target_products": r.get("target_products", []),
                "is_primary_reaction": r.get("is_primary_reaction", ""),
            })
            edges.append({"source": paper_uid, "target": r_uid, "edge_type": "HAS_REACTION"})

        # --- Catalyst 节点 ---
        for c in paper["task2"].get("catalyst_catalog", []):
            cid = c["catalyst_id"]
            c_uid = f"catalyst:{doi_norm}:{cid}"
            nodes.append({
                "uid": c_uid, "node_type": "Catalyst", "local_id": cid,
                "name_reported": c.get("name_reported", ""),
                "aliases": c.get("aliases", []),
                "substrate_or_support": c.get("substrate_or_support", ""),
                "tested_reaction_ids": c.get("tested_reaction_ids", []),
                "labels_material_platform": c.get("labels_material_platform", []),
                "labels_active_site_form": c.get("labels_active_site_form", []),
                "labels_morphology_device_form": c.get("labels_morphology_device_form", []),
                "form_factor": c.get("form_factor", []),
                "role": c.get("role", ""),
                "series_name": c.get("series_name", ""),
                "variant_rule": c.get("variant_rule", ""),
                "variant_value": c.get("variant_value", ""),
            })
            edges.append({"source": paper_uid, "target": c_uid, "edge_type": "HAS_CATALYST"})

            # Catalyst --TESTED_IN--> Reaction
            for rxn_id in c.get("tested_reaction_ids", []):
                r_uid = f"reaction:{doi_norm}:{rxn_id}"
                edges.append({"source": c_uid, "target": r_uid, "edge_type": "TESTED_IN"})

        # --- Procedure + ProcedureStep 节点 ---
        for p in paper["task3"].get("procedure_catalog", []):
            pid = p["procedure_id"]
            p_uid = f"procedure:{doi_norm}:{pid}"
            nodes.append({
                "uid": p_uid, "node_type": "Procedure", "local_id": pid,
                "procedure_type": p.get("procedure_type", ""),
                "name_reported": p.get("name_reported", ""),
                "catalyst_ids": p.get("catalyst_ids", []),
                "reaction_ids": p.get("reaction_ids", []),
            })
            edges.append({"source": paper_uid, "target": p_uid, "edge_type": "HAS_PROCEDURE"})

            # Procedure --APPLIES_TO--> Catalyst
            for cat_id in p.get("catalyst_ids", []):
                edges.append({
                    "source": p_uid,
                    "target": f"catalyst:{doi_norm}:{cat_id}",
                    "edge_type": "APPLIES_TO",
                })

            # Procedure --SPECIFIC_TO--> Reaction
            for rxn_id in p.get("reaction_ids", []):
                if rxn_id:
                    edges.append({
                        "source": p_uid,
                        "target": f"reaction:{doi_norm}:{rxn_id}",
                        "edge_type": "SPECIFIC_TO",
                    })

            # ProcedureStep 节点
            steps = p.get("steps", [])
            prev_step_uid = None
            for s in steps:
                sno = s.get("step_no", 0)
                s_uid = f"step:{doi_norm}:{pid}:S{sno}"
                nodes.append({
                    "uid": s_uid, "node_type": "ProcedureStep",
                    "procedure_uid": p_uid, "step_no": sno,
                    "step_type": s.get("step_type", ""),
                    "method_details": s.get("method_details", ""),
                    "inputs": s.get("inputs", []),
                    "parameters": s.get("parameters", {}),
                    "output_intermediate": s.get("output_intermediate", ""),
                })
                edges.append({"source": p_uid, "target": s_uid, "edge_type": "HAS_STEP"})
                if prev_step_uid:
                    edges.append({"source": prev_step_uid, "target": s_uid, "edge_type": "NEXT_STEP"})
                prev_step_uid = s_uid

        # --- CharacterizationRecord 节点 ---
        for cr in paper["task4"].get("characterization_records", []):
            cr_id = cr.get("record_id", "")
            cr_uid = f"char:{doi_norm}:{cr_id}"
            nodes.append({
                "uid": cr_uid, "node_type": "CharacterizationRecord", "local_id": cr_id,
                "catalyst_id": cr.get("catalyst_id", ""),
                "applies_to_catalyst_ids": cr.get("applies_to_catalyst_ids", []),
                "sample_state": cr.get("sample_state", ""),
                "reaction_id": cr.get("reaction_id", ""),
                "method_family": cr.get("method_family", ""),
                "method_name_reported": cr.get("method_name_reported", ""),
                "results": cr.get("results", []),
            })
            edges.append({"source": paper_uid, "target": cr_uid, "edge_type": "HAS_CHARACTERIZATION"})

            # CharRecord --APPLIES_TO_CATALYST--> Catalyst
            main_cat = cr.get("catalyst_id", "")
            if main_cat:
                # catalyst_id 可能是 str 或 list
                cat_ids = main_cat if isinstance(main_cat, list) else [main_cat]
                for cid in cat_ids:
                    if cid:
                        edges.append({
                            "source": cr_uid,
                            "target": f"catalyst:{doi_norm}:{cid}",
                            "edge_type": "APPLIES_TO_CATALYST",
                        })
            for cid in cr.get("applies_to_catalyst_ids", []):
                if cid:
                    edges.append({
                        "source": cr_uid,
                        "target": f"catalyst:{doi_norm}:{cid}",
                        "edge_type": "APPLIES_TO_CATALYST",
                    })

            # CharRecord --LINKED_TO_REACTION--> Reaction
            rxn_id = cr.get("reaction_id", "")
            if rxn_id:
                edges.append({
                    "source": cr_uid,
                    "target": f"reaction:{doi_norm}:{rxn_id}",
                    "edge_type": "LINKED_TO_REACTION",
                })

        # --- PerformanceDataset / OperatingPoint / Metric ---
        for pr in paper["task5"].get("performance_records", []):
            pr_id = pr.get("dataset_id", "")
            pr_uid = f"perf:{doi_norm}:{pr_id}"
            nodes.append({
                "uid": pr_uid, "node_type": "PerformanceDataset", "local_id": pr_id,
                "reaction_id": pr.get("reaction_id", ""),
                "dataset_type": pr.get("dataset_type", ""),
                "common_conditions": pr.get("common_conditions", {}),
            })
            edges.append({"source": paper_uid, "target": pr_uid, "edge_type": "HAS_PERFORMANCE_DATASET"})

            # Reaction --HAS_PERFORMANCE_DATASET--> PerfDataset
            rxn_id = pr.get("reaction_id", "")
            if rxn_id:
                edges.append({
                    "source": f"reaction:{doi_norm}:{rxn_id}",
                    "target": pr_uid,
                    "edge_type": "HAS_PERFORMANCE_DATASET",
                })

            for op in pr.get("operating_points", []):
                op_id = op.get("point_id", "")
                op_uid = f"op:{doi_norm}:{pr_id}:{op_id}"
                nodes.append({
                    "uid": op_uid, "node_type": "OperatingPoint",
                    "point_id": op_id,
                    "point_conditions": op.get("point_conditions", {}),
                })
                edges.append({"source": pr_uid, "target": op_uid, "edge_type": "HAS_OPERATING_POINT"})

                for mbci, mbc in enumerate(op.get("metrics_by_catalyst", []), 1):
                    cat_id = mbc.get("catalyst_id", "")
                    cat_state = mbc.get("catalyst_state_during_test", "")
                    state_notes = mbc.get("state_notes", "")
                    cat_token = cat_id or "NA"

                    for mi, m in enumerate(mbc.get("metrics", []), 1):
                        m_uid = f"metric:{doi_norm}:{pr_id}:{op_id}:{cat_token}:B{mbci}:M{mi}"
                        nodes.append({
                            "uid": m_uid, "node_type": "Metric",
                            "catalyst_id": cat_id,
                            "reaction_id": rxn_id,
                            "catalyst_state_during_test": cat_state,
                            "state_notes": state_notes,
                            "property_name": m.get("property_name", ""),
                            "target_species": m.get("target_species", ""),
                            "basis": m.get("basis", ""),
                            "value": m.get("value", ""),
                            "unit": m.get("unit", ""),
                            "notes": m.get("notes", ""),
                        })
                        # OP --HAS_METRIC--> Metric
                        edges.append({"source": op_uid, "target": m_uid, "edge_type": "HAS_METRIC"})
                        # Metric --FOR_CATALYST--> Catalyst
                        if cat_id:
                            edges.append({
                                "source": m_uid,
                                "target": f"catalyst:{doi_norm}:{cat_id}",
                                "edge_type": "FOR_CATALYST",
                            })
                        # Metric --UNDER_REACTION--> Reaction
                        if rxn_id:
                            edges.append({
                                "source": m_uid,
                                "target": f"reaction:{doi_norm}:{rxn_id}",
                                "edge_type": "UNDER_REACTION",
                            })

        # --- MechanisticClaim + EvidenceItem 节点 (task6) ---
        task6 = paper.get("task6", {})
        for mc in task6.get("mechanistic_claims", []):
            mc_id = mc.get("claim_id", "")
            mc_uid = f"claim:{doi_norm}:{mc_id}"
            nodes.append({
                "uid": mc_uid, "node_type": "MechanisticClaim", "local_id": mc_id,
                "reaction_id": mc.get("reaction_id", ""),
                "catalyst_id": mc.get("catalyst_id", ""),
                "applies_to_catalyst_ids": mc.get("applies_to_catalyst_ids", []),
                "claim_type": mc.get("claim_type", ""),
                "design_mechanism_tags": mc.get("design_mechanism_tags", []),
                "claim_summary": mc.get("claim_summary", ""),
            })
            # Paper --HAS_MECHANISTIC_CLAIM--> MechanisticClaim
            edges.append({"source": paper_uid, "target": mc_uid, "edge_type": "HAS_MECHANISTIC_CLAIM"})

            # MechanisticClaim --ABOUT_REACTION--> Reaction
            mc_rxn = mc.get("reaction_id", "")
            if mc_rxn:
                edges.append({
                    "source": mc_uid,
                    "target": f"reaction:{doi_norm}:{mc_rxn}",
                    "edge_type": "ABOUT_REACTION",
                })

            # MechanisticClaim --APPLIES_TO_CATALYST--> Catalyst
            mc_cat = mc.get("catalyst_id", "")
            if mc_cat:
                edges.append({
                    "source": mc_uid,
                    "target": f"catalyst:{doi_norm}:{mc_cat}",
                    "edge_type": "APPLIES_TO_CATALYST",
                })
            for extra_cat in mc.get("applies_to_catalyst_ids", []):
                if extra_cat and extra_cat != mc_cat:
                    edges.append({
                        "source": mc_uid,
                        "target": f"catalyst:{doi_norm}:{extra_cat}",
                        "edge_type": "APPLIES_TO_CATALYST",
                    })

            # EvidenceItem 节点
            for ei_idx, ei in enumerate(mc.get("evidence_chain", []), 1):
                ei_uid = f"evidence:{doi_norm}:{mc_id}:E{ei_idx}"
                nodes.append({
                    "uid": ei_uid, "node_type": "EvidenceItem",
                    "claim_id": mc_id,
                    "evidence_type": ei.get("evidence_type", ""),
                    "evidence_summary": ei.get("evidence_summary", ""),
                    "linked_characterization_record_ids": ei.get("linked_characterization_record_ids", []),
                    "linked_performance_dataset_ids": ei.get("linked_performance_dataset_ids", []),
                    "linked_procedure_ids": ei.get("linked_procedure_ids", []),
                })
                # MechanisticClaim --HAS_EVIDENCE--> EvidenceItem
                edges.append({"source": mc_uid, "target": ei_uid, "edge_type": "HAS_EVIDENCE"})

                # EvidenceItem --SUPPORTED_BY--> CharacterizationRecord
                for cr_ref in ei.get("linked_characterization_record_ids", []):
                    if cr_ref:
                        edges.append({
                            "source": ei_uid,
                            "target": f"char:{doi_norm}:{cr_ref}",
                            "edge_type": "SUPPORTED_BY",
                        })
                # EvidenceItem --SUPPORTED_BY--> PerformanceDataset
                for pr_ref in ei.get("linked_performance_dataset_ids", []):
                    if pr_ref:
                        edges.append({
                            "source": ei_uid,
                            "target": f"perf:{doi_norm}:{pr_ref}",
                            "edge_type": "SUPPORTED_BY",
                        })
                # EvidenceItem --SUPPORTED_BY--> Procedure
                for p_ref in ei.get("linked_procedure_ids", []):
                    if p_ref:
                        edges.append({
                            "source": ei_uid,
                            "target": f"procedure:{doi_norm}:{p_ref}",
                            "edge_type": "SUPPORTED_BY",
                        })

    return nodes, edges
