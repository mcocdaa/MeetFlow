def test_representative_mutation_routes_require_authentication(client):
    mutations = [
        ("/api/projects", {"name": "Private", "slug": "private"}),
        (
            "/api/projects/project-id/meetings",
            {
                "title": "Private meeting",
                "scheduled_start": "2026-07-22T09:00:00Z",
                "scheduled_end": "2026-07-22T10:00:00Z",
            },
        ),
        (
            "/api/meetings/meeting-id/agenda-items?expected_meeting_version=1",
            {"title": "Private topic", "agenda_type": "discussion"},
        ),
        (
            "/api/projects/project-id/decisions",
            {"title": "Private decision", "decision_markdown": "Not public"},
        ),
    ]

    for path, payload in mutations:
        assert client.post(path, json=payload).status_code == 401
