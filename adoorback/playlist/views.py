import uuid

from django.utils import timezone
from django.db.models import Q
from django.contrib.auth import get_user_model

from rest_framework import generics, permissions

from check_in.models import Song
from playlist.serializers import SongSerializer
from playlist.models import PlaylistFeed

User = get_user_model()


class SongList(generics.ListAPIView):
    """
    List (Feed): Returns songs based on 'type' parameter.
    """
    serializer_class = SongSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        filter_type = self.request.query_params.get('type')

        # Ensure daily digest exists
        feed_entries = self._get_or_create_daily_feed(user)

        # Filter by type if specified (subset of daily digest)
        if filter_type:
            categories = [c.strip() for c in filter_type.split(',')]
            feed_entries = feed_entries.filter(category__in=categories)

        return [entry.song for entry in feed_entries]

    def _get_or_create_daily_feed(self, user):
        base_qs = Song.objects.filter(is_active=True)

        now = timezone.now()
        last_feed = PlaylistFeed.objects.filter(user=user).order_by('-created_at').first()

        # Check validity (Date change in user timezone)
        user_timezone = getattr(user, 'timezone', 'UTC')
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(user_timezone)
        except ImportError:
            tz = timezone.get_current_timezone()

        now_local = now.astimezone(tz)
        needs_new_feed = False

        if not last_feed:
            needs_new_feed = True
        else:
            last_feed_local = last_feed.created_at.astimezone(tz)
            if now_local.date() > last_feed_local.date():
                needs_new_feed = True

        if needs_new_feed:
            self.generate_new_feed(user, base_qs)

        latest_feed_entry = PlaylistFeed.objects.filter(user=user).order_by('-created_at').first()
        if not latest_feed_entry:
            return PlaylistFeed.objects.none()

        return PlaylistFeed.objects.filter(
            user=user,
            feed_id=latest_feed_entry.feed_id,
            song__user__current_ver=user.current_ver,
        ).select_related('song', 'song__user').order_by('sort_order')

    def generate_new_feed(self, user, base_qs):
        # Recalculate exclusion and discovery logic exclusively for Feed Generation
        # This duplicates some logic but ensures independence.
        
        # Exclude IDs
        exclude_ids = set(user.friend_ids + user.close_friend_ids + user.user_report_blocked_ids + [user.id])

        # 1. Mutual Friends (same version only)
        user_friends = user.connected_users.filter(current_ver=user.current_ver)
        user_friend_ids = set(user_friends.values_list('id', flat=True))
        mutual_friend_potential_ids = set()
        for friend in user_friends:
            friend_of_friend_ids = set(friend.connected_users.filter(
                current_ver=user.current_ver
            ).values_list('id', flat=True))
            mutual_friend_potential_ids.update(friend_of_friend_ids)
        
        mf_ids = mutual_friend_potential_ids - user_friend_ids - exclude_ids
        
        # 2. Mutual Traits
        user_interests = set(user.user_interests.values_list('id', flat=True))
        user_personas = set(user.user_personas.values_list('id', flat=True))
        
        trait_users_qs = User.objects.filter(
            Q(user_interests__id__in=user_interests) | Q(user_personas__id__in=user_personas),
            current_ver=user.current_ver
        ).exclude(id__in=exclude_ids)
        trait_ids = set(trait_users_qs.values_list('id', flat=True))

        # 3. Anonymous (Strangers)
        stranger_users_qs = User.objects.filter(
            current_ver=user.current_ver
        ).exclude(
            id__in=exclude_ids | mf_ids | trait_ids
        ).exclude(is_superuser=True)
        stranger_ids = set(stranger_users_qs.values_list('id', flat=True))

        # Helper to get Song candidates
        def get_candidates(user_ids, limit=20):
            return list(base_qs.filter(
                user_id__in=user_ids,
            ).order_by('-created_at')[:limit])

        mf_candidates = get_candidates(mf_ids)
        trait_candidates = get_candidates(trait_ids)
        stranger_candidates = get_candidates(stranger_ids)

        category_candidates = [
            (mf_candidates, 'mutual_friends'),
            (trait_candidates, 'mutual_traits'),
            (stranger_candidates, 'anonymous')
        ]
        
        feed_items = []
        existing_obj_ids = set()
        
        # Step 1: Ensure at least 1 from each category
        for candidates, category in category_candidates:
            while candidates:
                cand = candidates.pop(0)
                if cand.id not in existing_obj_ids:
                    feed_items.append((cand, category))
                    existing_obj_ids.add(cand.id)
                    break

        # Step 2: Round-robin fill
        while len(feed_items) < 10:
            added_in_round = False
            for candidates, category in category_candidates:
                if len(feed_items) >= 10: break
                
                while candidates:
                    cand = candidates.pop(0)
                    if cand.id not in existing_obj_ids:
                        feed_items.append((cand, category))
                        existing_obj_ids.add(cand.id)
                        added_in_round = True
                        break
            if not added_in_round:
                break
        
        # Step 3: Fallback (Random)
        if len(feed_items) < 10:
            fallback_qs = base_qs\
                .exclude(user_id__in=exclude_ids)\
                .exclude(id__in=existing_obj_ids)\
                .order_by('?')[:(10 - len(feed_items))]
            
            for item in fallback_qs:
                feed_items.append((item, 'random'))

        # Sort Newest First
        feed_items.sort(key=lambda x: x[0].created_at, reverse=True)
        
        # Save to DB
        timestamp = timezone.now()
        feed_id = uuid.uuid4()
        new_feeds = []
        for i, (song, category) in enumerate(feed_items):
            new_feeds.append(PlaylistFeed(
                user=user,
                song=song,
                category=category,
                created_at=timestamp,
                sort_order=i,
                feed_id=feed_id
            ))
        PlaylistFeed.objects.bulk_create(new_feeds)
