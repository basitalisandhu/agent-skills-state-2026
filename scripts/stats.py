import csv, json, statistics, sys, os
W = sys.argv[1]
R = list(csv.DictReader(open(os.path.join(W, "out", "dataset.csv"))))
B = lambda v: v == "True"; I = lambda v: int(v) if v not in ("", None) else 0
n = len(R)
sk = [r for r in R if I(r["n_skill_md"]) > 0]
hk = [r for r in R if I(r["n_hooks"]) > 0]
mc = [r for r in R if I(r["n_mcp_stdio"]) > 0]
def pc(a, b): return f"{a}/{b} ({100*a/b:.1f}%)" if b else f"{a}/0 (0.0%)"
out = {}
out["repos"] = n
out["repos_with_skills"] = len(sk)
out["has_plugin_json"] = sum(B(r["has_plugin_json"]) for r in R)
out["has_marketplace_json"] = sum(B(r["has_marketplace_json"]) for r in R)
out["has_server_json"] = sum(B(r["has_server_json"]) for r in R)
out["has_mcp_json"] = sum(B(r["has_mcp_json"]) for r in R)
out["repos_with_hooks"] = len(hk); out["repos_with_stdio_mcp"] = len(mc)
counts = sorted((I(r["n_skill_md"]) for r in sk), reverse=True)
out["skill_md_total"] = sum(counts); out["skill_md_median_per_repo"] = statistics.median(counts) if counts else 0
top = counts[: max(1, len(counts)//100)]
out["share_skill_md_in_top_1pct_repos"] = f"{100*sum(top)/max(1, sum(counts)):.1f}% in {len(top)} repos"
out["owner_org"] = sum(r["owner_type"] == "Organization" for r in R)
st = sorted(I(r["stars"]) for r in R); out["stars_median"] = statistics.median(st) if st else 0; out["repos_100plus_stars"] = sum(s >= 100 for s in st)
out["created_2026"] = sum((r["created_at"] or "").startswith("2026") for r in R)
out["unpinned_mcp"] = pc(sum(B(r["any_unpinned_mcp"]) for r in mc), len(mc))
out["unpinned_mcp_latest"] = pc(sum(I(r["SSG403"]) > 0 for r in mc), len(mc))
out["unpinned_mcp_npm"] = pc(sum(I(r["SSG401"]) > 0 for r in mc), len(mc))
out["unpinned_mcp_py"] = pc(sum(I(r["SSG402"]) > 0 for r in mc), len(mc))
out["no_security_md"] = pc(sum(B(r["no_security_md"]) for r in R), n)
out["no_security_policy_github"] = pc(sum(r["github_security_policy"] != "True" for r in R), n)
out["no_licence_file"] = pc(sum(B(r["no_licence_file"]) for r in R), n)
out["no_licence_github"] = pc(sum(not r["github_licence_spdx"] for r in R), n)
out["unrestricted_bash_repos"] = pc(sum(B(r["any_unrestricted_bash"]) for r in sk), len(sk))
out["unrestricted_bash_findings"] = sum(I(r["SSG607"]) for r in R)
out["yaml_reject_repos"] = pc(sum(B(r["any_yaml_reject"]) for r in sk), len(sk))
out["yaml_reject_skills"] = pc(sum(I(r["n_skill_yaml_reject"]) for r in sk), out["skill_md_total"])
out["no_front_matter_skills"] = pc(sum(I(r["n_skill_no_front_matter"]) for r in sk), out["skill_md_total"])
out["no_front_matter_repos"] = pc(sum(I(r["n_skill_no_front_matter"]) > 0 for r in sk), len(sk))
out["desc_over_1024_repos"] = pc(sum(B(r["any_desc_over_1024"]) for r in sk), len(sk))
out["desc_over_1024_skills"] = pc(sum(I(r["n_skill_desc_over_1024"]) for r in sk), sum(I(r["n_skill_with_desc"]) for r in sk))
out["hook_flag_all"] = sum(B(r["hook_network_flag"]) for r in R)
out["hook_flag_in_hook_repos"] = pc(sum(B(r["hook_network_flag"]) for r in hk), len(hk))
for v in ("remote", "local", "unclear", "not-network"):
    out["hook_review_" + v] = sum(r["hook_network_review"] == v for r in R)
    out["hook_review_" + v + "_in_hook_repos"] = sum(r["hook_network_review"] == v for r in hk)
out["ssg601_noname_manifest"] = sum(I(r["SSG601"]) > 0 for r in R)
out["ssg606_invalid_json_repos"] = sum(I(r["SSG606"]) > 0 for r in R)
out["portability_any"] = pc(sum(I(r["n_portability_findings"]) > 0 for r in sk), len(sk))
# chart 2: by star band
bands = [("0", 0, 0), ("1-9", 1, 9), ("10-99", 10, 99), ("100+", 100, 10**9)]
c2 = []
for name, lo, hi in bands:
    g = [r for r in R if lo <= I(r["stars"]) <= hi]
    ng = max(1, len(g))  # a band can be empty in a small dry run
    c2.append({"band": name, "repos": len(g), "no_security_md_pct": round(100*sum(B(r["no_security_md"]) for r in g)/ng, 1),
               "no_licence_pct": round(100*sum(B(r["no_licence_file"]) for r in g)/ng, 1),
               "mcp_repos": sum(I(r["n_mcp_stdio"]) > 0 for r in g),
               "unpinned_mcp_pct": round(100*sum(B(r["any_unpinned_mcp"]) for r in g if I(r["n_mcp_stdio"]) > 0)/max(1, sum(I(r["n_mcp_stdio"]) > 0 for r in g)), 1)})
out["chart2"] = c2
json.dump(out, open(os.path.join(W, "out", "stats.json"), "w"), indent=1)
for k, v in out.items(): print(k, ":", v)
