import tornado.ioloop
import tornado.web
import os

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("test")


def startWebServer():
    app = tornado.web.Application([
        ("/", MainHandler),
    ],
        static_path=os.path.join(os.path.dirname(__file__), "statics"))
    app.listen(8080)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    startWebServer()