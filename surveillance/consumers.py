from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json
import logging

logger = logging.getLogger(__name__)

"""
1:from channels.genric.websocket import AsyncWebsocketConsumer is the base class for handling WebSocket connections in an asynchronous manner.
2:database_sync_to_async is a decorator that allows us to run synchronous database operations in an asynchronous context without blocking the event loop.
3:json is used for encoding and decoding JSON data sent over the WebSocket.
4:logging is used for logging errors and other information, which is crucial for debugging and monitoring the application.
"""

# The PoseConsumer class handles WebSocket connections for real-time notifications in the surveillance system. 
class PoseConsumer(AsyncWebsocketConsumer):
    #async def connect(self) is called when a new WebSocket connection is established. It checks if the user is authenticated, adds the connection to the appropriate channel groups, and sends any unread notifications to the client.
    async def connect(self):
        self.user = self.scope.get("user")
        # All clients join the "surveillance_group" to receive broadcast messages (e.g., supervisor alerts).
        await self.channel_layer.group_add("surveillance_group", self.channel_name)

        if self.user and self.user.is_authenticated:
            self.personal_group = f"user_{self.user.id}"
            await self.channel_layer.group_add(self.personal_group, self.channel_name)
            
            await self.accept()

            unread = await self._get_unread_notifications()
            if unread:
                await self.send(text_data=json.dumps({
                    "type": "INITIAL_NOTIFICATIONS",
                    "notifications": unread
                }))
        else:
            self.personal_group = None
            await self.accept()
    
    #async def disconnect(self, close_code) is called when the WebSocket connection is closed. It removes the connection from the channel groups to stop receiving messages. This ensures that resources are cleaned up properly when a
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("surveillance_group", self.channel_name)
        if self.personal_group:
            await self.channel_layer.group_discard(self.personal_group, self.channel_name)
 
    #async def receive(self, text_data) is called when a message is received from the client. It processes the incoming data, which can include actions like marking a notification as read or responding to a ping message. The method uses a try-except block to handle any potential errors gracefully and logs them for debugging purposes.
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action_type = data.get("type")

            if action_type == "MARK_READ":
                notif_id = data.get("notification_id")
                if notif_id:
                    await self._mark_notification_read(notif_id)
            
            elif action_type == "PING":
                await self.send(text_data=json.dumps({"type": "PONG"}))

        except Exception as e:
            logger.error(f"WebSocket Receive Error: {e}")

    # ------------------------------------------------------------------
    # Channel Layer Handlers
    # ------------------------------------------------------------------
    # These methods are called when messages are sent to the channel groups that this consumer is subscribed to. They handle forwarding messages to the WebSocket and sending notifications to the client.
    async def forward_to_websocket(self, event):
        await self.send(text_data=json.dumps(event["payload"]))

    # This method handles incoming notifications that are sent to the user's personal channel group. It formats the notification data and sends it to the client. The use of .get() with default values ensures that the method can handle cases where certain keys might be missing from the event, preventing potential KeyErrors.
    async def send_notification(self, event):
       
       
        created_at = event.get("created_at")
        if not isinstance(created_at, str) and created_at:
            created_at = created_at.strftime("%Y-%m-%d %H:%M:%S")   
            
        await self.send(text_data=json.dumps({
            "type":              "NOTIFICATION",
            # ↓ was event["notification_id"] — crashes when key is absent
            "notification_id":   event.get("notification_id"),
            "notification_type": event.get("notification_type", "info"),
            "title":             event.get("title", ""),
            "message":           event.get("message", ""),
            "event_id":          event.get("event_id"),
            "created_at":        created_at,
        }))

    # ------------------------------------------------------------------
    # Database Operations
    # ------------------------------------------------------------------
    # These methods interact with the database to retrieve unread notifications and mark notifications as read. They are decorated with @database_sync_to_async to ensure 
    @database_sync_to_async
    def _get_unread_notifications(self):
        from surveillance.models import Notification
        try:
            qs = Notification.objects.filter(
                recipient=self.user, is_read=False
            ).order_by('-created_at')[:15]
            
            notifications = []
            for n in qs:
                notifications.append({
                    "id": n.id,
                    "notification_type": n.notification_type,
                    "title": n.title,
                    "message": n.message,
                    "created_at": n.created_at.strftime("%Y-%m-%d %H:%M:%S")
                })
            return notifications
        except Exception as e:
            logger.error(f"DB Error in _get_unread_notifications: {e}")
            return []
    # This method marks a specific notification as read in the database. It uses a filter to ensure that only the notification belonging to the current user is updated, which adds a layer of security by preventing users from marking notifications that do not belong to them.
    @database_sync_to_async
    def _mark_notification_read(self, notif_id):
        from surveillance.models import Notification
        Notification.objects.filter(pk=notif_id, recipient=self.user).update(is_read=True)