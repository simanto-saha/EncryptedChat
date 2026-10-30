from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Message


class ChatConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        if not self.scope['user'].is_authenticated:
            await self.close()
            return

        self.room_group_name = None
        await self.accept()

    async def disconnect(self, close_code):
        if self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        action = content.get('action')

        if action == 'join':
            await self.join_room(content.get('user_id'))
            return

        if action == 'typing':
            recipient_id = content.get('to')
            if (
                isinstance(recipient_id, int)
                and self.room_group_name == self.private_room_name(recipient_id)
            ):
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_typing',
                        'sender_id': self.scope['user'].id,
                        'recipient_id': recipient_id,
                        'is_typing': content.get('is_typing') is True,
                    }
                )
            return

        raw_message = content.get('message')
        recipient_id = content.get('to')

        if (
            not isinstance(raw_message, str)
            or not isinstance(recipient_id, int)
        ):
            return

        message = raw_message.strip()
        if not message or len(message) > 1000:
            return

        if self.room_group_name != self.private_room_name(recipient_id):
            await self.join_room(recipient_id)

        self.pending_recipient_id = recipient_id
        saved_message = await self.save_message(message)
        if not saved_message:
            return

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': {
                    'id': saved_message.pk,
                    'sender_id': saved_message.sender_id,
                    'recipient_id': saved_message.receiver_id,
                    'content': saved_message.content,
                    'time': timezone.localtime(saved_message.timestamp).strftime('%H:%M'),
                },
            }
        )

    async def chat_message(self, event):
        await self.send_json({'message': event['message']})

    async def chat_typing(self, event):
        await self.send_json({
            'typing': {
                'sender_id': event['sender_id'],
                'recipient_id': event['recipient_id'],
                'is_typing': event['is_typing'],
            }
        })

    async def join_room(self, user_id):
        if not isinstance(user_id, int) or user_id == self.scope['user'].id:
            return
        if not await self.other_user_exists(user_id):
            return

        group_name = self.private_room_name(user_id)
        if self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

        self.room_group_name = group_name
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

    def private_room_name(self, user_id):
        low_id, high_id = sorted((self.scope['user'].id, user_id))
        return f'chat_{low_id}_{high_id}'

    @database_sync_to_async
    def other_user_exists(self, user_id):
        return User.objects.filter(
            pk=user_id,
            is_active=True
        ).exclude(pk=self.scope['user'].pk).exists()

    @database_sync_to_async
    def save_message(self, content):
        recipient_id = getattr(self, 'pending_recipient_id', None)
        try:
            receiver = User.objects.get(pk=recipient_id, is_active=True)
        except User.DoesNotExist:
            return None
        return Message.objects.create(
            sender=self.scope['user'],
            receiver=receiver,
            content=content
        )