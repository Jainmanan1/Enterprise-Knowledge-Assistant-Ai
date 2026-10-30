
EVAL_CASES = [
    {
        "query": "How many annual leave days do employees receive?",
        "owner_id": "user-1",
        "active_versions": {
            "doc-1": "v2",
            "doc-2": "v1",
        },
        "expected_chunks": [
            ("doc-1", "v2", 0),
        ],
    },
    {
        "query": "Who approves a leave request?",
        "owner_id": "user-1",
        "active_versions": {
            "doc-1": "v2",
            "doc-2": "v1",
        },
        "expected_chunks": [
            ("doc-1", "v2", 1),
        ],
    },
    {
        "query": "Can employees work remotely?",
        "owner_id": "user-1",
        "active_versions": {
            "doc-1": "v2",
            "doc-2": "v1",
        },
        "expected_chunks": [
            ("doc-2", "v1", 0),
        ],
    },
]
