from django.urls import path

from .views import MessageCreateView, MessageListView

urlpatterns = [
    path("messages/", MessageListView.as_view(), name="chat-message-list"),
    path("messages/send/", MessageCreateView.as_view(), name="chat-message-send"),
]
