import concurrent.futures
import io
import os
import sqlite3
import tempfile
import threading
import unittest

import app as chat_app
from werkzeug.security import check_password_hash


class RoomAccessFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        chat_app.DB_PATH = os.path.join(self.temp_dir.name, "test.db")
        chat_app.UPLOAD_FOLDER = os.path.join(self.temp_dir.name, "uploads")
        os.makedirs(chat_app.UPLOAD_FOLDER, exist_ok=True)
        chat_app.init_db()
        chat_app.app.config.update(TESTING=True)
        chat_app._access_attempts.clear()
        chat_app._typing_users.clear()
        chat_app._online_users.clear()
        self.client = chat_app.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_room(
        self,
        access_type="public",
        secret="",
        approval_required=False,
        client=None,
    ):
        client = client or self.client
        response = client.post(
            "/api/rooms",
            json={
                "name": "Equipo Alfa",
                "access_type": access_type,
                "secret": secret,
                "approval_required": approval_required,
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["slug"], response

    def register(self, client, slug, name):
        return client.post(f"/api/rooms/{slug}/membership", json={"name": name})

    def test_public_room_can_be_created_and_used(self):
        slug, _response = self.create_room()
        membership = self.register(self.client, slug, "Ana")
        self.assertEqual(membership.status_code, 200)
        self.assertEqual(membership.get_json()["member"]["role"], "admin")

        message = self.client.post(
            f"/api/rooms/{slug}/messages",
            json={"name": "Nombre falsificado", "text": "Hola", "type": "text"},
        )
        self.assertEqual(message.status_code, 201)
        self.assertEqual(message.get_json()["name"], "Ana")
        updates = self.client.get(f"/api/rooms/{slug}/updates?since=0")
        self.assertEqual([item["text"] for item in updates.get_json()["messages"]], ["Hola"])

    def test_retried_messages_are_idempotent_and_concurrent_senders_stay_available(self):
        slug, _response = self.create_room()
        self.register(self.client, slug, "Administradora")

        retry_payload = {
            "text": "Este mensaje solo debe existir una vez",
            "type": "text",
            "client_message_id": "retry-safe-message-001",
        }
        first = self.client.post(f"/api/rooms/{slug}/messages", json=retry_payload)
        retried = self.client.post(f"/api/rooms/{slug}/messages", json=retry_payload)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(first.get_json()["id"], retried.get_json()["id"])

        clients = []
        for index in range(5):
            participant = chat_app.app.test_client()
            registered = self.register(participant, slug, f"Persona {index}")
            self.assertEqual(registered.status_code, 200)
            clients.append(participant)

        barrier = threading.Barrier(len(clients))

        def send_many(index):
            client = clients[index]
            barrier.wait(timeout=10)
            statuses = []
            for message_index in range(12):
                response = client.post(
                    f"/api/rooms/{slug}/messages",
                    json={
                        "text": f"Mensaje {index}-{message_index}",
                        "type": "text",
                        "client_message_id": f"load-{index}-{message_index}",
                    },
                )
                statuses.append(response.status_code)
                if message_index % 3 == 0:
                    statuses.append(
                        client.get(
                            f"/api/rooms/{slug}/updates?since=0"
                        ).status_code
                    )
            return statuses

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(clients)) as executor:
            results = list(executor.map(send_many, range(len(clients))))

        self.assertTrue(
            all(status in {200, 201} for result in results for status in result)
        )
        updates = self.client.get(f"/api/rooms/{slug}/updates?since=0").get_json()
        user_messages = [
            message for message in updates["messages"] if message["type"] == "text"
        ]
        self.assertEqual(len(user_messages), 61)
        self.assertEqual(
            len(
                [
                    message
                    for message in user_messages
                    if message["client_message_id"] == "retry-safe-message-001"
                ]
            ),
            1,
        )

    def test_password_is_hashed_and_access_is_checked_server_side(self):
        slug, _response = self.create_room("password", "Gato2026")
        self.register(self.client, slug, "Creadora")
        conn = sqlite3.connect(chat_app.DB_PATH)
        access_hash = conn.execute(
            "SELECT access_hash FROM rooms WHERE slug = ?", (slug,)
        ).fetchone()[0]
        conn.close()
        self.assertNotEqual(access_hash, "Gato2026")
        self.assertTrue(check_password_hash(access_hash, "Gato2026"))

        guest = chat_app.app.test_client()
        self.assertTrue(
            guest.get(f"/api/rooms/{slug}/config").get_json()["requires_access"]
        )
        denied = guest.get(f"/api/rooms/{slug}/updates")
        self.assertEqual(denied.status_code, 401)

        wrong = guest.post(f"/api/rooms/{slug}/access", json={"secret": "incorrecta"})
        self.assertEqual(wrong.status_code, 401)
        accepted = guest.post(
            f"/api/rooms/{slug}/access",
            json={"secret": "Gato2026", "remember": False},
        )
        self.assertEqual(accepted.status_code, 200)
        cookie = accepted.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertNotIn("Max-Age", cookie)

        self.assertEqual(guest.get(f"/api/rooms/{slug}/updates").status_code, 403)
        self.assertEqual(self.register(guest, slug, "Invitado").status_code, 200)
        self.assertEqual(guest.get(f"/api/rooms/{slug}/updates").status_code, 200)

    def test_remembered_access_uses_persistent_secure_cookie_and_hashed_token(self):
        slug, _response = self.create_room("code", "483921")
        guest = chat_app.app.test_client()
        accepted = guest.post(
            f"/api/rooms/{slug}/access",
            json={"secret": "483921", "remember": True},
            headers={"X-Forwarded-Proto": "https"},
        )
        cookies = accepted.headers.getlist("Set-Cookie")
        room_cookie = next(value for value in cookies if value.startswith(f"room_access_{slug}="))
        self.assertIn("Max-Age=2592000", room_cookie)
        self.assertIn("Secure", room_cookie)
        raw_token = room_cookie.split("=", 1)[1].split(";", 1)[0]

        conn = sqlite3.connect(chat_app.DB_PATH)
        stored_tokens = [
            row[0] for row in conn.execute("SELECT token_hash FROM room_tokens").fetchall()
        ]
        conn.close()
        self.assertNotIn(raw_token, stored_tokens)
        self.assertIn(chat_app.token_digest(raw_token), stored_tokens)

    def test_code_validation_and_attempt_limit(self):
        invalid = self.client.post(
            "/api/rooms",
            json={"name": "Código", "access_type": "code", "secret": "12345"},
        )
        self.assertEqual(invalid.status_code, 400)

        slug, _response = self.create_room("code", "123456")
        guest = chat_app.app.test_client()
        for _ in range(chat_app.MAX_ACCESS_ATTEMPTS):
            response = guest.post(
                f"/api/rooms/{slug}/access", json={"secret": "000000"}
            )
            self.assertEqual(response.status_code, 401)
        limited = guest.post(f"/api/rooms/{slug}/access", json={"secret": "123456"})
        self.assertEqual(limited.status_code, 429)
        self.assertIn("Retry-After", limited.headers)

    def test_files_are_private_and_rooms_are_isolated(self):
        private_slug, _response = self.create_room("password", "secreto")
        self.register(self.client, private_slug, "Creadora")
        uploaded = self.client.post(
            f"/api/rooms/{private_slug}/upload",
            data={"file": (io.BytesIO(b"private data"), "informe.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded.status_code, 200)
        file_url = uploaded.get_json()["url"]

        guest = chat_app.app.test_client()
        self.assertEqual(guest.get(file_url).status_code, 401)
        guest.post(
            f"/api/rooms/{private_slug}/access",
            json={"secret": "secreto", "remember": False},
        )
        self.assertEqual(self.register(guest, private_slug, "Luis").status_code, 200)
        downloaded = guest.get(file_url)
        self.assertEqual(downloaded.data, b"private data")
        downloaded.close()

        public_slug, _response = self.create_room()
        self.register(self.client, public_slug, "Creadora")
        self.client.post(
            f"/api/rooms/{private_slug}/messages",
            json={"text": "Solo privado", "type": "text"},
        )
        public_updates = self.client.get(f"/api/rooms/{public_slug}/updates")
        self.assertEqual(public_updates.get_json()["messages"], [])

    def test_manual_approval_rejection_kick_system_message_and_permissions(self):
        slug, _response = self.create_room(approval_required=True)
        self.register(self.client, slug, "Administradora")
        guest = chat_app.app.test_client()
        pending = self.register(guest, slug, "Visitante")
        self.assertEqual(pending.status_code, 202)
        guest_id = pending.get_json()["member"]["id"]
        denied = guest.get(f"/api/rooms/{slug}/updates")
        self.assertEqual(denied.get_json()["code"], "approval_pending")

        owner_updates = self.client.get(f"/api/rooms/{slug}/updates").get_json()
        self.assertEqual(owner_updates["join_requests"], [{"id": guest_id, "name": "Visitante"}])
        approved = self.client.post(
            f"/api/rooms/{slug}/members/{guest_id}/decision",
            json={"action": "approve"},
        )
        self.assertEqual(approved.get_json()["status"], "approved")
        self.assertEqual(guest.get(f"/api/rooms/{slug}/updates").status_code, 200)

        sent = guest.post(
            f"/api/rooms/{slug}/messages",
            json={"name": "Administradora", "text": "Mensaje visitante", "type": "text"},
        )
        message_id = sent.get_json()["id"]
        self.assertEqual(sent.get_json()["name"], "Visitante")

        cannot_edit = self.client.patch(
            f"/api/rooms/{slug}/messages/{message_id}",
            json={"name": "Visitante", "text": "Suplantado"},
        )
        self.assertEqual(cannot_edit.status_code, 403)
        cannot_kick = guest.post(f"/api/rooms/{slug}/members/{guest_id}/kick")
        self.assertEqual(cannot_kick.status_code, 403)

        pin = guest.post(f"/api/rooms/{slug}/pin", json={"message_id": message_id})
        self.assertEqual(pin.status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/rooms/{slug}/updates").get_json()["pinned_message"]["id"],
            message_id,
        )
        unread = self.client.post(
            "/api/rooms/unread",
            json={"rooms": [{"slug": slug, "seen": 0}]},
        ).get_json()
        self.assertEqual(unread["rooms"][slug]["count"], 1)

        kicked = self.client.post(f"/api/rooms/{slug}/members/{guest_id}/kick")
        self.assertEqual(kicked.status_code, 200)
        kicked_response = guest.get(f"/api/rooms/{slug}/updates")
        self.assertEqual(kicked_response.get_json()["code"], "member_kicked")
        system_texts = [
            item["text"]
            for item in self.client.get(f"/api/rooms/{slug}/updates").get_json()["messages"]
            if item["type"] == "system"
        ]
        self.assertTrue(any("fue expulsado" in text for text in system_texts))

        rejected_guest = chat_app.app.test_client()
        rejected = self.register(rejected_guest, slug, "Otra persona")
        rejected_id = rejected.get_json()["member"]["id"]
        self.client.post(
            f"/api/rooms/{slug}/members/{rejected_id}/decision",
            json={"action": "reject"},
        )
        status = rejected_guest.get(f"/api/rooms/{slug}/membership").get_json()["member"]
        self.assertEqual(status["status"], "rejected")

    def test_owner_deletes_others_and_display_names_can_change_without_duplicates(self):
        slug, _response = self.create_room()
        self.register(self.client, slug, "Administradora")
        guest = chat_app.app.test_client()
        self.register(guest, slug, "Visitante")

        owner_message = self.client.post(
            f"/api/rooms/{slug}/messages",
            json={"text": "Mensaje de la creadora", "type": "text"},
        ).get_json()
        guest_message = guest.post(
            f"/api/rooms/{slug}/messages",
            json={"text": "Mensaje del visitante", "type": "text"},
        ).get_json()

        forbidden = guest.delete(
            f"/api/rooms/{slug}/messages/{owner_message['id']}"
        )
        self.assertEqual(forbidden.status_code, 403)

        deleted_by_owner = self.client.delete(
            f"/api/rooms/{slug}/messages/{guest_message['id']}"
        )
        self.assertEqual(deleted_by_owner.status_code, 200)
        owner_deletes_own = self.client.delete(
            f"/api/rooms/{slug}/messages/{owner_message['id']}"
        )
        self.assertEqual(owner_deletes_own.status_code, 200)
        remaining_messages = {
            item["id"]: item
            for item in self.client.get(f"/api/rooms/{slug}/updates").get_json()["messages"]
        }
        remaining_ids = set(remaining_messages)
        self.assertIn(owner_message["id"], remaining_ids)
        self.assertEqual(remaining_messages[owner_message["id"]]["type"], "deleted")
        self.assertEqual(
            remaining_messages[owner_message["id"]]["text"],
            "El mensaje de Administradora (Admin) fue borrado por "
            "Administradora (Admin)",
        )
        self.assertEqual(remaining_messages[guest_message["id"]]["type"], "deleted")
        self.assertEqual(
            remaining_messages[guest_message["id"]]["text"],
            "El mensaje de Visitante (Participante) fue borrado por "
            "Administradora (Admin)",
        )

        guest.get(f"/api/rooms/{slug}/updates")
        renamed = guest.patch(
            f"/api/rooms/{slug}/membership/name",
            json={"name": "Visitante Nuevo"},
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.get_json()["member"]["name"], "Visitante Nuevo")

        duplicate = guest.patch(
            f"/api/rooms/{slug}/membership/name",
            json={"name": "  ADMINISTRADORA  "},
        )
        self.assertEqual(duplicate.status_code, 409)

        duplicate_client = chat_app.app.test_client()
        duplicate_join = self.register(duplicate_client, slug, "visitante nuevo")
        self.assertEqual(duplicate_join.status_code, 409)

        updates = self.client.get(f"/api/rooms/{slug}/updates").get_json()
        participant_names = {item["name"] for item in updates["participants"]}
        self.assertIn("Visitante Nuevo", participant_names)
        self.assertNotIn("Visitante", participant_names)
        self.assertIn(
            "Visitante Nuevo",
            {person["name"] for person in updates["online"]},
        )
        system_texts = [
            item["text"] for item in updates["messages"] if item["type"] == "system"
        ]
        self.assertIn(
            '"Visitante" ha tenido una crisis de identidad y ahora es "Visitante Nuevo"',
            system_texts,
        )

        new_message = guest.post(
            f"/api/rooms/{slug}/messages",
            json={"text": "Ya tengo otro nombre", "type": "text"},
        ).get_json()
        self.assertEqual(new_message["name"], "Visitante Nuevo")
        own_delete = guest.delete(
            f"/api/rooms/{slug}/messages/{new_message['id']}"
        )
        self.assertEqual(own_delete.status_code, 200)
        own_deleted_message = next(
            item
            for item in guest.get(f"/api/rooms/{slug}/updates").get_json()["messages"]
            if item["id"] == new_message["id"]
        )
        self.assertEqual(own_deleted_message["type"], "deleted")
        self.assertEqual(
            own_deleted_message["text"],
            "El mensaje de Visitante Nuevo (Participante) fue borrado por "
            "Visitante Nuevo (Participante)",
        )

    def test_role_hierarchy_guest_read_only_and_moderator_authority(self):
        slug, _response = self.create_room()
        admin_member = self.register(self.client, slug, "Admin Principal").get_json()["member"]

        moderator_client = chat_app.app.test_client()
        moderator_member = self.register(
            moderator_client, slug, "Carlos"
        ).get_json()["member"]
        promoted_moderator = self.client.post(
            f"/api/rooms/{slug}/members/{moderator_member['id']}/role",
            json={"action": "ascend", "role": "moderator"},
        )
        self.assertEqual(promoted_moderator.status_code, 200)

        participant_client = chat_app.app.test_client()
        participant_member = self.register(
            participant_client, slug, "Elena"
        ).get_json()["member"]

        guest_client = chat_app.app.test_client()
        guest_member = self.register(guest_client, slug, "Lector").get_json()["member"]
        demoted_guest = self.client.post(
            f"/api/rooms/{slug}/members/{guest_member['id']}/role",
            json={"action": "descend", "role": "guest"},
        )
        self.assertEqual(demoted_guest.status_code, 200)

        second_admin_client = chat_app.app.test_client()
        second_admin_member = self.register(
            second_admin_client, slug, "Otra Admin"
        ).get_json()["member"]
        self.client.post(
            f"/api/rooms/{slug}/members/{second_admin_member['id']}/role",
            json={"action": "ascend", "role": "admin"},
        )

        for endpoint, method, payload in (
            (f"/api/rooms/{slug}/messages", "post", {"text": "No puedo", "type": "text"}),
            (f"/api/rooms/{slug}/typing", "post", {"is_typing": True}),
            (f"/api/rooms/{slug}/pin", "post", {"message_id": None}),
            (
                f"/api/rooms/{slug}/membership/name",
                "patch",
                {"name": "Otro lector"},
            ),
        ):
            response = getattr(guest_client, method)(endpoint, json=payload)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.get_json()["code"], "read_only_role")

        admin_message = self.client.post(
            f"/api/rooms/{slug}/messages",
            json={"text": "Mensaje que modera Carlos", "type": "text"},
        ).get_json()
        moderated = moderator_client.delete(
            f"/api/rooms/{slug}/messages/{admin_message['id']}"
        )
        self.assertEqual(moderated.status_code, 200)
        audit_message = next(
            item
            for item in self.client.get(f"/api/rooms/{slug}/updates").get_json()["messages"]
            if item["id"] == admin_message["id"]
        )
        self.assertEqual(audit_message["type"], "deleted")
        self.assertEqual(
            audit_message["text"],
            "El mensaje de Admin Principal (Admin) fue borrado por "
            "Carlos (Moderador)",
        )
        self.assertNotIn("deleted_original_text", audit_message)
        self.assertNotIn("deleted_original_file_url", audit_message)
        conn = sqlite3.connect(chat_app.DB_PATH)
        stored_audit = conn.execute(
            """SELECT deleted_original_text, deleted_original_type
               FROM messages WHERE id = ?""",
            (admin_message["id"],),
        ).fetchone()
        conn.close()
        self.assertEqual(stored_audit, ("Mensaje que modera Carlos", "text"))

        moderator_own_message = moderator_client.post(
            f"/api/rooms/{slug}/messages",
            json={"text": "Mensaje propio del moderador", "type": "text"},
        ).get_json()
        moderator_deletes_own = moderator_client.delete(
            f"/api/rooms/{slug}/messages/{moderator_own_message['id']}"
        )
        self.assertEqual(moderator_deletes_own.status_code, 200)
        moderator_own_audit = next(
            item
            for item in self.client.get(f"/api/rooms/{slug}/updates").get_json()["messages"]
            if item["id"] == moderator_own_message["id"]
        )
        self.assertEqual(
            moderator_own_audit["text"],
            "El mensaje de Carlos (Moderador) fue borrado por Carlos (Moderador)",
        )

        moderator_cannot_kick_admin = moderator_client.post(
            f"/api/rooms/{slug}/members/{second_admin_member['id']}/kick"
        )
        self.assertEqual(moderator_cannot_kick_admin.status_code, 403)
        moderator_kicks_participant = moderator_client.post(
            f"/api/rooms/{slug}/members/{participant_member['id']}/kick"
        )
        self.assertEqual(moderator_kicks_participant.status_code, 202)
        self.assertEqual(
            moderator_kicks_participant.get_json()["status"],
            "pending_approval",
        )
        self.assertEqual(
            participant_client.get(f"/api/rooms/{slug}/updates").status_code,
            200,
        )
        expulsion_requests = self.client.get(
            f"/api/rooms/{slug}/updates"
        ).get_json()["expulsion_requests"]
        self.assertEqual(len(expulsion_requests), 1)
        self.assertEqual(
            expulsion_requests[0]["target_id"],
            participant_member["id"],
        )
        request_id = expulsion_requests[0]["id"]
        moderator_cannot_approve = moderator_client.post(
            f"/api/rooms/{slug}/expulsion-requests/{request_id}/decision",
            json={"action": "approve"},
        )
        self.assertEqual(moderator_cannot_approve.status_code, 403)
        admin_approves_expulsion = self.client.post(
            f"/api/rooms/{slug}/expulsion-requests/{request_id}/decision",
            json={"action": "approve"},
        )
        self.assertEqual(admin_approves_expulsion.status_code, 200)
        self.assertEqual(
            participant_client.get(f"/api/rooms/{slug}/updates").status_code,
            403,
        )
        moderator_cannot_change_roles = moderator_client.post(
            f"/api/rooms/{slug}/members/{guest_member['id']}/role",
            json={"action": "ascend", "role": "participant"},
        )
        self.assertEqual(moderator_cannot_change_roles.status_code, 403)
        admin_kicks_admin = self.client.post(
            f"/api/rooms/{slug}/members/{second_admin_member['id']}/kick"
        )
        self.assertEqual(admin_kicks_admin.status_code, 200)

        cannot_change_self = self.client.post(
            f"/api/rooms/{slug}/members/{admin_member['id']}/role",
            json={"action": "descend", "role": "moderator"},
        )
        self.assertEqual(cannot_change_self.status_code, 400)
        wrong_direction = self.client.post(
            f"/api/rooms/{slug}/members/{moderator_member['id']}/role",
            json={"action": "ascend", "role": "participant"},
        )
        self.assertEqual(wrong_direction.status_code, 409)
        descended = self.client.post(
            f"/api/rooms/{slug}/members/{moderator_member['id']}/role",
            json={"action": "descend", "role": "guest"},
        )
        self.assertEqual(descended.status_code, 200)
        system_texts = [
            item["text"]
            for item in self.client.get(f"/api/rooms/{slug}/updates").get_json()["messages"]
            if item["type"] == "system"
        ]
        self.assertIn(
            "Se le ha ascendido a Carlos al rango de Moderador",
            system_texts,
        )
        self.assertIn(
            "Se le ha descendido a Carlos al rango de Invitado",
            system_texts,
        )

    def test_expulsion_requests_reject_duplicates_and_cancel_stale_roles(self):
        slug, _response = self.create_room()
        self.register(self.client, slug, "Admin de Guardia")

        moderator_client = chat_app.app.test_client()
        moderator = self.register(
            moderator_client, slug, "Moderadora"
        ).get_json()["member"]
        self.client.post(
            f"/api/rooms/{slug}/members/{moderator['id']}/role",
            json={"action": "ascend", "role": "moderator"},
        )

        target_client = chat_app.app.test_client()
        target = self.register(target_client, slug, "Persona invitada").get_json()["member"]
        self.client.post(
            f"/api/rooms/{slug}/members/{target['id']}/role",
            json={"action": "descend", "role": "guest"},
        )

        requested = moderator_client.post(
            f"/api/rooms/{slug}/members/{target['id']}/kick"
        )
        self.assertEqual(requested.status_code, 202)
        duplicate = moderator_client.post(
            f"/api/rooms/{slug}/members/{target['id']}/kick"
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            duplicate.get_json()["code"],
            "expulsion_request_exists",
        )
        moderator_updates = moderator_client.get(
            f"/api/rooms/{slug}/updates"
        ).get_json()
        self.assertEqual(moderator_updates["expulsion_requests"], [])
        self.assertEqual(
            moderator_updates["pending_expulsion_target_ids"],
            [target["id"]],
        )

        admin_updates = self.client.get(f"/api/rooms/{slug}/updates").get_json()
        pending = admin_updates["expulsion_requests"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["requester_name"], "Moderadora")
        self.assertEqual(pending[0]["requester_role_label"], "Moderador")
        self.assertEqual(pending[0]["target_name"], "Persona invitada")
        self.assertEqual(pending[0]["target_role_label"], "Invitado")

        rejected = self.client.post(
            f"/api/rooms/{slug}/expulsion-requests/{pending[0]['id']}/decision",
            json={"action": "reject"},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(
            target_client.get(f"/api/rooms/{slug}/updates").status_code,
            200,
        )
        self.assertEqual(
            moderator_client.get(
                f"/api/rooms/{slug}/updates"
            ).get_json()["pending_expulsion_target_ids"],
            [],
        )

        stale_request = moderator_client.post(
            f"/api/rooms/{slug}/members/{target['id']}/kick"
        ).get_json()
        promoted = self.client.post(
            f"/api/rooms/{slug}/members/{target['id']}/role",
            json={"action": "ascend", "role": "participant"},
        )
        self.assertEqual(promoted.status_code, 200)
        stale_decision = self.client.post(
            f"/api/rooms/{slug}/expulsion-requests/{stale_request['request_id']}/decision",
            json={"action": "approve"},
        )
        self.assertEqual(stale_decision.status_code, 404)

        final_request = moderator_client.post(
            f"/api/rooms/{slug}/members/{target['id']}/kick"
        ).get_json()
        approved = self.client.post(
            f"/api/rooms/{slug}/expulsion-requests/{final_request['request_id']}/decision",
            json={"action": "approve"},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(
            target_client.get(f"/api/rooms/{slug}/updates").status_code,
            403,
        )
        system_texts = [
            item["text"]
            for item in self.client.get(f"/api/rooms/{slug}/updates").get_json()["messages"]
            if item["type"] == "system"
        ]
        self.assertIn(
            "Persona invitada fue expulsado después de que Admin de Guardia "
            "(Admin) aprobara la solicitud de Moderadora (Moderador)",
            system_texts,
        )

    def test_manual_approval_assigns_role_and_returns_one_time_welcome(self):
        slug, _response = self.create_room(approval_required=True)
        self.register(self.client, slug, "Jesús")
        waiting_client = chat_app.app.test_client()
        pending = self.register(waiting_client, slug, "Nuevo usuario")
        pending_id = pending.get_json()["member"]["id"]

        approved = self.client.post(
            f"/api/rooms/{slug}/members/{pending_id}/decision",
            json={"action": "approve", "role": "guest"},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.get_json()["role"], "guest")

        membership = waiting_client.get(
            f"/api/rooms/{slug}/membership"
        ).get_json()["member"]
        self.assertEqual(membership["role"], "guest")
        self.assertEqual(
            membership["welcome"],
            {
                "approved_by_name": "Jesús",
                "approved_by_role": "admin",
                "approved_by_role_label": "Admin",
                "assigned_role": "guest",
                "assigned_role_label": "Invitado",
            },
        )
        waiting_client.post(f"/api/rooms/{slug}/membership/welcome-seen")
        seen_membership = waiting_client.get(
            f"/api/rooms/{slug}/membership"
        ).get_json()["member"]
        self.assertNotIn("welcome", seen_membership)

        promoted = self.client.post(
            f"/api/rooms/{slug}/members/{pending_id}/role",
            json={"action": "ascend", "role": "participant"},
        )
        self.assertEqual(promoted.status_code, 200)
        live_state = waiting_client.get(f"/api/rooms/{slug}/updates").get_json()
        self.assertEqual(live_state["member_role"], "participant")
        self.assertEqual(live_state["member_role_label"], "Participante")

    def test_private_chat_requires_acceptance_and_is_limited_to_two_people(self):
        slug, _response = self.create_room()
        admin = self.register(self.client, slug, "Alicia").get_json()["member"]
        bob_client = chat_app.app.test_client()
        bob = self.register(bob_client, slug, "Bruno").get_json()["member"]
        third_client = chat_app.app.test_client()
        self.register(third_client, slug, "Carla")

        requested = self.client.post(
            f"/api/rooms/{slug}/members/{bob['id']}/direct-request"
        )
        self.assertEqual(requested.status_code, 202)
        request_id = requested.get_json()["request_id"]
        self.assertEqual(self.client.get("/api/direct-chats").get_json()["chats"], [])
        reverse_request = bob_client.post(
            f"/api/rooms/{slug}/members/{admin['id']}/direct-request"
        )
        self.assertEqual(reverse_request.status_code, 200)
        self.assertEqual(
            reverse_request.get_json()["status"],
            "incoming_pending",
        )
        self.assertEqual(reverse_request.get_json()["request_id"], request_id)

        bob_state = bob_client.get("/api/direct-chats").get_json()
        self.assertEqual(len(bob_state["requests"]), 1)
        self.assertEqual(bob_state["requests"][0]["requester_name"], "Alicia")
        self.assertEqual(
            third_client.post(
                f"/api/direct-chat-requests/{request_id}/decision",
                json={"action": "accept"},
            ).status_code,
            404,
        )

        accepted = bob_client.post(
            f"/api/direct-chat-requests/{request_id}/decision",
            json={"action": "accept"},
        )
        self.assertEqual(accepted.status_code, 200)
        chat_id = accepted.get_json()["chat_id"]
        self.assertEqual(self.client.get(f"/direct/{chat_id}").status_code, 200)
        self.assertEqual(bob_client.get(f"/direct/{chat_id}").status_code, 200)
        self.assertEqual(third_client.get(f"/direct/{chat_id}").status_code, 404)
        self.assertEqual(
            third_client.get(f"/api/direct-chats/{chat_id}/config").status_code,
            403,
        )

        payload = {
            "type": "text",
            "text": "Solo nosotros",
            "client_message_id": "direct-message-001",
        }
        first = self.client.post(
            f"/api/direct-chats/{chat_id}/messages", json=payload
        )
        retried = self.client.post(
            f"/api/direct-chats/{chat_id}/messages", json=payload
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(first.get_json()["id"], retried.get_json()["id"])

        updates = bob_client.get(
            f"/api/direct-chats/{chat_id}/updates?since=0"
        ).get_json()
        self.assertEqual([item["text"] for item in updates["messages"]], ["Solo nosotros"])
        self.assertEqual(updates["member"]["id"], bob["id"])
        self.assertEqual(updates["other"]["id"], admin["id"])

        uploaded = self.client.post(
            f"/api/direct-chats/{chat_id}/upload",
            data={"file": (io.BytesIO(b"private direct data"), "privado.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded.status_code, 200)
        file_url = uploaded.get_json()["url"]
        downloaded = bob_client.get(file_url)
        self.assertEqual(downloaded.data, b"private direct data")
        downloaded.close()
        self.assertEqual(third_client.get(file_url).status_code, 403)

        conn = sqlite3.connect(chat_app.DB_PATH)
        stored_pair = conn.execute(
            """SELECT member_low_id, member_high_id
               FROM direct_chats WHERE id = ?""",
            (chat_id,),
        ).fetchone()
        conn.close()
        self.assertEqual(set(stored_pair), {admin["id"], bob["id"]})

    def test_private_chat_rejection_cooldown_and_guest_restrictions(self):
        slug, _response = self.create_room()
        self.register(self.client, slug, "Admin")
        participant_client = chat_app.app.test_client()
        participant = self.register(
            participant_client, slug, "Participante"
        ).get_json()["member"]
        guest_client = chat_app.app.test_client()
        guest = self.register(guest_client, slug, "Invitado").get_json()["member"]
        demoted = self.client.post(
            f"/api/rooms/{slug}/members/{guest['id']}/role",
            json={"action": "descend", "role": "guest"},
        )
        self.assertEqual(demoted.status_code, 200)

        self.assertEqual(
            participant_client.post(
                f"/api/rooms/{slug}/members/{participant['id']}/direct-request"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                f"/api/rooms/{slug}/members/{guest['id']}/direct-request"
            ).status_code,
            403,
        )
        self.assertEqual(
            guest_client.post(
                f"/api/rooms/{slug}/members/{participant['id']}/direct-request"
            ).status_code,
            403,
        )

        requested = self.client.post(
            f"/api/rooms/{slug}/members/{participant['id']}/direct-request"
        )
        request_id = requested.get_json()["request_id"]
        rejected = participant_client.post(
            f"/api/direct-chat-requests/{request_id}/decision",
            json={"action": "reject"},
        )
        self.assertEqual(rejected.status_code, 200)
        cooldown = self.client.post(
            f"/api/rooms/{slug}/members/{participant['id']}/direct-request"
        )
        self.assertEqual(cooldown.status_code, 429)
        self.assertEqual(cooldown.get_json()["code"], "direct_request_cooldown")

    def test_private_chat_access_is_revoked_if_member_becomes_guest(self):
        slug, _response = self.create_room()
        self.register(self.client, slug, "Administradora")
        participant_client = chat_app.app.test_client()
        participant = self.register(
            participant_client, slug, "Persona"
        ).get_json()["member"]
        requested = self.client.post(
            f"/api/rooms/{slug}/members/{participant['id']}/direct-request"
        ).get_json()
        accepted = participant_client.post(
            f"/api/direct-chat-requests/{requested['request_id']}/decision",
            json={"action": "accept"},
        ).get_json()
        chat_id = accepted["chat_id"]
        self.assertEqual(
            participant_client.get(f"/api/direct-chats/{chat_id}/config").status_code,
            200,
        )

        demoted = self.client.post(
            f"/api/rooms/{slug}/members/{participant['id']}/role",
            json={"action": "descend", "role": "guest"},
        )
        self.assertEqual(demoted.status_code, 200)
        self.assertEqual(
            participant_client.get(f"/api/direct-chats/{chat_id}/config").status_code,
            403,
        )
        self.assertEqual(participant_client.get("/api/direct-chats").get_json()["chats"], [])

    def test_media_galleries_are_isolated_by_room_and_private_chat(self):
        room_slug, _response = self.create_room()
        admin = self.register(self.client, room_slug, "Alicia").get_json()["member"]
        participant_client = chat_app.app.test_client()
        participant = self.register(
            participant_client, room_slug, "Bruno"
        ).get_json()["member"]

        room_upload = self.client.post(
            f"/api/rooms/{room_slug}/upload",
            data={"file": (io.BytesIO(b"room image"), "sala.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(room_upload.status_code, 200)
        room_file = room_upload.get_json()
        room_message = self.client.post(
            f"/api/rooms/{room_slug}/messages",
            json={
                "type": "image",
                "file_url": room_file["url"],
                "file_name": room_file["filename"],
                "client_message_id": "room-gallery-image-001",
            },
        )
        self.assertEqual(room_message.status_code, 201)

        other_room_client = chat_app.app.test_client()
        other_slug, _response = self.create_room(client=other_room_client)
        self.register(other_room_client, other_slug, "Otra sala")
        room_gallery = participant_client.get(
            f"/api/rooms/{room_slug}/media?type=image"
        )
        self.assertEqual(room_gallery.status_code, 200)
        self.assertEqual(len(room_gallery.get_json()["items"]), 1)
        self.assertEqual(room_gallery.get_json()["counts"]["image"], 1)
        self.assertEqual(
            other_room_client.get(
                f"/api/rooms/{other_slug}/media?type=all"
            ).get_json()["items"],
            [],
        )

        request_data = self.client.post(
            f"/api/rooms/{room_slug}/members/{participant['id']}/direct-request"
        ).get_json()
        accepted = participant_client.post(
            f"/api/direct-chat-requests/{request_data['request_id']}/decision",
            json={"action": "accept"},
        )
        chat_id = accepted.get_json()["chat_id"]
        config = self.client.get(
            f"/api/direct-chats/{chat_id}/config"
        ).get_json()
        self.assertEqual(config["member"]["id"], admin["id"])
        self.assertEqual(config["member"]["role"], "participant")
        self.assertEqual(config["other"]["role"], "participant")

        audio_upload = self.client.post(
            f"/api/direct-chats/{chat_id}/upload",
            data={
                "file": (io.BytesIO(b"private audio"), "nota.webm"),
                "kind": "audio",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(audio_upload.status_code, 200)
        audio_file = audio_upload.get_json()
        audio_message = self.client.post(
            f"/api/direct-chats/{chat_id}/messages",
            json={
                "type": "audio",
                "file_url": audio_file["url"],
                "file_name": audio_file["filename"],
                "client_message_id": "direct-gallery-audio-001",
            },
        )
        self.assertEqual(audio_message.status_code, 201)

        direct_gallery = participant_client.get(
            f"/api/direct-chats/{chat_id}/media?type=audio"
        )
        self.assertEqual(direct_gallery.status_code, 200)
        direct_data = direct_gallery.get_json()
        self.assertEqual(len(direct_data["items"]), 1)
        self.assertEqual(direct_data["items"][0]["type"], "audio")
        self.assertEqual(direct_data["counts"]["audio"], 1)
        self.assertEqual(
            participant_client.get(
                f"/api/rooms/{room_slug}/media?type=audio"
            ).get_json()["items"],
            [],
        )
        self.assertEqual(
            other_room_client.get(
                f"/api/direct-chats/{chat_id}/media"
            ).status_code,
            403,
        )

    def test_private_message_controls_receipts_profiles_and_search(self):
        slug, _response = self.create_room()
        alice = self.register(self.client, slug, "Alicia").get_json()["member"]
        bob_client = chat_app.app.test_client()
        bob = self.register(bob_client, slug, "Bruno").get_json()["member"]
        request_data = self.client.post(
            f"/api/rooms/{slug}/members/{bob['id']}/direct-request"
        ).get_json()
        accepted = bob_client.post(
            f"/api/direct-chat-requests/{request_data['request_id']}/decision",
            json={"action": "accept"},
        ).get_json()
        chat_id = accepted["chat_id"]

        sent = self.client.post(
            f"/api/direct-chats/{chat_id}/messages",
            json={
                "type": "text",
                "text": "Un mensaje muy especial",
                "client_message_id": "private-controls-001",
            },
        )
        self.assertEqual(sent.status_code, 201)
        message_id = sent.get_json()["id"]

        bob_client.get("/api/direct-chats")
        delivered = self.client.get(
            f"/api/direct-chats/{chat_id}/updates?since=0"
        ).get_json()
        self.assertEqual(delivered["receipts"][str(message_id)], "delivered")
        bob_client.get(f"/api/direct-chats/{chat_id}/updates?since=0")
        seen = self.client.get(
            f"/api/direct-chats/{chat_id}/updates?since=0"
        ).get_json()
        self.assertEqual(seen["receipts"][str(message_id)], "seen")

        self.assertEqual(
            bob_client.patch(
                f"/api/direct-chats/{chat_id}/messages/{message_id}",
                json={"text": "No permitido"},
            ).status_code,
            403,
        )
        self.assertEqual(
            bob_client.delete(
                f"/api/direct-chats/{chat_id}/messages/{message_id}",
                json={"scope": "everyone"},
            ).status_code,
            403,
        )
        edited = self.client.patch(
            f"/api/direct-chats/{chat_id}/messages/{message_id}",
            json={"text": "Un mensaje especial editado"},
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(
            bob_client.post(
                f"/api/direct-chats/{chat_id}/messages/{message_id}/reactions",
                json={"emoji": "👍"},
            ).status_code,
            200,
        )
        self.assertEqual(
            bob_client.post(
                f"/api/direct-chats/{chat_id}/pin",
                json={"message_id": message_id},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/direct-chats/{chat_id}/messages/{message_id}/star"
            ).status_code,
            200,
        )
        alice_state = self.client.get(
            f"/api/direct-chats/{chat_id}/updates?since=0"
        ).get_json()
        self.assertEqual(alice_state["pinned_message"]["id"], message_id)
        self.assertTrue(alice_state["messages"][0]["starred"])
        self.assertEqual(alice_state["messages"][0]["reactions"][0]["name"], "Bruno")
        bob_state = bob_client.get(
            f"/api/direct-chats/{chat_id}/updates?since=0"
        ).get_json()
        self.assertFalse(bob_state["messages"][0]["starred"])

        hidden = bob_client.delete(
            f"/api/direct-chats/{chat_id}/messages/{message_id}",
            json={"scope": "me"},
        )
        self.assertEqual(hidden.status_code, 200)
        self.assertEqual(
            bob_client.get(
                f"/api/direct-chats/{chat_id}/updates?since=0"
            ).get_json()["messages"],
            [],
        )
        self.assertEqual(
            bob_client.get(
                f"/api/direct-chats/{chat_id}/search?q=editado"
            ).get_json()["count"],
            0,
        )
        self.assertEqual(
            self.client.get(
                f"/api/direct-chats/{chat_id}/search?q=editado"
            ).get_json()["count"],
            1,
        )

        second = self.client.post(
            f"/api/direct-chats/{chat_id}/messages",
            json={
                "type": "text",
                "text": "Mensaje para borrar en ambos",
                "client_message_id": "private-controls-002",
            },
        ).get_json()
        deleted = self.client.delete(
            f"/api/direct-chats/{chat_id}/messages/{second['id']}",
            json={"scope": "everyone"},
        )
        self.assertEqual(deleted.status_code, 200)
        visible_deleted = bob_client.get(
            f"/api/direct-chats/{chat_id}/updates?since=0"
        ).get_json()["messages"]
        self.assertEqual(visible_deleted[-1]["type"], "deleted")
        self.assertEqual(visible_deleted[-1]["text"], "Este mensaje fue eliminado")

        reply_target = self.client.post(
            f"/api/direct-chats/{chat_id}/messages",
            json={
                "type": "text",
                "text": "Mensaje original para responder",
                "client_message_id": "private-reply-target-001",
            },
        ).get_json()
        reply = bob_client.post(
            f"/api/direct-chats/{chat_id}/messages",
            json={
                "type": "text",
                "text": "Esta es una respuesta privada",
                "reply_to_id": reply_target["id"],
                "reply_to_name": "Nombre falsificado",
                "reply_to_text": "Texto falsificado",
                "client_message_id": "private-reply-001",
            },
        )
        self.assertEqual(reply.status_code, 201)
        reply_state = self.client.get(
            f"/api/direct-chats/{chat_id}/updates?since=0"
        ).get_json()["messages"][-1]
        self.assertEqual(reply_state["reply_to_id"], reply_target["id"])
        self.assertEqual(reply_state["reply_to_name"], "Alicia")
        self.assertEqual(reply_state["reply_to_text"], "Mensaje original para responder")
        self.assertEqual(
            bob_client.post(
                f"/api/direct-chats/{chat_id}/messages",
                json={
                    "type": "text",
                    "text": "Referencia inexistente",
                    "reply_to_id": 999999,
                    "client_message_id": "private-reply-invalid-001",
                },
            ).status_code,
            404,
        )

        profile = self.client.patch(
            f"/api/rooms/{slug}/profile",
            json={"bio": "Diseñadora y amante de los chats limpios."},
        )
        self.assertEqual(profile.status_code, 200)
        photo = self.client.post(
            f"/api/rooms/{slug}/profile/photo",
            data={"photo": (io.BytesIO(b"fake png"), "perfil.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(photo.status_code, 200)
        banner = self.client.post(
            f"/api/rooms/{slug}/profile/banner",
            data={"banner": (io.BytesIO(b"fake banner"), "banner.webp")},
            content_type="multipart/form-data",
        )
        self.assertEqual(banner.status_code, 200)
        viewed = bob_client.get(
            f"/api/rooms/{slug}/members/{alice['id']}/profile"
        ).get_json()["profile"]
        self.assertEqual(viewed["bio"], "Diseñadora y amante de los chats limpios.")
        self.assertTrue(viewed["photo_url"].endswith(".png"))
        self.assertTrue(viewed["banner_url"].endswith(".webp"))

        room_message = self.client.post(
            f"/api/rooms/{slug}/messages",
            json={"type": "text", "text": "Clave de búsqueda sala"},
        )
        self.assertEqual(room_message.status_code, 201)
        room_search = bob_client.get(
            f"/api/rooms/{slug}/search?q=búsqueda"
        ).get_json()
        self.assertEqual(room_search["count"], 1)


    def test_profile_changes_refresh_rooms_and_every_private_chat(self):
        slug, _response = self.create_room()
        alice = self.register(self.client, slug, "Alicia").get_json()["member"]
        bob_client = chat_app.app.test_client()
        bob = self.register(bob_client, slug, "Bruno").get_json()["member"]

        room_message = self.client.post(
            f"/api/rooms/{slug}/messages",
            json={"type": "text", "text": "Mensaje anterior al cambio de perfil"},
        ).get_json()
        room_reply = bob_client.post(
            f"/api/rooms/{slug}/messages",
            json={
                "type": "text",
                "text": "Respuesta que conserva la referencia",
                "reply_to_id": room_message["id"],
            },
        )
        self.assertEqual(room_reply.status_code, 201)
        self.assertEqual(
            self.client.post(
                f"/api/rooms/{slug}/pin",
                json={"message_id": room_message["id"]},
            ).status_code,
            200,
        )

        requested = self.client.post(
            f"/api/rooms/{slug}/members/{bob['id']}/direct-request"
        ).get_json()
        chat_id = bob_client.post(
            f"/api/direct-chat-requests/{requested['request_id']}/decision",
            json={"action": "accept"},
        ).get_json()["chat_id"]
        direct_message = self.client.post(
            f"/api/direct-chats/{chat_id}/messages",
            json={
                "type": "text",
                "text": "Mensaje privado anterior al cambio",
                "client_message_id": "profile-sync-direct-001",
            },
        ).get_json()
        direct_reply = bob_client.post(
            f"/api/direct-chats/{chat_id}/messages",
            json={
                "type": "text",
                "text": "Respuesta privada",
                "reply_to_id": direct_message["id"],
                "client_message_id": "profile-sync-direct-002",
            },
        )
        self.assertEqual(direct_reply.status_code, 201)
        self.assertEqual(
            bob_client.post(
                f"/api/direct-chats/{chat_id}/pin",
                json={"message_id": direct_message["id"]},
            ).status_code,
            200,
        )

        room_before = bob_client.get(
            f"/api/rooms/{slug}/updates?since=0"
        ).get_json()["version"]
        direct_before = bob_client.get(
            f"/api/direct-chats/{chat_id}/updates?since=0"
        ).get_json()["version"]

        bio = "Biografía nueva y sincronizada."
        self.assertEqual(
            self.client.patch(
                f"/api/rooms/{slug}/profile", json={"bio": bio}
            ).status_code,
            200,
        )
        photo_url = self.client.post(
            f"/api/rooms/{slug}/profile/photo",
            data={"photo": (io.BytesIO(b"profile image"), "perfil.png")},
            content_type="multipart/form-data",
        ).get_json()["photo_url"]
        banner_url = self.client.post(
            f"/api/rooms/{slug}/profile/banner",
            data={"banner": (io.BytesIO(b"profile banner"), "banner.webp")},
            content_type="multipart/form-data",
        ).get_json()["banner_url"]
        renamed = self.client.patch(
            f"/api/rooms/{slug}/membership/name",
            json={"name": "Alicia Renovada"},
        )
        self.assertEqual(renamed.status_code, 200)

        room_state = bob_client.get(
            f"/api/rooms/{slug}/updates?since=0"
        ).get_json()
        self.assertGreater(room_state["version"], room_before)
        alice_profile = next(
            person for person in room_state["participants"] if person["id"] == alice["id"]
        )
        self.assertEqual(alice_profile["name"], "Alicia Renovada")
        self.assertEqual(alice_profile["bio"], bio)
        self.assertEqual(alice_profile["photo_url"], photo_url)
        self.assertEqual(alice_profile["banner_url"], banner_url)
        old_room_message = next(
            message
            for message in room_state["messages"]
            if message["id"] == room_message["id"]
        )
        self.assertEqual(old_room_message["name"], "Alicia Renovada")
        self.assertEqual(old_room_message["author_photo_url"], photo_url)
        synced_room_reply = next(
            message
            for message in room_state["messages"]
            if message["id"] == room_reply.get_json()["id"]
        )
        self.assertEqual(synced_room_reply["reply_to_name"], "Alicia Renovada")
        self.assertEqual(room_state["pinned_message"]["name"], "Alicia Renovada")
        self.assertEqual(
            bob_client.get(
                f"/api/rooms/{slug}/search?q=anterior"
            ).get_json()["matches"][0]["author_name"],
            "Alicia Renovada",
        )

        direct_state = bob_client.get(
            f"/api/direct-chats/{chat_id}/updates?since=0"
        ).get_json()
        self.assertGreaterEqual(direct_state["version"], direct_before + 4)
        self.assertEqual(direct_state["other"]["name"], "Alicia Renovada")
        self.assertEqual(direct_state["other"]["bio"], bio)
        self.assertEqual(direct_state["other"]["photo_url"], photo_url)
        self.assertEqual(direct_state["other"]["banner_url"], banner_url)
        old_direct_message = next(
            message
            for message in direct_state["messages"]
            if message["id"] == direct_message["id"]
        )
        self.assertEqual(old_direct_message["author_name"], "Alicia Renovada")
        self.assertEqual(old_direct_message["author_photo_url"], photo_url)
        synced_direct_reply = next(
            message
            for message in direct_state["messages"]
            if message["id"] == direct_reply.get_json()["id"]
        )
        self.assertEqual(synced_direct_reply["reply_to_name"], "Alicia Renovada")
        self.assertEqual(
            direct_state["pinned_message"]["author_name"], "Alicia Renovada"
        )
        direct_config = bob_client.get(
            f"/api/direct-chats/{chat_id}/config"
        ).get_json()
        self.assertEqual(direct_config["other"]["name"], "Alicia Renovada")
        self.assertEqual(direct_config["other"]["bio"], bio)


if __name__ == "__main__":
    unittest.main()
