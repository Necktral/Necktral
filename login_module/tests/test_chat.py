import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.mark.django_db
def test_list_messages_requires_auth():
    client = APIClient()
    response = client.get("/api/chat/messages/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_send_message_requires_auth():
    client = APIClient()
    response = client.post("/api/chat/messages/send/", {"content": "hello"}, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_authenticated_user_can_send_message():
    user = User.objects.create_user(username="chat_user1", password="pass12345")
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "chat_user1", "password": "pass12345"}, format="json")
    access = login.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    response = client.post("/api/chat/messages/send/", {"content": "Hello world"}, format="json")
    assert response.status_code == 201
    assert response.data["content"] == "Hello world"
    assert response.data["sender_username"] == "chat_user1"


@pytest.mark.django_db
def test_authenticated_user_can_list_messages():
    user = User.objects.create_user(username="chat_user2", password="pass12345")
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "chat_user2", "password": "pass12345"}, format="json")
    access = login.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    client.post("/api/chat/messages/send/", {"content": "Test message"}, format="json")

    response = client.get("/api/chat/messages/")
    assert response.status_code == 200
    assert len(response.data["results"]) >= 1
    assert any(m["content"] == "Test message" for m in response.data["results"])


@pytest.mark.django_db
def test_send_message_empty_content_returns_400():
    user = User.objects.create_user(username="chat_user3", password="pass12345")
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "chat_user3", "password": "pass12345"}, format="json")
    access = login.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    response = client.post("/api/chat/messages/send/", {"content": ""}, format="json")
    assert response.status_code == 400
