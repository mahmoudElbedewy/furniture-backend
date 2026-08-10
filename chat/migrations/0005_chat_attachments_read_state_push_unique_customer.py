import django.db.models.deletion
from django.db import migrations, models


def merge_duplicate_customer_conversations(apps, schema_editor):
    ChatConversation = apps.get_model("chat", "ChatConversation")
    ChatMessage = apps.get_model("chat", "ChatMessage")

    identifiers = (
        ChatConversation.objects.values_list("customer_identifier", flat=True)
        .order_by("customer_identifier")
        .distinct()
    )
    for identifier in identifiers:
        conversations = list(
            ChatConversation.objects.filter(customer_identifier=identifier).order_by(
                "-last_message_at", "created_at"
            )
        )
        if len(conversations) <= 1:
            continue

        keeper = conversations[0]
        duplicate_ids = [conversation.id for conversation in conversations[1:]]
        ChatMessage.objects.filter(conversation_id__in=duplicate_ids).update(
            conversation_id=keeper.id
        )
        ChatConversation.objects.filter(id__in=duplicate_ids).delete()


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("chat", "0004_remove_chatconversation_force_agent_auto"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatconversation",
            name="admin_last_read_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="chatconversation",
            name="customer_last_read_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="chatmessage",
            name="content",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.CreateModel(
            name="CustomerPushSubscription",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("customer_identifier", models.CharField(db_index=True, max_length=100)),
                ("endpoint", models.TextField(unique=True)),
                ("p256dh", models.TextField()),
                ("auth", models.TextField()),
                ("user_agent", models.CharField(blank=True, default="", max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="ChatAttachment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("image", models.ImageField(upload_to="chat_attachments/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "message",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="chat.chatmessage",
                    ),
                ),
            ],
        ),
        migrations.RunPython(
            merge_duplicate_customer_conversations, migrations.RunPython.noop
        ),
        migrations.AddConstraint(
            model_name="chatconversation",
            constraint=models.UniqueConstraint(
                fields=("customer_identifier",), name="unique_chat_per_customer"
            ),
        ),
    ]
