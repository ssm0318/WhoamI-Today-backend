from note.serializers_q import QNoteSerializer
from note.views import NoteCreate, NoteDetail


class QNoteCreate(NoteCreate):
    """Note creation for Version Q (no share_type, likes only)."""
    serializer_class = QNoteSerializer


class QNoteDetail(NoteDetail):
    """Note detail for Version Q (no share_type, likes only)."""
    serializer_class = QNoteSerializer
