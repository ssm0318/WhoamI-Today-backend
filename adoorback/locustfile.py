import random

from locust import HttpUser, task, between


class WebsiteUser(HttpUser):
    wait_time = between(5, 15)
    host = 'http://localhost:8000'

    def on_start(self):
        response = self.client.get('/api/user/token/anonymous/')
        csrf_token = response.cookies['csrftoken']

        response = self.client.post('/api/user/login/',
                                    json={"username": "adoor_user", "password": "adoor2020:)"},
                                    headers={"X-CSRFToken": csrf_token})
        if response.status_code != 204:
            print(str(response.status_code) + " login")

    # Friend Feed Related
    @task
    def get_search_results(self):
        response = self.client.get("/api/user/search/?query=a")
        if response.status_code != 200:
            print(str(response.status_code) + " get search results")

    @task
    def get_current_user(self):
        response = self.client.get("/api/user/me/")
        if response.status_code != 200:
            print(str(response.status_code) + " get current user profile")

    @task
    def get_current_user_friends(self):
        response = self.client.get("/api/user/me/friends/")
        if response.status_code != 200:
            print(str(response.status_code) + " get current user friend list")

    @task
    def get_recommended_questions(self):
        response = self.client.get("/api/feed/questions/daily/recommended/")
        if response.status_code != 200:
            print(str(response.status_code) + " get friend feed")

    @task
    def get_daily_questions(self):
        response = self.client.get("/api/feed/questions/daily/")
        if response.status_code != 200:
            print(str(response.status_code) + " get friend feed")

    @task(20)
    def get_notifications(self):
        response = self.client.get("/api/notifications/")
        if response.status_code != 200:
            print(str(response.status_code) + " get notifications")

    @task(5)
    def get_friend_feed(self):
        response = self.client.get("/api/feed/friend/")
        if response.status_code != 200:
            print(str(response.status_code) + " get friend feed")

    # Anonymous Feed Related
    @task(3)
    def get_anonymous_feed(self):
        response = self.client.get("/api/feed/anonymous/")
        if response.status_code != 200:
            print(str(response.status_code) + " get anonymous feed")

    # Question Feed Related
    @task
    def get_questions_feed(self):
        response = self.client.get("/api/feed/questions/")
        if response.status_code != 200:
            print(str(response.status_code) + " get questions feed")

    @task(3)
    def get_questions_detail(self):
        response = self.client.get("/api/feed/questions/5/")
        if response.status_code != 200:
            print(str(response.status_code) + " get questions detail")

    # Create Methods
    @task
    def post_question(self):
        response = self.client.get('/api/user/token/anonymous/')
        csrf_token = response.cookies['csrftoken']

        response = self.client.post("/api/feed/questions/",
                                    json={"content": "test content",
                                          "share_anonymously": random.choice([True, False])},
                                    headers={"X-CSRFToken": csrf_token})
        if response.status_code != 201:
            print(str(response.status_code) + " post question")

    @task(2)
    def post_question_response(self):
        response = self.client.get('/api/user/token/anonymous/')
        csrf_token = response.cookies['csrftoken']

        response = self.client.post("/api/feed/responses/",
                                    json={"content": "test content",
                                          "question_id": 5,
                                          "share_anonymously": random.choice([True, False])},
                                    headers={"X-CSRFToken": csrf_token})
        if response.status_code != 201:
            print(str(response.status_code) + " post response")

    @task
    def post_article(self):
        response = self.client.get('/api/user/token/anonymous/')
        csrf_token = response.cookies['csrftoken']

        response = self.client.post("/api/feed/articles/",
                                    json={"content": "test content",
                                          "share_anonymously": random.choice([True, False])},
                                    headers={"X-CSRFToken": csrf_token})
        if response.status_code != 201:
            print(str(response.status_code) + " post article")

    @task(2)
    def post_anonymous_comment(self):
        response = self.client.get('/api/user/token/anonymous/')
        csrf_token = response.cookies['csrftoken']

        response = self.client.post("/api/comments/",
                                    json={"content": "test content",
                                          "target_id": random.randint(1, 1000),
                                          "target_type": "Article",
                                          "is_anonymous": True},
                                    headers={"X-CSRFToken": csrf_token})
        if response.status_code != 201:
            print(str(response.status_code) + " post anonymous comment")

    @task(2)
    def post_friend_comment(self):
        response = self.client.get('/api/user/token/anonymous/')
        csrf_token = response.cookies['csrftoken']

        response = self.client.post("/api/comments/",
                                    json={"content": "test content",
                                          "target_id": random.randint(1, 1000),
                                          "target_type": "Response",
                                          "is_anonymous": False},
                                    headers={"X-CSRFToken": csrf_token})
        if response.status_code != 201:
            print(str(response.status_code) + " post friend comment")

    @task(2)
    def post_anonymous_like(self):
        response = self.client.get('/api/user/token/anonymous/')
        csrf_token = response.cookies['csrftoken']

        response = self.client.post("/api/likes/",
                                    json={"target_id": random.randint(1, 1000),
                                          "target_type": "Article",
                                          "is_anonymous": True},
                                    headers={"X-CSRFToken": csrf_token})
        if response.status_code != 201:
            print(str(response.status_code) + " post anonymous like")

    @task(2)
    def post_friend_like(self):
        response = self.client.get('/api/user/token/anonymous/')
        csrf_token = response.cookies['csrftoken']

        response = self.client.post("/api/likes/",
                                    json={"target_id": random.randint(1, 1000),
                                          "target_type": "Question",
                                          "is_anonymous": False},
                                    headers={"X-CSRFToken": csrf_token})
        if response.status_code != 201:
            print(str(response.status_code) + " post friend like")

    @task
    def post_response_request(self):
        response = self.client.get('/api/user/token/anonymous/')
        csrf_token = response.cookies['csrftoken']

        from django.contrib.auth import get_user_model
        User = get_user_model()
        current_user = User.objects.get(username="adoor_user")

        response = self.client.post("/api/feed/questions/response-request/",
                                    json={"question_id": 5,
                                          "requester_id": current_user.id,
                                          "requestee_id": random.choice(current_user.friend_ids)},
                                    headers={"X-CSRFToken": csrf_token})
        if response.status_code != 201:
            print(str(response.status_code) + " post response request")

    # Account Related
    @task
    def get_user_detail(self):
        response = self.client.get("/api/user/5/")
        if response.status_code != 200:
            print(str(response.status_code) + " get other user detail")

    @task
    def post_friend_request(self):
        response = self.client.get('/api/user/token/anonymous/')
        csrf_token = response.cookies['csrftoken']

        from django.contrib.auth import get_user_model
        User = get_user_model()
        current_user = User.objects.get(username="adoor_user")
        non_friend_ids = set(list(User.objects.values_list('id', flat=True))) - \
                         set(current_user.friend_ids)

        response = self.client.post("/api/user/friend-requests/",
                                    json={"question_id": 5,
                                          "requester_id": current_user.id,
                                          "requestee_id": random.choice(list(non_friend_ids))},
                                    headers={"X-CSRFToken": csrf_token})
        if response.status_code != 201:
            print(str(response.status_code) + " post response request")
