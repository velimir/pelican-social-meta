# -*- coding: utf-8 -*- #
"""
in this order:
TODO: refactor
TODO: add docs
"""
from __future__ import unicode_literals

import os
import logging
import json

from bs4 import BeautifulSoup

from pelican import contents, signals
from pelican.generators import ArticlesGenerator, PagesGenerator
from pelican.contents import Page, Article
from pelican.urlwrappers import Author

from PIL import Image
from io import BytesIO
from os import path

TWITTER_IMAGE_MAX_SIZE = 1000 * 1000
IMAGE_RESIZE_STEP = 2 ** 6


logger = logging.getLogger(__name__)


def _get_page_image_info(instance):
    image = None
    if hasattr(instance, 'image'):
        image = instance.image
    settings = instance.settings
    image = settings['DEFAULT_HEADER_IMAGE'] if not image else image
    return _get_image_info(settings, settings['PATH'], image)


def _get_image_info(settings, base_dir, image_path):
    url = path.join(settings['SITEURL'], image_path)
    i = Image.open(path.join(base_dir, image_path))
    return {
        'width': i.width,
        'height': i.height,
        'type': 'image/{}'.format(i.format.lower()),
        'url': url,
        'path': image_path
    }


def _save_image(image_path, image):
    directory = path.dirname(image_path)
    if not path.exists(directory):
        os.makedirs(directory)

    image.save(image_path, quality=95, optimize=True)


def _make_publisher_image(settings, image_url, ext='.png', size=(60, 60)):
    src_path = path.join(settings['PATH'], image_url)
    name, _ = path.splitext(path.basename(image_url))

    image_path = path.join('images', 'logos', name + ext)
    out_dir = settings['OUTPUT_PATH']
    dst_path = path.join(out_dir, image_path)
    if path.exists(dst_path):
        return _get_image_info(settings, out_dir, image_path)

    image = Image.open(src_path)
    image.thumbnail(size)
    _save_image(dst_path, image)

    return _get_image_info(settings, out_dir, image_path)


def _twitterize_image(settings, image_info):
    return _thumbnail_image(settings, image_info,
                            TWITTER_IMAGE_MAX_SIZE, 'twitter-cards')


def _thumbnail_image(settings, image_info, max_size, directory):
    src_path = path.join(settings['PATH'], image_info['path'])
    src_size = path.getsize(src_path)
    if not src_size > max_size:
        return image_info

    image_path = path.join('images', directory, path.basename(src_path))
    out_dir = settings['OUTPUT_PATH']
    dst_path = path.join(out_dir, image_path)
    if path.exists(dst_path):
        return _get_image_info(settings, out_dir, image_path)

    image = Image.open(src_path)
    _reduce_image_size(image, max(image.width, image.height))

    _save_image(dst_path, image)

    return _get_image_info(settings, out_dir, image_path)


def _saved_image_size(image):
    img_file = BytesIO()
    image.save(img_file, image.format, quality=95, optimize=True)
    return img_file.tell()


def _reduce_image_size(image, side_size):
    logger.debug('reducing image size: %s', side_size)
    image.thumbnail((side_size, side_size))
    if _saved_image_size(image) > TWITTER_IMAGE_MAX_SIZE:
        _reduce_image_size(image, side_size - IMAGE_RESIZE_STEP)


def _get_page_type(instance):
    if isinstance(instance, contents.Article):
        return 'article'
    return 'website'


def _get_page_url(instance):
    site_url = instance.settings['SITEURL']
    return path.join(site_url, instance.url)


def strip_tags(func):
    def remove_tags(*args, **kwargs):
        soup = BeautifulSoup(func(*args, **kwargs), "html.parser")
        return soup.get_text()
    return remove_tags


def _get_page_description(instance):
    return instance.metadata.get('summary', instance.summary)


def _get_page_title(instance):
    return instance.title


def _get_create_date(instance):
    return instance.date.isoformat()


def _get_modified_date(instance):
    if hasattr(instance, 'modified'):
        return instance.modified.isoformat()


def _get_tags(instance):
    try:
        return [tag.name for tag in instance.tags]
    except AttributeError:
        return []


def _tag_author(author):
    settings = author.settings
    image_info = _get_image_info(settings, settings['PATH'], author.picture)
    info = {
        'object':      author,
        'title':       author.name,
        'type':        'profile',
        'image':       image_info,
        'url':         _get_page_url(author),
        'description': author.bio,
        'site_name':   author.settings['SITENAME'],
        'first_name':  author.first_name,
        'last_name':   author.last_name,
        'gender':      author.gender,
        'username':    author.username,
        'twitter':     author.twitter
    }

    tags = _make_tags(info, settings)
    _set_attrs(author, tags)


def _tag_article(article):
    page_info = {
        'object':         article,
        'title':          _get_page_title(article),
        'type':           'article',
        'image':          _get_page_image_info(article),
        'url':            _get_page_url(article),
        'description':    _get_page_description(article),
        'site_name':      article.settings['SITENAME'],
        'published_time': _get_create_date(article),
        'section':        article.category.name,
        'tags':           _get_tags(article)
    }

    modified = _get_modified_date(article)
    if modified:
        page_info['modified_time'] = modified

    page_info['authors'] = article.authors

    tags = _make_tags(page_info, article.settings)
    _set_attrs(article, tags)


def _tag_generator(generator):
    settings = generator.settings
    image = settings['DEFAULT_HEADER_IMAGE']
    image_info = _get_image_info(settings, settings['PATH'], image)
    page_info = {
        'object':      generator,
        'image':       image_info,
        'title':       settings['SITENAME'],
        'type':        'website',
        'url':         settings['SITEURL'],
        'description': settings['SITE_DESCRIPTION'],
        'site_name':   settings['SITENAME']
    }
    tags = _make_tags(page_info, generator.settings)
    generator.context.update(tags)


def _tag_page(page):
    page_info = {
        'object':      page,
        'title':       _get_page_title(page),
        'type':        'website',
        'image':       _get_page_image_info(page),
        'url':         _get_page_url(page),
        'description': _get_page_description(page),
        'site_name':   page.settings['SITENAME']
    }
    tags = _make_tags(page_info, page.settings)
    _set_attrs(page, tags)


def _set_attrs(obj, attrs):
    for k, v in attrs.iteritems():
        setattr(obj, k, v)
    return obj


def _make_tags(info, settings):
    providers = {
        'og_tags': _make_og_tags,
        'twitter_tags': _make_twitter_tags,
        'meta_tags': _make_common_tags,
        'ld_json': _make_ld_json
    }
    tags = {}
    for name, fn in providers.iteritems():
        tags[name] = fn(info, settings)

    return tags


def _make_common_tags(info, settings):
    metas = {
        'description': info['description']
    }
    return metas.items()


def _make_twitter_tags(info, settings):
    image_info = _twitterize_image(settings, info['image'])
    metas = {
        'twitter:title': info['title'],
        'twitter:description': info['description'],
        'twitter:image': image_info['url']
    }

    width = image_info['width']
    height = image_info['height']
    if width >= 280 and height >= 150:
        metas['twitter:card'] = 'summary_large_image'

    ptype = info['type']
    if 'article' == ptype:
        author = info['authors'][0]
        twitter_id = author.twitter
        metas['twitter:site'] = twitter_id

    elif 'profile' == ptype:
        metas['twitter:site'] = info['twitter']

    else:
        author_name = settings['AUTHOR']
        username = settings['AUTHORS'][author_name]['twitter']
        metas['twitter:site'] = username

    return metas.items()


def _image_ld_info(image):
    return {
        '@type': 'ImageObject',
        'url': image['url'],
        'width': image['width'],
        'height': image['height']
    }


def _make_ld_index(generator):
    settings = generator.settings
    image = settings['DEFAULT_HEADER_IMAGE']
    image_info = _get_image_info(settings, settings['PATH'], image)
    blog_posting = [_make_ld_article(it) for it in generator.articles]
    return {
        '@context': 'http://schema.org',
        '@type': 'Blog',
        'name': settings['SITENAME'],
        'url': settings['SITEURL'],
        'mainEntityOfPage': settings['SITEURL'],
        'image': _image_ld_info(image_info),
        'description': settings['SITE_DESCRIPTION'],
        'blogPost': blog_posting,
        'publisher': _make_ld_publisher(settings)
    }


def _make_ld_page(page):
    logger.debug('page %s', page)
    if hasattr(page, 'ld_json'):
        return json.loads(page.ld_json)

    if 'about' == page.slug:
        settings = page.settings
        image = _get_page_image_info(page)
        return {
            '@context': 'http://schema.org',
            '@type': 'AboutPage',
            'name':   settings['SITENAME'],
            'url': _get_page_url(page),
            'image': _image_ld_info(image),
            'description': _get_page_description(page),
            'publisher': _make_ld_publisher(settings)
        }


def _make_ld_article(article):
    if hasattr(article, 'ld_json'):
        return json.loads(article.ld_json)

    image = _get_page_image_info(article)
    title = _get_page_title(article)
    url = _get_page_url(article)
    ld_json = {
        '@context': 'http://schema.org',
        '@type': 'BlogPosting',
        'name': title,
        'url': url,
        'mainEntityOfPage': url,
        'headline': title,
        'datePublished': _get_create_date(article),
        'image': _image_ld_info(image),
        'description': _get_page_description(article),
        'author': [_make_ld_author(author) for author in article.authors],
        'publisher': _make_ld_publisher(article.settings)
    }

    modified = _get_modified_date(article)
    modified = modified if modified else ld_json['datePublished']
    ld_json['dateModified'] = modified

    return ld_json


def _make_ld_publisher(settings):
    publisher = settings['PUBLISHER']
    image = _make_publisher_image(settings, publisher['logo'])
    return {
        '@type': 'Organization',
        'name': publisher['name'],
        'logo': _image_ld_info(image)
    }


def _make_ld_author(author):
    if hasattr(author, 'ld_json'):
        return json.loads(author.ld_json)

    settings = author.settings
    image = _get_image_info(settings, settings['PATH'], author.picture)
    male_type = 'http://schema.org/Male'
    female_type = 'http://schema.org/Female'
    # TODO: add support for non binary types
    gender = male_type if author.gender == 'male' else female_type
    return {
        '@context': 'http://schema.org',
        '@type': 'Person',
        'url': _get_page_url(author),
        'image': _image_ld_info(image),
        'familyName': author.last_name,
        'givenName': author.first_name,
        'birthDate': author.birth_date,
        'email': author.email,
        'gender': gender,
        'height': author.height,
        'name': '{} {}'.format(author.first_name, author.last_name),
    }


def _make_ld_json(info, settings):
    inst = info['object']
    ld_json = None

    if isinstance(inst, ArticlesGenerator):
        ld_json = _make_ld_index(inst)

    elif isinstance(inst, Article):
        ld_json = _make_ld_article(inst)

    elif isinstance(inst, Author):
        ld_json = _make_ld_author(inst)

    elif isinstance(inst, Page):
        ld_json = _make_ld_page(inst)

    if ld_json:
        return json.dumps(ld_json, indent=4, separators=(',', ': '))


def _make_og_tags(info, settings):
    ptype = info['type']
    image = info['image']
    metas = {
        'fb:app_id': settings['FACEBOOK_APP_ID'],
        'og:type': ptype,
        'og:url': info['url'],
        'og:title': info['title'],
        'og:description': info['description'],
        'og:site_name': info['site_name'],
        'og:image': image['url'],
        'og:image:url': image['url'],
        'og:image:type': image['type'],
        'og:image:width': image['width'],
        'og:image:height': image['height']
    }

    if 'article' == ptype:
        metas['article:published_time'] = info['published_time']
        metas['article:section'] = info['section']

        if 'modified_time' in info:
            metas['article:modified_time'] = info['modified_time']

        site_url = settings['SITEURL']
        for author in info['authors']:
            metas['article:author'] = path.join(site_url, author.url)

        publisher = info['authors'][0]
        metas['article:publisher'] = path.join(site_url, publisher.url)

        og_tags = [('article:tag', tag) for tag in info['tags']]
        return metas.items() + og_tags

    elif 'profile' == ptype:
        metas.update({
            'og:first_name': info['first_name'],
            'og:last_name': info['last_name'],
            'og:gender': info['gender'],
            'og:username': info['username']
        })

    return metas.items()


def run_plugin(generators):
    for generator in generators:
        if isinstance(generator, ArticlesGenerator):
            for author, _ in generator.authors:
                _tag_author(author)

            for article in generator.articles:
                _tag_article(article)

            _tag_generator(generator)

        elif isinstance(generator, PagesGenerator):
            for page in generator.pages:
                _tag_page(page)


def register():
    signals.all_generators_finalized.connect(run_plugin)
