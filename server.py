#!/usr/bin/env python
import logging
import os
import sys

import pytz
import tornado.ioloop
import tornado.web
import tornado.options
from tornado.web import StaticFileHandler
from tornado import httpserver

# Patch Tornado with the Jade template loader
from tornado import template
from pyjade.ext.tornado import patch_tornado
patch_tornado()

try:
    import motor
except ImportError:
    print >> sys.stderr, (
        "Can't import motor.\n\n"
        " Motor is an experimental async driver for"
        " MongoDB, get it by cloning\n"
        " git://github.com/mongodb/motor.git \n"
        " then put the mongo-python-driver directory"
        " on your PYTHONPATH\n\n"
        )

    raise

from motor.web import GridFSHandler

from motor_blog import indexes, cache, options

from motor_blog.api.handlers import APIHandler, RSDHandler
from motor_blog.web.lytics import TrackingPixelHandler
from motor_blog.web.handlers import *
from motor_blog.web.admin import *

# TODO: RPC over HTTPS
# TODO: a static-url function to set long cache TTL on media URLs
# TODO: Nginx cache media
# TODO: sitemap.xml

if __name__ == "__main__":
    opts = options.options()

    # TODO: Mongo connection options
    db = motor.MotorClient().open_sync().motorblog
    cache.startup(db)

    if opts.rebuild_indexes or opts.ensure_indexes:
        indexes.ensure_indexes(
            db.connection.sync_client().motorblog,
            opts.rebuild_indexes)

    base_url = opts.base_url

    class U(tornado.web.URLSpec):
        def __init__(self, pattern, *args, **kwargs):
            """Include base_url in pattern"""
            super(U, self).__init__(
                '/' + base_url.strip('/') + '/' + pattern.lstrip('/'),
                *args, **kwargs
            )

        def _find_groups(self):
            """Get rid of final '?' -- Tornado's reverse_url() works poorly
               with tornado.web.addslash
            """
            path, group_count = super(U, self)._find_groups()
            if path.endswith('?'):
                path = path[:-1]
            return path, group_count

    static_path = os.path.join(opts.theme, 'static')

    application = tornado.web.Application([
        # XML-RPC API
        U(r"/rsd", RSDHandler, name='rsd'),
        U(r"/api", APIHandler, name='api'),

        # Admin
        U(r"admin/?", LoginHandler, name='login'),
        U(r"admin/logout/?", LogoutHandler, name='logout'),
        U(r"admin/drafts/?", DraftsHandler, name='drafts'),
        U(r"admin/draft/(?P<slug>.+)/?", DraftHandler, name='draft'),
        U(r"admin/media/?", MediaPageHandler, name='media-page'),
        U(r"admin/media/delete", DeleteMediaHandler, name='delete-media'),

        # Atom
        U(r"feed/?", FeedHandler, name='feed'),
        U(r"category/(?P<slug>.+)/feed/?", FeedHandler, name='category-feed'),

        # Web
        U(r"media/(.+)", GridFSHandler, {"database": db}, name='media'),
        U(r"tracking-pixel.gif", TrackingPixelHandler, name='tracking-pixel'),
        U(r"theme/static/(.+)", StaticFileHandler, {"path": static_path}, name='theme-static'),
        U(r"category/(?P<slug>.+)/page/(?P<page_num>\d+)/?", CategoryHandler, name='category-page'),
        U(r"category/(?P<slug>.+)/?", CategoryHandler, name='category'),
        U(r"page/(?P<page_num>\d+)/?", HomeHandler, name='page'),
        U(r"all-posts/?", AllPostsHandler, name='all-posts'),
        U(r"tag/(?P<tag>.+)/page/(?P<page_num>\d+)/?", TagHandler, name='tag-page'),
        U(r"tag/(?P<tag>.+)/?", TagHandler, name='tag'),
        U(r"search/", SearchHandler, name='search'),
        # PostHandler's URL pattern must be last because slug could be anything
        U(r"(?P<slug>.+)/?", PostHandler, name='post'),
        U(r"/?", HomeHandler, name='home'),

        ],
        db=db,
        template_path=os.path.join(opts.theme, 'templates'),
        tz=pytz.timezone(opts.timezone),
        gzip=True,
        **{k: v.value() for k, v in opts.items()}
    )

    http_server = httpserver.HTTPServer(application, xheaders=True)
    http_server.listen(opts.port)
    msg = 'Listening on port %s' % opts.port
    print msg
    logging.info(msg)
    tornado.ioloop.IOLoop.instance().start()
