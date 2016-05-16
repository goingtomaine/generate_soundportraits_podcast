from bs4 import BeautifulSoup
from datetime import datetime
from datetime import timedelta
import html
from mutagen.mp3 import MPEGInfo
import os
import requests
from tempfile import NamedTemporaryFile
from tqdm import tqdm

air_dict = {
    'http://soundportraits.org/on-air/execution_tapes/': datetime(2001, 1, 1),
    'http://soundportraits.org/on-air/marriage_broker/': datetime(1990, 2, 11),
    'http://soundportraits.org/on-air/last_day_at_the_automat/':
    datetime(1991, 4, 9)
}

bad_shows = set(['http://soundportraits.org/on-air/youth_portraits/',
                 'http://soundportraits.org/on-air/yiddish_radio_project/'])


def content_tag(name_str, content_str):
    """
    Generates a name_str tag, with content_str content.
    :param str name_str:
    :param str content_str:
    :returns str:
    """
    return '<{}>{}</{}>'.format(name_str, content_str, name_str)


def sub_string(string, start_str, end_str):
    """
    Dumb search for the first instance of a string wrapped by start_str
    and end_str. Could be a regex, but this should be (needlessly) faster.
    :param str string:
    :param str start_str:
    :param str end_str:
    :returns str:
    """
    substr = string[string.find(start_str) + len(start_str):]
    substr = substr[:substr.find(end_str)]
    return substr


def soundportraits_show_urls():
    """
    Visits http://www.soundportraits.org/on-air/
    and gets a list of show URLs.
    :returns list:
    """
    r = requests.get('http://www.soundportraits.org/on-air/')
    bs = BeautifulSoup(r.text, 'lxml')
    urls = [x['href'] for x in bs.findAll('a') if x.has_attr('href')]
    urls = [x for x in urls if x.find(
        'http://soundportraits.org/on-air/') > -1]
    return list(set(urls) - bad_shows)


def parsed_show_page(show_page_url):
    """
    Takes a Sound Portraits episode and finds out some salient information
    This entails downloading the episode to get duration data, so it is _slow_
    :param str show_page_url:
    :returns tuple: Data about this Sound Portraits episode, None if no MP3
    """
    r = requests.get(show_page_url)
    bs = BeautifulSoup(r.text, 'lxml')

    title = html.unescape(bs.title.contents[0].split(':')[0]).strip()

    if show_page_url in air_dict:
        premiere = air_dict[show_page_url]

    else:
        premiere = sub_string(r.text,
                              '<!-- Start premiere info -->',
                              '<!-- Start premiere info -->').strip()
        premiere = sub_string(premiere,
                              'Premiered ',
                              ', on').strip()
        premiere = datetime.strptime(premiere, '%B %d, %Y')

    body = sub_string(r.text,
                      '<!-- Start body text -->',
                      '<!--End body text -->').strip()
    body = ' '.join(body.split())
    body = body.replace(' </p> <p> ', '\n')
    body = body.replace('</p> <p>', '\n')
    body = body.replace('<p>', '')
    body = BeautifulSoup(html.unescape(body), 'lxml').text.strip()

    if show_page_url[-1] == '/':
        audio_page_url = '{}audio.php'.format(show_page_url)
    else:
        audio_page_url = '{}/audio.php'.format(show_page_url)

    try:
        r = requests.get(audio_page_url)
        bs = BeautifulSoup(r.text, 'lxml')
        flashvars = bs.find('param', {'name': 'FlashVars'})['value']
        soundfile = sub_string(flashvars, 'soundFile=', '.mp3') + '.mp3'
        soundfile = soundfile.replace('%2F', '/').replace('%3A', ':')

        r = requests.get(soundfile)
        temp = NamedTemporaryFile()
        temp.write(r.content)
        duration = MPEGInfo(temp).length
        size = os.stat(temp.name).st_size
        temp.close()

    except:
        # If we can't find the sound file page, forget it.
        return None

    return (premiere, title, body, soundfile, duration, size)


def feed_entry(data_tuple):
    """
    Turn a data tuple into a Podcast RSS Entry
    :param tuple data_tuple: (time, title, description, url, duration)
    :returns str: Podcast RSS <item> tag as a string
    """
    post_date, title, body, url, duration, size = data_tuple
    return '<item>\n\t' + '\n\t'.join([
        content_tag('title', title),
        content_tag('link', url),
        content_tag('guid', url),
        content_tag('description', body),
        '<enclosure url="{}" length="{}" type="audio/mpeg"/>'.format(url,
                                                                     size),
        content_tag('category', 'Podcasts'),
        content_tag(
            'pubDate', '{} 00:00:00 +0000'.format(
                post_date.strftime('%a, %d %b %Y'))),
        content_tag('itunes:duration',
                    str(timedelta(seconds=int(duration + 1)))),
        content_tag('itunes:author', 'Sound Portraits Productions'),
        content_tag('itunes:explicit', 'No'),
        content_tag('itunes:subtitle', body[:79] + '…'),
        content_tag('itunes:summary', body)
    ]) + '\n</item>'


def main():
    """Generate a new RSS file"""
    show_urls = soundportraits_show_urls()
    data = []
    data = [parsed_show_page(url) for url in tqdm(show_urls)]
    data = [datum for datum in data if datum is not None]

    data.sort(key=lambda x: x[0])
    feed_entries = '\n'.join([feed_entry(datum) for datum in data])
    header = open('header.xml', 'r').read()

    with open('soundportraits.rss', 'w') as outfile:
        outfile.write(header.strip() + '\n')
        outfile.write(feed_entries + '\n')
        outfile.write('</channel></rss>\n')


if __name__ == "__main__":
    main()
