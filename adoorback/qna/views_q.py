from qna.serializers_q import QResponseSerializer
from qna.views import ResponseCreate, ResponseDetail


class QResponseCreate(ResponseCreate):
    """Response create for Version Q (likes only, no reactions)."""
    serializer_class = QResponseSerializer


class QResponseDetail(ResponseDetail):
    """Response detail for Version Q (likes only, no reactions)."""
    serializer_class = QResponseSerializer
