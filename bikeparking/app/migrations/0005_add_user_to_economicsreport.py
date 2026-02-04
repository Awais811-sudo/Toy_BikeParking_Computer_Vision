# app/migrations/000X_add_user_to_economicsreport.py
from django.db import migrations, models
from django.conf import settings

class Migration(migrations.Migration):

    dependencies = [
        ('app', '0004_delete_subscriptionpayment'),  # replace with your last migration
    ]

    operations = [
        migrations.AddField(
            model_name='economicsreport',
            name='user',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=models.SET_NULL,
                null=True,
                blank=True
            ),
        ),
    ]
