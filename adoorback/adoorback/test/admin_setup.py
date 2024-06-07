import pandas as pd

from django.contrib.auth import get_user_model
from qna.models import Question


def set_product_seed():
    User = get_user_model()

    if not User.objects.filter(username='me').exists():
        admin = User.objects.create_superuser(
            username='me', email='team.whoami.today@gmail.com', password='1+1==Gwiyomi')
        admin.profile_image.save('adoorback/adoorback/media/profile_images/me.png',
                                 open('adoorback/assets/logo.png', 'rb'))
        print("admin me profile created!")
    else:
        admin = User.objects.get(username='me')
        print("admin me already exists!")

    df = pd.read_csv("adoorback/assets/questions.tsv", delimiter='\t')

    print("last Question id before import: ", Question.objects.first().id)
    for index, row in df.iterrows():
        Question.objects.get_or_create(author=admin, is_admin_question=True,
                                       content_ko=row.iloc[0], content_en=row.iloc[1])

    print("last Question id after import: ", Question.objects.first().id)
