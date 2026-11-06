"""Tests for the HTTP API: auth, predictions, exports, and error handling."""

from __future__ import annotations

from tests.conftest import LYSOZYME


class TestHealth:
    def test_health_is_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["engine"] == "Proteoscope"

    def test_api_root_lists_docs(self, client):
        resp = client.get("/api")
        assert resp.status_code == 200
        assert resp.json()["docs"] == "/api/docs"


class TestAuth:
    def test_register_returns_token_and_user(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"email": "a@example.com", "password": "helix1234", "full_name": "A"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["access_token"]
        assert body["user"]["email"] == "a@example.com"
        assert "password" not in body["user"]

    def test_duplicate_email_is_rejected(self, client):
        payload = {"email": "dup@example.com", "password": "helix1234"}
        assert client.post("/api/auth/register", json=payload).status_code == 201
        assert client.post("/api/auth/register", json=payload).status_code == 409

    def test_weak_password_is_rejected(self, client):
        resp = client.post("/api/auth/register", json={"email": "w@example.com", "password": "password"})
        assert resp.status_code == 422

    def test_login_succeeds_with_correct_password(self, client):
        client.post("/api/auth/register", json={"email": "b@example.com", "password": "helix1234"})
        resp = client.post("/api/auth/login", json={"email": "b@example.com", "password": "helix1234"})
        assert resp.status_code == 200
        assert resp.json()["access_token"]

    def test_login_fails_with_wrong_password(self, client):
        client.post("/api/auth/register", json={"email": "c@example.com", "password": "helix1234"})
        resp = client.post("/api/auth/login", json={"email": "c@example.com", "password": "wrongpass1"})
        assert resp.status_code == 401

    def test_login_does_not_reveal_whether_email_exists(self, client):
        # Unknown email and wrong password must return the same message.
        client.post("/api/auth/register", json={"email": "d@example.com", "password": "helix1234"})
        wrong_pw = client.post("/api/auth/login", json={"email": "d@example.com", "password": "nope12345"})
        unknown = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope12345"})
        assert wrong_pw.status_code == unknown.status_code == 401
        assert wrong_pw.json()["detail"] == unknown.json()["detail"]

    def test_me_requires_a_token(self, client):
        assert client.get("/api/auth/me").status_code == 401

    def test_me_returns_the_authenticated_user(self, auth_client):
        resp = auth_client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == "researcher@example.com"

    def test_garbage_token_is_rejected(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
        assert resp.status_code == 401


class TestPredictions:
    def test_prediction_works_anonymously(self, client):
        # Running the engine is a pure computation, so it needs no account.
        resp = client.post("/api/predictions", json={"sequence": LYSOZYME})
        assert resp.status_code == 201
        body = resp.json()
        assert body["saved"] is False
        assert body["id"] is None
        assert body["result"]["sequence"]["length"] == len(LYSOZYME)

    def test_saving_anonymously_is_rejected(self, client):
        # Saving needs an identity, so this one does require a token.
        resp = client.post("/api/predictions", json={"sequence": LYSOZYME, "save": True})
        assert resp.status_code == 401

    def test_prediction_returns_full_result(self, auth_client):
        resp = auth_client.post("/api/predictions", json={"sequence": LYSOZYME})
        assert resp.status_code == 201
        body = resp.json()
        assert body["saved"] is False
        assert body["result"]["sequence"]["length"] == len(LYSOZYME)
        assert body["result"]["structure"]["coordinates"]

    def test_prediction_can_be_saved(self, auth_client):
        resp = auth_client.post(
            "/api/predictions", json={"sequence": LYSOZYME, "save": True, "label": "Lysozyme"}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["saved"] is True
        assert isinstance(body["id"], int)

    def test_invalid_residues_return_422(self, auth_client):
        resp = auth_client.post("/api/predictions", json={"sequence": "MKTAYIAKQRQISFVKXBZ"})
        assert resp.status_code == 422

    def test_too_short_sequence_returns_422(self, auth_client):
        resp = auth_client.post("/api/predictions", json={"sequence": "MKTA"})
        assert resp.status_code == 422

    def test_oversized_sequence_returns_422(self, auth_client):
        resp = auth_client.post("/api/predictions", json={"sequence": "A" * 5000})
        assert resp.status_code == 422

    def test_fasta_header_letters_are_not_treated_as_residues(self, auth_client):
        # Regression: the pre-validator used to count every letter in the raw
        # text, so a header like ">sp|P00698|LYSC_CHICK Lysozyme C" was rejected
        # for containing O and Z. A valid FASTA record must be accepted.
        fasta = ">sp|P00698|LYSC_CHICK Lysozyme C\n" + LYSOZYME
        resp = auth_client.post("/api/predictions", json={"sequence": fasta})
        assert resp.status_code == 201, resp.text
        assert resp.json()["result"]["sequence"]["length"] == len(LYSOZYME)
        assert resp.json()["result"]["sequence"]["header"] == "sp|P00698|LYSC_CHICK Lysozyme C"

    def test_list_is_empty_for_a_new_user(self, auth_client):
        resp = auth_client.get("/api/predictions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_saved_prediction_appears_in_the_list(self, auth_client):
        auth_client.post("/api/predictions", json={"sequence": LYSOZYME, "save": True})
        rows = auth_client.get("/api/predictions").json()
        assert len(rows) == 1
        assert rows[0]["length"] == len(LYSOZYME)

    def test_fetch_saved_prediction_returns_the_result(self, auth_client):
        created = auth_client.post("/api/predictions", json={"sequence": LYSOZYME, "save": True}).json()
        resp = auth_client.get(f"/api/predictions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["result"]["sequence"]["length"] == len(LYSOZYME)

    def test_delete_removes_the_prediction(self, auth_client):
        created = auth_client.post("/api/predictions", json={"sequence": LYSOZYME, "save": True}).json()
        assert auth_client.delete(f"/api/predictions/{created['id']}").status_code == 204
        assert auth_client.get(f"/api/predictions/{created['id']}").status_code == 404

    def test_missing_prediction_returns_404(self, auth_client):
        assert auth_client.get("/api/predictions/99999").status_code == 404

    def test_users_cannot_read_each_others_predictions(self, client):
        # User A saves something.
        a = client.post(
            "/api/auth/register", json={"email": "a2@example.com", "password": "helix1234"}
        ).json()
        created = client.post(
            "/api/predictions",
            json={"sequence": LYSOZYME, "save": True},
            headers={"Authorization": f"Bearer {a['access_token']}"},
        ).json()

        # User B must not be able to read it.
        b = client.post(
            "/api/auth/register", json={"email": "b2@example.com", "password": "helix1234"}
        ).json()
        resp = client.get(
            f"/api/predictions/{created['id']}",
            headers={"Authorization": f"Bearer {b['access_token']}"},
        )
        assert resp.status_code == 404


class TestExports:
    def test_pdb_export_has_atom_records(self, auth_client):
        created = auth_client.post("/api/predictions", json={"sequence": LYSOZYME, "save": True}).json()
        resp = auth_client.get(f"/api/predictions/{created['id']}/export?fmt=pdb")
        assert resp.status_code == 200
        assert "ATOM" in resp.text
        assert resp.text.rstrip().endswith("END")

    def test_csv_export_has_a_header_and_rows(self, auth_client):
        created = auth_client.post("/api/predictions", json={"sequence": LYSOZYME, "save": True}).json()
        resp = auth_client.get(f"/api/predictions/{created['id']}/export?fmt=csv")
        assert resp.status_code == 200
        lines = resp.text.strip().splitlines()
        assert lines[0].startswith("index,residue")
        assert len(lines) == len(LYSOZYME) + 1

    def test_text_export_contains_the_report_header(self, auth_client):
        created = auth_client.post("/api/predictions", json={"sequence": LYSOZYME, "save": True}).json()
        resp = auth_client.get(f"/api/predictions/{created['id']}/export?fmt=txt")
        assert resp.status_code == 200
        assert "PROTEOSCOPE STRUCTURE REPORT" in resp.text

    def test_unknown_export_format_is_rejected(self, auth_client):
        created = auth_client.post("/api/predictions", json={"sequence": LYSOZYME, "save": True}).json()
        resp = auth_client.get(f"/api/predictions/{created['id']}/export?fmt=docx")
        assert resp.status_code == 422


class TestSecurity:
    def test_security_headers_are_present(self, client):
        resp = client.get("/api/health")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert "X-Request-ID" in resp.headers

    def test_rate_limit_returns_429(self, client):
        # The auth limit is 10/minute; the 11th call must be refused.
        payload = {"email": "rl@example.com", "password": "wrongpass1"}
        codes = [client.post("/api/auth/login", json=payload).status_code for _ in range(12)]
        assert 429 in codes

    def test_rate_limited_response_carries_retry_after(self, client):
        payload = {"email": "rl2@example.com", "password": "wrongpass1"}
        last = None
        for _ in range(12):
            last = client.post("/api/auth/login", json=payload)
        assert last.status_code == 429
        assert "Retry-After" in last.headers

    def test_validation_errors_are_structured(self, auth_client):
        resp = auth_client.post("/api/predictions", json={"sequence": "MKTA"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "validation_error"
        assert "fields" in body
