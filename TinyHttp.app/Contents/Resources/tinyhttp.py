#!/usr/bin/env python

# vim:fdm=marker sw=2 ts=2 ft=python expandtab:

import socket,sys
import cgi
import BaseHTTPServer,CGIHTTPServer

# CGIHTTPServer.CGIHTTPRequestHandler.cgi_directories = ['/']
for port in range(50080, 65535):
    try:
        print("starting sever - http://localhost:%d" % port)
        BaseHTTPServer.HTTPServer(( '0.0.0.0', port ), CGIHTTPServer.CGIHTTPRequestHandler ).serve_forever()
        break
    except socket.error:
        print "Unexpected error:", sys.exc_info()[0]

