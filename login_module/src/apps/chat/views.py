from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Message
from .serializers import MessageCreateSerializer, MessageSerializer


class MessageListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        messages = Message.objects.select_related("sender").order_by("created_at")
        serializer = MessageSerializer(messages, many=True)
        return Response({"results": serializer.data})


class MessageCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MessageCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        message = Message.objects.create(
            sender=request.user,
            content=serializer.validated_data["content"],
        )
        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)
