import datetime
import os

import motor
from tornado.options import options as opts

from motor_blog import image
from motor_blog.api import engine, rpc
from motor_blog.text.link import media_link, absolute


class Media(object):
    """Mixin for motor_blog.api.handlers.APIHandler, deals with XML-RPC calls
       related to images and potentially other media
    """
    @rpc
    @engine
    def metaWeblog_newMediaObject(self, blogid, user, password, struct):
        name = struct['name']
        content = struct['bits'].data # xmlrpclib created a 'Binary' object
        content_type = struct['type']

        if image.is_retina_filename(name):
            # Store a HiDPI version and a half-sized regular version
            _, width, height = yield motor.Op(self.store_image,
                name, content, content_type, opts.maxwidth * 2)

            regular_name = image.regular_from_retina(name)
            mlink, _, _ = yield motor.Op(self.store_image,
                regular_name, content, content_type, width / 2)
        else:
            mlink, _, _ = yield motor.Op(self.store_image,
                name, content, content_type, opts.maxwidth)

        full_link = absolute(
            os.path.join(opts.base_url, 'media', mlink))
        
        self.result({
            'file': name, 'url': full_link, 'type': content_type})

    @engine
    def store_image(self, name, content, content_type, maxwidth, callback):
        try:
            # In a higher-volume site this work should be offloaded to a queue
            resized_content, width, height = image.resized(content, maxwidth)
            fs = yield motor.Op(motor.MotorGridFS(self.settings['db']).open)

            # This is the tail end of the URL, like 2012/06/foo.png
            now = datetime.datetime.utcnow()
            mlink = media_link(now.year, now.month, name)
            gridin = yield motor.Op(fs.new_file,
                filename=mlink,
                content_type=content_type,
                # GridFS stores any metadata we want
                width=width,
                height=height)

            yield motor.Op(gridin.write, resized_content)
            yield motor.Op(gridin.close)
            callback((mlink, width, height), None)
        except Exception, e:
            callback(None, e)
