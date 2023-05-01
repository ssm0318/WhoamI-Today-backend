import textwrap


def wrap_content(content):
    content_as_string = str(content)
    wrap_result = textwrap.shorten(content_as_string, width=18, placeholder='...')
    if wrap_result != '...':
        return wrap_result
    return f'{content_as_string[:15].rstrip()}...'
