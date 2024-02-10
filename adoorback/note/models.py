from django.db import models
from safedelete.models import SafeDeleteModel

from adoorback.models import AdoorModel


class Note(AdoorModel, SafeDeleteModel):
    pass