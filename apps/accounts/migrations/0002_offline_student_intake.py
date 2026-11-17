import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('routes', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='must_change_password',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='studentprofile',
            name='guardian_name',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AddField(
            model_name='studentprofile',
            name='guardian_phone',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='studentprofile',
            name='preferred_route',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='preferred_by_students',
                to='routes.route',
            ),
        ),
        migrations.AddField(
            model_name='studentprofile',
            name='preferred_pickup_stop',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='preferred_pickup_students',
                to='routes.busstop',
            ),
        ),
        migrations.AddField(
            model_name='studentprofile',
            name='preferred_drop_stop',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='preferred_drop_students',
                to='routes.busstop',
            ),
        ),
    ]
