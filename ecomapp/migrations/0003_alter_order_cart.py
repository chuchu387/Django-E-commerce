# Generated by Django 5.0.1 on 2024-03-01 20:04

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ecomapp', '0002_alter_order_cart'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='cart',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='ecomapp.cart'),
        ),
    ]