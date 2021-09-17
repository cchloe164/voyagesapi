# Generated by Django 3.2.6 on 2021-09-17 15:08

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('voyage', '0002_remove_voyage_voyage_sources'),
    ]

    operations = [
        migrations.AddField(
            model_name='voyage',
            name='voyage_sources',
            field=models.ManyToManyField(blank=True, related_name='sources', through='voyage.VoyageSourcesConnection', to='voyage.VoyageSources'),
        ),
        migrations.AlterField(
            model_name='voyagesourcesconnection',
            name='group',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='source_groups', to='voyage.voyage'),
        ),
        migrations.AlterField(
            model_name='voyagesourcesconnection',
            name='source',
            field=models.ForeignKey(blank=True, on_delete=django.db.models.deletion.CASCADE, related_name='voyage_sources', to='voyage.voyagesources'),
        ),
    ]
