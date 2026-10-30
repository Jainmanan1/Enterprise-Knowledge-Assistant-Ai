"""
Self-contained retrieval test. Needs the MCP server running.
Run from backend/:  python check_retrieval.py
"""








def main() -> None:
    import uuid

    from _bootstrap import prepare_backend

    prepare_backend()

    from app.chat.mcp_client import call_tool_sync
    from app.documents.indexer import create_mcp_token
    run = uuid.uuid4().hex[:6]
    USER_A = f"test-a-{run}"
    USER_B = f"test-b-{run}"
    ADMIN = f"test-admin-{run}"

    A1, A2, B1 = f"doc-a1-{run}", f"doc-a2-{run}", f"doc-b1-{run}"
    V = "v1"
    RARE_IDX, SEM_IDX = 11, 5
    failures: list[str] = []
    FILLER = [
    "The quarterly planning meeting covers hiring targets and budget allocation for each department.",
    "Employees should submit expense reports within thirty days of travel using the finance portal.",
    "The office kitchen is cleaned every evening and recycling is collected on Thursday mornings.",
    "Our security policy requires multi-factor authentication for all remote access to internal systems.",
    "New hires complete onboarding training covering company values, tools and communication norms.",
    "The design team reviews wireframes weekly and records feedback in the shared project tracker.",
    "Customer interviews are scheduled monthly to gather product feedback from enterprise clients.",
    "Backups of the production database run nightly and are retained for ninety days.",
    "Annual leave requests must be approved by a manager at least two weeks in advance.",
    "The engineering handbook describes code review expectations and the release checklist.",
    "Meeting rooms can be booked through the calendar system and released if unused after ten minutes.",
    "Vendors must complete a security questionnaire before they receive access to company data.",
]

    A1_CHUNKS = [f"Section {i}. {FILLER[i % len(FILLER)]} Reference note {i}." for i in range(24)]
    A1_CHUNKS[RARE_IDX] = "Troubleshooting guide: when the billing service returns ERR-4471-XJ, restart the sync worker and verify the queue depth."
    A1_CHUNKS[SEM_IDX] = "Refund requests are escalated when a card transaction is declined at checkout."
    A2_CHUNKS = [
        "Appendix: error code ZETA-9901 means the nightly export job timed out.",
        "Appendix: the export job writes CSV files to the shared reporting bucket.",
        "Appendix: exports older than ninety days are archived automatically.",
    ]
    B1_CHUNKS = [
        "Confidential: the vault passphrase label is SECRET-B-7788 and rotates quarterly.",
        "Confidential: only the platform team may rotate vault credentials.",
        "Confidential: audit logs for vault access are reviewed monthly.",
    ]

    MAP_A = {A1: V, A2: V}
    MODES = ("dense", "bm25", "hybrid")
    def tok(uid, role="employee"):
        return create_mcp_token(uid, role)


    def index(uid, doc_id, name, chunks):
        return call_tool_sync("index_document", {
            "owner_id": uid, "document_id": doc_id, "filename": name,
            "chunks": chunks, "version_id": V, "auth_token": tok(uid)})


    def search(owner, query, mapping, mode, k=5, actor=None, role="employee"):
        return call_tool_sync("search_document", {
            "owner_id": owner, "query": query, "active_versions": mapping,
            "k": k, "mode": mode, "auth_token": tok(actor or owner, role)})


    def ids(hits):
        return [(h["document_id"], h["chunk_index"]) for h in hits]

    def deleted(uid, doc_id):
        return call_tool_sync("delete_document", {"document_id": doc_id, "auth_token": tok(uid)})

    def check(name, ok, detail=""):
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))
        if not ok:
            failures.append(name)

    try:
        print("Indexing test data (1-2 minutes)...")
        index(USER_A, A1, "a1.txt", A1_CHUNKS)
        index(USER_A, A2, "a2.txt", A2_CHUNKS)
        index(USER_B, B1, "b1.txt", B1_CHUNKS)
        RARE = (A1, RARE_IDX)
        Q_RARE = "ERR-4471-XJ"

        r = search(USER_A, Q_RARE, MAP_A, "bm25")
        check("1  bm25 ranks the rare-token chunk first", bool(r) and ids(r)[0] == RARE, f"got {ids(r)[:3]}")

        r = search(USER_A, Q_RARE, MAP_A, "hybrid", k=3)
        check("2  hybrid has the rare-token chunk in its top 3", RARE in ids(r), f"got {ids(r)}")

        r = search(USER_A, "customer payment keeps failing", MAP_A, "dense", k=3)
        ok = (A1, SEM_IDX) in ids(r)
        check("3  dense finds the refund/declined-card chunk by meaning",ok,f"got {ids(r)}",)

        r = search(USER_A, Q_RARE, MAP_A, "dense", k=10)
        pos = ids(r).index(RARE) + 1 if RARE in ids(r) else None
        print(f"INFO  4  dense-only rank of the rare-token chunk: {pos}  (BM25 gets it at rank 1)")

        for m in MODES:
            r = search(USER_A, Q_RARE, {A1: "bogus", A2: V}, m)
            check(f"5  {m}: bogus active version excludes doc A1", all(d != A1 for d, _ in ids(r)), f"got {ids(r)}")

        for m in MODES:
            r = search(USER_A, Q_RARE, {A2: V}, m)
            check(f"6  {m}: doc absent from mapping is excluded", all(d != A1 for d, _ in ids(r)), f"got {ids(r)}")

        for m in MODES:
            try:
                r = search(USER_A, Q_RARE, {A1: V}, m)
                ok = bool(r) if m == "bm25" else True
                check(f"7  {m}: works with exactly one active doc", ok, f"got {ids(r)[:3]}")
            except Exception as e:
                check(f"7  {m}: works with exactly one active doc", False, str(e)[:90])

        for m in MODES:
            check(f"8  {m}: empty mapping returns []", search(USER_A, Q_RARE, {}, m) == [])

        for m in MODES:
            r = search(USER_A, "SECRET-B-7788", {B1: V}, m)
            check(f"9  {m}: user A cannot read B's doc via the mapping", r == [], f"got {ids(r)}")

        try:
            search(USER_B, "SECRET-B-7788", {B1: V}, "hybrid", actor=USER_A)
            check("10 employee token cannot search another owner", False, "request was accepted")
        except Exception:
            check("10 employee token cannot search another owner", True)

        r = search(USER_A, Q_RARE, MAP_A, "bm25", actor=ADMIN, role="admin")
        check("11 admin token can search a tenant", RARE in ids(r), f"got {ids(r)[:3]}")

        before = search(USER_A, "ZETA-9901", MAP_A, "bm25")
        check("12a bm25 finds the A2 chunk before deleting", (A2, 0) in ids(before), f"got {ids(before)}")
        res = deleted(USER_A, A2)
        check("12b delete removed all 3 chunks", res.get("deleted_chunks") == 3, str(res))
        after = search(USER_A, "ZETA-9901", MAP_A, "bm25")
        check("12c bm25 no longer returns the deleted doc", all(d != A2 for d, _ in ids(after)), f"got {ids(after)}")

    finally:
        print("Cleaning up test data...")
        for uid, doc in ((USER_A, A1), (USER_A, A2), (USER_B, B1)):
            try:
                deleted(uid, doc)
            except Exception as e:
                print(f"  cleanup warning for {doc}: {str(e)[:80]}")

    print()
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED:")
        for failure in failures:
            print("  -", failure)
        raise SystemExit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
