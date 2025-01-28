from django.db import models

from django.conf import settings
from django.db import models
from django.db.models import Q
from safedelete.models import SafeDeleteModel
from safedelete import SOFT_DELETE_CASCADE

from adoorback.models import AdoorTimestampedModel

def get_default_owner():
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.filter(is_superuser=True).first().id if User.objects.filter(is_superuser=True).exists() else User.objects.first().id

class Category(AdoorTimestampedModel, SafeDeleteModel):
    HIERARCHY_CHOICES = [
        ('public', 'Public'),
        ('follower', 'Follower'),
        ('friend', 'Friend'),
        ('private', 'Private'),
    ]

    name = models.CharField(max_length=100)
    added_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='added_categories', 
        blank=True
    )
    sharing_scope = models.CharField(
        max_length=255,
        choices=HIERARCHY_CHOICES,
        default='public'
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_categories',
        default=get_default_owner
    )

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        verbose_name_plural = "categories"
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['sharing_scope']),
        ]

    def __str__(self):
        return self.name


class Subscription(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='category_subscriptions', on_delete=models.CASCADE)
    category = models.ForeignKey(Category, related_name='subscriptions', on_delete=models.CASCADE)
    _safedelete_policy = SOFT_DELETE_CASCADE
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'category'], 
                condition=Q(deleted__isnull=True),
                name='unique_user_category_subscription'
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'category']),
        ]

    def __str__(self):
        return f'{self.user} subscribed to {self.category}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)