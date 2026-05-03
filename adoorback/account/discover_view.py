from datetime import timedelta
import random
from collections import defaultdict
from itertools import chain
from operator import attrgetter
from zoneinfo import ZoneInfo

from django.db.models import F
from rest_framework.views import APIView
from rest_framework.response import Response as DjangoResponse
from rest_framework.permissions import IsAuthenticated

from account.models import DiscoverFeed, DiscoverFeedMusic, User
from adoorback.utils.validators import adoor_exception_handler
from note.models import Note, ShareType
from qna.models import Response as _Response, Question
from adoorback.models import Mission
from check_in.models import Song, CheckIn as CheckInModel
from account.serializers import viewer_sees_check_in_component
from note.serializers import NoteSerializer
from qna.serializers import ResponseSerializer, QuestionBaseSerializer
from adoorback.serializers import MissionSerializer
from account.serializers import DiscoverFeedMusicSerializer  # if not exists, we'll serialize songs manually

class DiscoverFeedView(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request):
        user = request.user
        
        # Determine 6-hour boundary (PDT: 7am, 1pm, 7pm, 1am)
        la_tz = ZoneInfo('America/Los_Angeles')
        now_la = timezone.now().astimezone(la_tz)
        
        hour = now_la.hour
        if hour >= 19:
            boundary_hour = 19
        elif hour >= 13:
            boundary_hour = 13
        elif hour >= 7:
            boundary_hour = 7
        else:
            boundary_hour = 1

        recent_boundary = now_la.replace(hour=boundary_hour, minute=0, second=0, microsecond=0)
        if hour < 1:
            recent_boundary -= timedelta(days=1)
            recent_boundary = recent_boundary.replace(hour=19) # previous day 7pm

        last_feed = DiscoverFeed.objects.filter(user=user, category='recommended').order_by('-created_at').first()
        needs_new_feed = False
        if not last_feed:
            needs_new_feed = True
        else:
            last_feed_la = last_feed.created_at.astimezone(la_tz)
            if last_feed_la < recent_boundary:
                needs_new_feed = True
                
        if needs_new_feed:
            self.generate_new_feed(user, batch_time=timezone.now())

        # Now fetch from DiscoverFeed and DiscoverFeedMusic
        # Since music is shuffled on every entry, we'll shuffle it here
        # Return structured JSON
        
