"""Generates missions.example.xlsx — a sample Mission content file with 8 representative rows.

Usage (run from the backend repo root):
    python adoorback/adoorback/assets/missions.example.gen.py

Re-run any time to regenerate the example xlsx. Both this script AND the
generated missions.example.xlsx are committed.
"""
from pathlib import Path

from openpyxl import Workbook


HEADERS = ['status', 'slug', 'prompt_en', 'prompt_ko', 'type']

ROWS = [
    # Buffer day before study (April 30, day -3 — first scheduled date).
    ('added', 'm_buffer_pre_d1',
     "Take a moment to set an intention for the next four weeks.",
     "앞으로 4주 동안의 다짐을 한 줄로 적어보세요.",
     'text'),

    # First study day (May 3, day 1).
    ('added', 'm_study_w1_d1',
     "Share a song that captures how you want this week to feel.",
     "이번 주 분위기를 담은 노래를 공유해보세요.",
     'song'),

    # Mid-study (May 16, day 14).
    ('added', 'm_study_w2_d14',
     "Send a compliment to a friend you haven't talked to recently.",
     "오랜만인 친구에게 칭찬 한마디를 보내보세요.",
     'compliment'),

    # Last study day (May 30, day 28).
    ('added', 'm_study_w4_d28',
     "Looking back at the past four weeks — what surprised you?",
     "지난 4주를 돌아보며 — 가장 놀라웠던 점은?",
     'text'),

    # Buffer day after study (May 31, day +1).
    ('added', 'm_buffer_post_d1',
     "Ask someone how their day has been, and really listen.",
     "오늘 누군가에게 어떻게 지냈는지 묻고, 진심으로 들어보세요.",
     'question'),

    # Long-term general mission (no schedule — random rotation pool).
    # Slug doesn't follow the m_buffer_/m_study_/m_buffer_post_ pattern,
    # so the schedule migration ignores it. The cron picks it on ordinary days.
    ('added', 'm_general_001',
     "Send a song you've had on repeat lately to a close friend.",
     "요즘 반복해서 듣는 노래를 친한 친구에게 보내보세요.",
     'song'),

    # Example of a 'modified' row (lifecycle demonstration).
    # On first import this gets treated as 'added' since the slug doesn't exist yet.
    # The user changes status to 'modified' on subsequent edits.
    ('modified', 'm_general_002',
     "Compliment a stranger today.",
     "오늘 모르는 사람에게 칭찬 한마디 해보세요.",
     'compliment'),

    # Example of a 'removed' row (lifecycle demonstration).
    # NOTE: a 'removed' row will be REJECTED by the loader if the slug has any
    # selected_dates entries. Test with an unscheduled slug only.
    ('removed', 'm_general_003',
     "",  # prompt_en ignored for removed
     "",
     ''),  # type ignored for removed
]


def main():
    wb = Workbook()
    ws = wb.active
    ws.title = 'Missions'
    ws.append(HEADERS)
    for row in ROWS:
        ws.append(list(row))
    out = Path(__file__).parent / 'missions.example.xlsx'
    wb.save(out)
    print(f'Wrote {out} ({len(ROWS)} rows + header).')


if __name__ == '__main__':
    main()
