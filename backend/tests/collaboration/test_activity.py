def _create_project(client, *, name: str, slug: str) -> dict:
    actor = client.get("/api/auth/me").json()
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "slug": slug,
            "status": "active",
            "lead_user_id": actor["id"],
            "member_ids": [actor["id"]],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_activity_is_committed_with_mutation_but_not_stale_failure(
    authenticated_client,
):
    actor = authenticated_client.get("/api/auth/me").json()
    project = _create_project(
        authenticated_client, name="Atomic activity", slug="atomic-activity"
    )

    updated = authenticated_client.put(
        f"/api/projects/{project['id']}",
        json={"expected_version": project["version"], "summary": "Visible change"},
    )
    assert updated.status_code == 200

    activity = authenticated_client.get(f"/api/projects/{project['id']}/activity")
    assert activity.status_code == 200
    items = activity.json()["items"]
    assert items[0]["event_type"] == "project.updated"
    assert items[0]["actor"]["id"] == actor["id"]
    assert items[0]["subject"] == {"type": "project", "id": project["id"]}

    before_count = len(items)
    stale = authenticated_client.put(
        f"/api/projects/{project['id']}",
        json={"expected_version": project["version"], "summary": "Stale change"},
    )
    assert stale.status_code == 409
    after = authenticated_client.get(f"/api/projects/{project['id']}/activity").json()
    assert len(after["items"]) == before_count


def test_activity_api_is_project_scoped_and_gap_free(authenticated_client, client):
    first = _create_project(
        authenticated_client, name="First activity", slug="first-activity"
    )
    second = _create_project(
        authenticated_client, name="Second activity", slug="second-activity"
    )

    for content in ("First update", "Second update", "Third update"):
        response = authenticated_client.post(
            f"/api/projects/{first['id']}/updates",
            json={"health": "on_track", "content_markdown": content},
        )
        assert response.status_code == 201
    response = authenticated_client.post(
        f"/api/projects/{second['id']}/updates",
        json={"health": "at_risk", "content_markdown": "Other project"},
    )
    assert response.status_code == 201

    full = authenticated_client.get(
        f"/api/projects/{first['id']}/activity", params={"limit": 100}
    ).json()
    first_page = authenticated_client.get(
        f"/api/projects/{first['id']}/activity", params={"limit": 2}
    ).json()
    second_page = authenticated_client.get(
        f"/api/projects/{first['id']}/activity",
        params={"limit": 2, "before": first_page["next_cursor"]},
    ).json()

    full_ids = [item["id"] for item in full["items"]]
    paged_ids = [item["id"] for item in first_page["items"] + second_page["items"]]
    assert full_ids == sorted(full_ids, reverse=True)
    assert paged_ids == full_ids
    assert len(first_page["items"]) == 2
    assert first_page["next_cursor"] == first_page["items"][-1]["id"]
    assert second_page["next_cursor"] is None

    other = authenticated_client.get(f"/api/projects/{second['id']}/activity").json()
    assert {item["project_id"] for item in full["items"]} == {first["id"]}
    assert {item["project_id"] for item in other["items"]} == {second["id"]}

    authenticated_client.post("/api/auth/logout")
    assert client.get(f"/api/projects/{first['id']}/activity").status_code == 401
